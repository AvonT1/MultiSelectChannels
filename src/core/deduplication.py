"""
Deduplication service for preventing duplicate message forwarding.
Uses content hashing and database caching with TTL support.
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert

from src.database import get_db_session, DeduplicationCache
from src.config import settings

logger = logging.getLogger(__name__)


class DeduplicationService:
    """Service for detecting and preventing duplicate message forwarding."""
    
    def __init__(self, cache_ttl_hours: int = 24):
        self.cache_ttl_hours = cache_ttl_hours
    
    async def is_duplicate(self, message_data: Dict[str, Any]) -> bool:
        """Check if a message is a duplicate based on content hash."""
        content_hash = message_data.get('content_hash')
        if not content_hash:
            logger.warning("Message data missing content_hash")
            return False
        
        try:
            async with get_db_session() as session:
                # Check if hash exists in cache
                result = await session.execute(
                    select(DeduplicationCache).where(
                        DeduplicationCache.content_hash == content_hash
                    )
                )
                existing = result.scalar_one_or_none()
                
                if existing:
                    # Check if cache entry is still valid (within TTL)
                    if self._is_cache_valid(existing.created_at):
                        logger.debug(f"Duplicate detected: {content_hash}")
                        return True
                    else:
                        # Remove expired entry
                        await session.delete(existing)
                        await session.commit()
                
                return False
                
        except Exception as e:
            logger.error(f"Error checking for duplicate: {e}")
            return False
    
    async def mark_as_processed(self, message_data: Dict[str, Any]) -> None:
        """Mark a message as processed to prevent future duplicates."""
        content_hash = message_data.get('content_hash')
        source_channel_id = message_data.get('source_channel_id')
        source_message_id = message_data.get('message_id')
        
        if not all([content_hash, source_channel_id, source_message_id]):
            logger.warning("Incomplete message data for deduplication marking")
            return
        
        try:
            async with get_db_session() as session:
                # Use PostgreSQL UPSERT to handle race conditions
                stmt = insert(DeduplicationCache).values(
                    content_hash=content_hash,
                    source_channel_id=source_channel_id,
                    source_message_id=source_message_id,
                    created_at=datetime.utcnow()
                )
                stmt = stmt.on_conflict_do_nothing(index_elements=['content_hash'])
                
                await session.execute(stmt)
                await session.commit()
                
                logger.debug(f"Marked message as processed: {content_hash}")
                
        except Exception as e:
            logger.error(f"Error marking message as processed: {e}")
    
    async def cleanup_expired_entries(self) -> int:
        """Clean up expired deduplication cache entries."""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=self.cache_ttl_hours)
            
            async with get_db_session() as session:
                result = await session.execute(
                    delete(DeduplicationCache).where(
                        DeduplicationCache.created_at < cutoff_time
                    )
                )
                
                deleted_count = result.rowcount
                await session.commit()
                
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} expired deduplication entries")
                
                return deleted_count
                
        except Exception as e:
            logger.error(f"Error cleaning up expired entries: {e}")
            return 0
    
    async def get_cache_statistics(self) -> Dict[str, Any]:
        """Get deduplication cache statistics."""
        try:
            async with get_db_session() as session:
                from sqlalchemy import func
                
                # Total entries
                total_result = await session.execute(
                    select(func.count(DeduplicationCache.id))
                )
                total_entries = total_result.scalar()
                
                # Entries by age
                cutoff_time = datetime.utcnow() - timedelta(hours=self.cache_ttl_hours)
                valid_result = await session.execute(
                    select(func.count(DeduplicationCache.id)).where(
                        DeduplicationCache.created_at >= cutoff_time
                    )
                )
                valid_entries = valid_result.scalar()
                
                expired_entries = total_entries - valid_entries
                
                return {
                    'total_entries': total_entries,
                    'valid_entries': valid_entries,
                    'expired_entries': expired_entries,
                    'cache_ttl_hours': self.cache_ttl_hours
                }
                
        except Exception as e:
            logger.error(f"Error getting cache statistics: {e}")
            return {
                'total_entries': 0,
                'valid_entries': 0,
                'expired_entries': 0,
                'cache_ttl_hours': self.cache_ttl_hours
            }
    
    def _is_cache_valid(self, created_at: datetime) -> bool:
        """Check if a cache entry is still valid based on TTL."""
        expiry_time = created_at + timedelta(hours=self.cache_ttl_hours)
        return datetime.utcnow() < expiry_time
    
    async def force_cleanup_all(self) -> int:
        """Force cleanup of all deduplication entries (use with caution)."""
        try:
            async with get_db_session() as session:
                result = await session.execute(delete(DeduplicationCache))
                deleted_count = result.rowcount
                await session.commit()
                
                logger.warning(f"Force cleaned all {deleted_count} deduplication entries")
                return deleted_count
                
        except Exception as e:
            logger.error(f"Error in force cleanup: {e}")
            return 0
