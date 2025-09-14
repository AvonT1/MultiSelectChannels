"""
Redis-based queue manager for handling message forwarding tasks.
Implements priority queuing, retry logic, and FloodWait handling.
"""
import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

import aioredis
from aioredis import Redis

from src.config import settings

logger = logging.getLogger(__name__)


class QueueManager:
    """Manages Redis-based message queuing with retry and FloodWait support."""
    
    def __init__(self):
        self.redis: Optional[Redis] = None
        self._running = False
        
        # Queue names
        self.main_queue = "forwarding:messages"
        self.retry_queue = "forwarding:retry"
        self.failed_queue = "forwarding:failed"
        self.flood_wait_queue = "forwarding:flood_wait"
        
        # Queue processing task
        self._retry_processor_task = None
        self._flood_wait_processor_task = None
    
    async def start(self) -> None:
        """Start the queue manager and connect to Redis."""
        if self._running:
            return
        
        logger.info("Starting queue manager...")
        
        # Connect to Redis
        self.redis = await aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20
        )
        
        # Test connection
        await self.redis.ping()
        
        self._running = True
        
        # Start background processors
        self._retry_processor_task = asyncio.create_task(self._process_retry_queue())
        self._flood_wait_processor_task = asyncio.create_task(self._process_flood_wait_queue())
        
        logger.info("Queue manager started successfully")
    
    async def stop(self) -> None:
        """Stop the queue manager and close Redis connection."""
        if not self._running:
            return
        
        logger.info("Stopping queue manager...")
        self._running = False
        
        # Cancel background tasks
        if self._retry_processor_task:
            self._retry_processor_task.cancel()
        if self._flood_wait_processor_task:
            self._flood_wait_processor_task.cancel()
        
        # Wait for tasks to complete
        await asyncio.gather(
            self._retry_processor_task, 
            self._flood_wait_processor_task,
            return_exceptions=True
        )
        
        # Close Redis connection
        if self.redis:
            await self.redis.close()
        
        logger.info("Queue manager stopped")
    
    async def enqueue_message(self, message_data: Dict[str, Any], priority: int = 0) -> None:
        """Add a message to the main processing queue."""
        if not self.redis:
            raise RuntimeError("Queue manager not started")
        
        try:
            # Add metadata
            message_data['enqueued_at'] = datetime.utcnow().isoformat()
            message_data['priority'] = priority
            message_data['attempts'] = 0
            
            # Serialize and enqueue
            message_json = json.dumps(message_data)
            
            if priority > 0:
                # Use sorted set for priority queue
                await self.redis.zadd(f"{self.main_queue}:priority", {message_json: priority})
            else:
                # Use regular list for normal priority
                await self.redis.lpush(self.main_queue, message_json)
            
            logger.debug(f"Enqueued message with priority {priority}")
            
        except Exception as e:
            logger.error(f"Error enqueuing message: {e}")
            raise
    
    async def dequeue_message(self, timeout: int = 5) -> Optional[Dict[str, Any]]:
        """Get a message from the queue for processing."""
        if not self.redis:
            return None
        
        try:
            # First check priority queue
            priority_result = await self.redis.zpopmax(f"{self.main_queue}:priority")
            if priority_result:
                message_json = priority_result[0][0]
                return json.loads(message_json)
            
            # Then check regular queue
            result = await self.redis.brpop(self.main_queue, timeout=timeout)
            if result:
                message_json = result[1]
                return json.loads(message_json)
            
            return None
            
        except Exception as e:
            logger.error(f"Error dequeuing message: {e}")
            return None
    
    async def enqueue_retry(self, message_data: Dict[str, Any], delay_seconds: int) -> None:
        """Add a message to the retry queue with delay."""
        if not self.redis:
            raise RuntimeError("Queue manager not started")
        
        try:
            # Update retry metadata
            message_data['attempts'] = message_data.get('attempts', 0) + 1
            message_data['retry_after'] = (datetime.utcnow() + timedelta(seconds=delay_seconds)).isoformat()
            
            # Add to retry queue with score as timestamp
            retry_time = datetime.utcnow().timestamp() + delay_seconds
            message_json = json.dumps(message_data)
            
            await self.redis.zadd(self.retry_queue, {message_json: retry_time})
            
            logger.debug(f"Enqueued message for retry in {delay_seconds} seconds (attempt {message_data['attempts']})")
            
        except Exception as e:
            logger.error(f"Error enqueuing retry: {e}")
            raise
    
    async def enqueue_flood_wait(self, message_data: Dict[str, Any], wait_seconds: int) -> None:
        """Add a message to the FloodWait queue."""
        if not self.redis:
            raise RuntimeError("Queue manager not started")
        
        try:
            # Update FloodWait metadata
            message_data['flood_wait_until'] = (datetime.utcnow() + timedelta(seconds=wait_seconds)).isoformat()
            message_data['flood_wait_duration'] = wait_seconds
            
            # Add to FloodWait queue
            wait_until = datetime.utcnow().timestamp() + wait_seconds
            message_json = json.dumps(message_data)
            
            await self.redis.zadd(self.flood_wait_queue, {message_json: wait_until})
            
            logger.info(f"Enqueued message for FloodWait processing in {wait_seconds} seconds")
            
        except Exception as e:
            logger.error(f"Error enqueuing FloodWait: {e}")
            raise
    
    async def enqueue_failed(self, message_data: Dict[str, Any], error_message: str) -> None:
        """Add a permanently failed message to the failed queue."""
        if not self.redis:
            raise RuntimeError("Queue manager not started")
        
        try:
            # Update failure metadata
            message_data['failed_at'] = datetime.utcnow().isoformat()
            message_data['final_error'] = error_message
            message_data['final_attempts'] = message_data.get('attempts', 0)
            
            message_json = json.dumps(message_data)
            await self.redis.lpush(self.failed_queue, message_json)
            
            logger.warning(f"Message permanently failed after {message_data.get('attempts', 0)} attempts: {error_message}")
            
        except Exception as e:
            logger.error(f"Error enqueuing failed message: {e}")
            raise
    
    async def _process_retry_queue(self) -> None:
        """Background processor for retry queue."""
        logger.info("Starting retry queue processor")
        
        while self._running:
            try:
                current_time = datetime.utcnow().timestamp()
                
                # Get messages ready for retry
                results = await self.redis.zrangebyscore(
                    self.retry_queue, 0, current_time, withscores=True
                )
                
                for message_json, score in results:
                    # Remove from retry queue
                    await self.redis.zrem(self.retry_queue, message_json)
                    
                    # Re-enqueue for processing
                    message_data = json.loads(message_json)
                    await self.enqueue_message(message_data)
                    
                    logger.debug("Moved message from retry queue back to main queue")
                
                # Sleep before next check
                await asyncio.sleep(10)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in retry queue processor: {e}")
                await asyncio.sleep(30)
        
        logger.info("Retry queue processor stopped")
    
    async def _process_flood_wait_queue(self) -> None:
        """Background processor for FloodWait queue."""
        logger.info("Starting FloodWait queue processor")
        
        while self._running:
            try:
                current_time = datetime.utcnow().timestamp()
                
                # Get messages ready after FloodWait
                results = await self.redis.zrangebyscore(
                    self.flood_wait_queue, 0, current_time, withscores=True
                )
                
                for message_json, score in results:
                    # Remove from FloodWait queue
                    await self.redis.zrem(self.flood_wait_queue, message_json)
                    
                    # Re-enqueue for processing
                    message_data = json.loads(message_json)
                    await self.enqueue_message(message_data)
                    
                    logger.info("Moved message from FloodWait queue back to main queue")
                
                # Sleep before next check
                await asyncio.sleep(15)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in FloodWait queue processor: {e}")
                await asyncio.sleep(30)
        
        logger.info("FloodWait queue processor stopped")
    
    async def get_queue_size(self) -> Dict[str, int]:
        """Get the size of all queues."""
        if not self.redis:
            return {}
        
        try:
            sizes = {}
            sizes['main'] = await self.redis.llen(self.main_queue)
            sizes['priority'] = await self.redis.zcard(f"{self.main_queue}:priority")
            sizes['retry'] = await self.redis.zcard(self.retry_queue)
            sizes['flood_wait'] = await self.redis.zcard(self.flood_wait_queue)
            sizes['failed'] = await self.redis.llen(self.failed_queue)
            sizes['total'] = sum(sizes.values())
            
            return sizes
            
        except Exception as e:
            logger.error(f"Error getting queue sizes: {e}")
            return {}
    
    async def get_queue_statistics(self) -> Dict[str, Any]:
        """Get comprehensive queue statistics."""
        sizes = await self.get_queue_size()
        
        # Additional statistics could be added here
        # (processing rates, average wait times, etc.)
        
        return {
            'queue_sizes': sizes,
            'is_running': self._running,
            'redis_connected': self.redis is not None
        }
    
    async def clear_queue(self, queue_name: str) -> int:
        """Clear a specific queue (admin operation)."""
        if not self.redis:
            return 0
        
        try:
            if queue_name == 'main':
                deleted = await self.redis.delete(self.main_queue)
                deleted += await self.redis.delete(f"{self.main_queue}:priority")
            elif queue_name == 'retry':
                deleted = await self.redis.delete(self.retry_queue)
            elif queue_name == 'flood_wait':
                deleted = await self.redis.delete(self.flood_wait_queue)
            elif queue_name == 'failed':
                deleted = await self.redis.delete(self.failed_queue)
            else:
                return 0
            
            logger.warning(f"Cleared {queue_name} queue, deleted {deleted} keys")
            return deleted
            
        except Exception as e:
            logger.error(f"Error clearing queue {queue_name}: {e}")
            return 0
