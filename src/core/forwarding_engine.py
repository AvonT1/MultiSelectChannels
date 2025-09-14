"""
Core forwarding engine that orchestrates message processing and routing.
Handles the main forwarding logic with dual-client support.
"""
import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.database import (
    get_db_session, Channel, ForwardingMapping, MessageLog, 
    AccessType, ForwardingMode, MessageStatus
)
from src.clients import ClientFactory, ClientType
from src.core.message_processor import MessageProcessor
from src.core.deduplication import DeduplicationService
from src.core.queue_manager import QueueManager
from src.config import settings

logger = logging.getLogger(__name__)


class ForwardingEngine:
    """Main forwarding engine that coordinates all forwarding operations."""
    
    def __init__(self, client_factory: ClientFactory):
        self.client_factory = client_factory
        self.message_processor = MessageProcessor(client_factory)
        self.deduplication_service = DeduplicationService()
        self.queue_manager = QueueManager()
        self._running = False
        self._processing_tasks = []
    
    async def start(self) -> None:
        """Start the forwarding engine."""
        if self._running:
            return
        
        logger.info("Starting forwarding engine...")
        
        # Start queue manager
        await self.queue_manager.start()
        
        # Start processing tasks
        self._running = True
        for i in range(settings.max_concurrent_forwards):
            task = asyncio.create_task(self._process_queue_worker(f"worker-{i}"))
            self._processing_tasks.append(task)
        
        logger.info(f"Forwarding engine started with {settings.max_concurrent_forwards} workers")
    
    async def stop(self) -> None:
        """Stop the forwarding engine."""
        if not self._running:
            return
        
        logger.info("Stopping forwarding engine...")
        self._running = False
        
        # Cancel processing tasks
        for task in self._processing_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        await asyncio.gather(*self._processing_tasks, return_exceptions=True)
        self._processing_tasks.clear()
        
        # Stop queue manager
        await self.queue_manager.stop()
        
        logger.info("Forwarding engine stopped")
    
    async def process_new_message(self, source_channel_id: int, message_id: int, message_data: Dict[str, Any]) -> None:
        """Process a new message for forwarding."""
        try:
            # Check for deduplication
            if await self.deduplication_service.is_duplicate(message_data):
                logger.debug(f"Duplicate message detected: {source_channel_id}:{message_id}")
                return
            
            # Get forwarding mappings for this source channel
            mappings = await self._get_forwarding_mappings(source_channel_id)
            if not mappings:
                logger.debug(f"No forwarding mappings found for channel {source_channel_id}")
                return
            
            # Create message log entry
            dest_channel_ids = [mapping.dest_channel_id for mapping in mappings]
            message_log = await self._create_message_log(source_channel_id, message_id, dest_channel_ids)
            
            # Queue for processing
            queue_item = {
                'message_log_id': message_log.id,
                'source_channel_id': source_channel_id,
                'message_id': message_id,
                'mappings': [
                    {
                        'dest_channel_id': m.dest_channel_id,
                        'mode': m.mode.value,
                        'source_access': m.source_channel.access_type.value,
                        'dest_access': m.dest_channel.access_type.value
                    }
                    for m in mappings
                ],
                'message_data': message_data,
                'created_at': datetime.utcnow().isoformat()
            }
            
            await self.queue_manager.enqueue_message(queue_item)
            logger.debug(f"Queued message for forwarding: {source_channel_id}:{message_id}")
            
        except Exception as e:
            logger.error(f"Error processing new message {source_channel_id}:{message_id}: {e}", exc_info=True)
    
    async def _process_queue_worker(self, worker_name: str) -> None:
        """Worker that processes messages from the queue."""
        logger.info(f"Starting queue worker: {worker_name}")
        
        while self._running:
            try:
                # Get message from queue
                queue_item = await self.queue_manager.dequeue_message()
                if not queue_item:
                    await asyncio.sleep(1)
                    continue
                
                # Process the message
                await self._process_queued_message(queue_item, worker_name)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in queue worker {worker_name}: {e}", exc_info=True)
                await asyncio.sleep(5)  # Back off on error
        
        logger.info(f"Queue worker stopped: {worker_name}")
    
    async def _process_queued_message(self, queue_item: Dict[str, Any], worker_name: str) -> None:
        """Process a single queued message."""
        message_log_id = queue_item['message_log_id']
        source_channel_id = queue_item['source_channel_id']
        message_id = queue_item['message_id']
        mappings = queue_item['mappings']
        
        logger.debug(f"Worker {worker_name} processing message {source_channel_id}:{message_id}")
        
        try:
            # Update message log status
            await self._update_message_log_status(message_log_id, MessageStatus.PROCESSING)
            
            # Process each mapping
            forwarded_message_ids = {}
            all_successful = True
            
            for mapping in mappings:
                dest_channel_id = mapping['dest_channel_id']
                mode = ForwardingMode(mapping['mode'])
                source_access = AccessType(mapping['source_access'])
                dest_access = AccessType(mapping['dest_access'])
                
                # Determine optimal client
                client_type = self.client_factory.get_optimal_client(source_access, dest_access)
                
                # Forward/copy the message
                result = await self._forward_single_message(
                    source_channel_id, message_id, dest_channel_id, mode, client_type
                )
                
                if result:
                    forwarded_message_ids[str(dest_channel_id)] = result['message_id']
                    logger.debug(f"Successfully forwarded to {dest_channel_id}: {result['message_id']}")
                else:
                    all_successful = False
                    logger.warning(f"Failed to forward to {dest_channel_id}")
            
            # Update message log with results
            if all_successful:
                await self._update_message_log_success(message_log_id, forwarded_message_ids)
            else:
                await self._update_message_log_partial_success(message_log_id, forwarded_message_ids)
            
        except Exception as e:
            logger.error(f"Error processing queued message {message_log_id}: {e}", exc_info=True)
            await self._update_message_log_error(message_log_id, str(e))
    
    async def _forward_single_message(self, source_channel_id: int, message_id: int, 
                                    dest_channel_id: int, mode: ForwardingMode, 
                                    client_type: ClientType) -> Optional[Dict[str, Any]]:
        """Forward a single message to a destination."""
        try:
            if mode == ForwardingMode.FORWARD:
                return await self.client_factory.forward_message(
                    dest_channel_id, source_channel_id, message_id, client_type=client_type
                )
            else:  # COPY mode
                return await self.client_factory.copy_message(
                    dest_channel_id, source_channel_id, message_id, client_type=client_type
                )
        except Exception as e:
            logger.error(f"Error forwarding message: {e}")
            return None
    
    async def _get_forwarding_mappings(self, source_channel_id: int) -> List[ForwardingMapping]:
        """Get active forwarding mappings for a source channel."""
        async with get_db_session() as session:
            result = await session.execute(
                select(ForwardingMapping)
                .options(
                    selectinload(ForwardingMapping.source_channel),
                    selectinload(ForwardingMapping.dest_channel)
                )
                .join(Channel, ForwardingMapping.source_channel_id == Channel.id)
                .where(
                    Channel.telegram_id == source_channel_id,
                    ForwardingMapping.enabled == True,
                    Channel.is_active == True
                )
            )
            return result.scalars().all()
    
    async def _create_message_log(self, source_channel_id: int, message_id: int, 
                                dest_channel_ids: List[int]) -> MessageLog:
        """Create a new message log entry."""
        async with get_db_session() as session:
            # Get source channel
            result = await session.execute(
                select(Channel).where(Channel.telegram_id == source_channel_id)
            )
            source_channel = result.scalar_one()
            
            message_log = MessageLog(
                source_channel_id=source_channel.id,
                source_message_id=message_id,
                dest_channel_ids=dest_channel_ids,
                status=MessageStatus.PENDING,
                processing_started_at=datetime.utcnow()
            )
            
            session.add(message_log)
            await session.commit()
            await session.refresh(message_log)
            return message_log
    
    async def _update_message_log_status(self, message_log_id: int, status: MessageStatus) -> None:
        """Update message log status."""
        async with get_db_session() as session:
            result = await session.execute(
                select(MessageLog).where(MessageLog.id == message_log_id)
            )
            message_log = result.scalar_one()
            message_log.status = status
            await session.commit()
    
    async def _update_message_log_success(self, message_log_id: int, forwarded_message_ids: Dict[str, int]) -> None:
        """Update message log with successful forwarding results."""
        async with get_db_session() as session:
            result = await session.execute(
                select(MessageLog).where(MessageLog.id == message_log_id)
            )
            message_log = result.scalar_one()
            message_log.status = MessageStatus.SUCCESS
            message_log.forwarded_message_ids = forwarded_message_ids
            message_log.processing_completed_at = datetime.utcnow()
            await session.commit()
    
    async def _update_message_log_partial_success(self, message_log_id: int, forwarded_message_ids: Dict[str, int]) -> None:
        """Update message log with partial success (some destinations failed)."""
        async with get_db_session() as session:
            result = await session.execute(
                select(MessageLog).where(MessageLog.id == message_log_id)
            )
            message_log = result.scalar_one()
            message_log.status = MessageStatus.FAILED
            message_log.forwarded_message_ids = forwarded_message_ids
            message_log.last_error = "Partial success - some destinations failed"
            message_log.processing_completed_at = datetime.utcnow()
            await session.commit()
    
    async def _update_message_log_error(self, message_log_id: int, error_message: str) -> None:
        """Update message log with error."""
        async with get_db_session() as session:
            result = await session.execute(
                select(MessageLog).where(MessageLog.id == message_log_id)
            )
            message_log = result.scalar_one()
            message_log.status = MessageStatus.FAILED
            message_log.last_error = error_message
            message_log.attempts += 1
            message_log.processing_completed_at = datetime.utcnow()
            await session.commit()
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Get forwarding statistics."""
        async with get_db_session() as session:
            # Get message counts by status
            from sqlalchemy import func
            
            result = await session.execute(
                select(MessageLog.status, func.count(MessageLog.id))
                .group_by(MessageLog.status)
            )
            status_counts = dict(result.all())
            
            # Get queue size
            queue_size = await self.queue_manager.get_queue_size()
            
            return {
                'queue_size': queue_size,
                'message_counts': {
                    'pending': status_counts.get(MessageStatus.PENDING, 0),
                    'processing': status_counts.get(MessageStatus.PROCESSING, 0),
                    'success': status_counts.get(MessageStatus.SUCCESS, 0),
                    'failed': status_counts.get(MessageStatus.FAILED, 0),
                    'retrying': status_counts.get(MessageStatus.RETRYING, 0)
                },
                'workers_running': len(self._processing_tasks),
                'engine_running': self._running
            }
    
    @property
    def is_running(self) -> bool:
        """Check if forwarding engine is running."""
        return self._running
