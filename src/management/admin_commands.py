"""
Administrative commands for system management and maintenance.
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from sqlalchemy import select, func, delete, update
from src.database import (
    get_db_session, init_database, close_database,
    User, Channel, ForwardingMapping, MessageLog, DeduplicationCache,
    AccessType, ForwardingMode, MessageStatus, UserRole
)
from src.config import settings

logger = logging.getLogger(__name__)


class AdminCommands:
    """Administrative commands for system management."""
    
    async def create_admin_user(self, telegram_id: int, username: Optional[str] = None) -> Dict[str, Any]:
        """Create a new administrator user."""
        try:
            await init_database()
            
            async with get_db_session() as session:
                # Check if user already exists
                result = await session.execute(
                    select(User).where(User.telegram_id == telegram_id)
                )
                existing_user = result.scalar_one_or_none()
                
                if existing_user:
                    if existing_user.role == UserRole.ADMINISTRATOR:
                        return {
                            'success': False,
                            'message': f'User {telegram_id} is already an administrator'
                        }
                    else:
                        # Upgrade existing user to admin
                        existing_user.role = UserRole.ADMINISTRATOR
                        await session.commit()
                        return {
                            'success': True,
                            'message': f'User {telegram_id} upgraded to administrator'
                        }
                else:
                    # Create new admin user
                    admin_user = User(
                        telegram_id=telegram_id,
                        username=username,
                        role=UserRole.ADMINISTRATOR
                    )
                    session.add(admin_user)
                    await session.commit()
                    
                    return {
                        'success': True,
                        'message': f'Administrator user {telegram_id} created successfully'
                    }
                    
        except Exception as e:
            logger.error(f"Failed to create admin user: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
        finally:
            await close_database()
    
    async def list_users(self, role_filter: Optional[UserRole] = None) -> Dict[str, Any]:
        """List all users, optionally filtered by role."""
        try:
            await init_database()
            
            async with get_db_session() as session:
                query = select(User)
                if role_filter:
                    query = query.where(User.role == role_filter)
                
                result = await session.execute(query.order_by(User.created_at.desc()))
                users = result.scalars().all()
                
                user_list = []
                for user in users:
                    user_list.append({
                        'id': user.id,
                        'telegram_id': user.telegram_id,
                        'username': user.username,
                        'role': user.role.value,
                        'created_at': user.created_at.isoformat(),
                        'last_seen': user.last_seen.isoformat() if user.last_seen else None
                    })
                
                return {
                    'success': True,
                    'users': user_list,
                    'total_count': len(user_list)
                }
                
        except Exception as e:
            logger.error(f"Failed to list users: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
        finally:
            await close_database()
    
    async def manage_channel(self, action: str, telegram_id: int, **kwargs) -> Dict[str, Any]:
        """Manage channel operations (add, remove, update, activate, deactivate)."""
        try:
            await init_database()
            
            async with get_db_session() as session:
                if action == "add":
                    return await self._add_channel(session, telegram_id, **kwargs)
                elif action == "remove":
                    return await self._remove_channel(session, telegram_id)
                elif action == "update":
                    return await self._update_channel(session, telegram_id, **kwargs)
                elif action == "activate":
                    return await self._toggle_channel(session, telegram_id, True)
                elif action == "deactivate":
                    return await self._toggle_channel(session, telegram_id, False)
                else:
                    return {
                        'success': False,
                        'error': f'Unknown action: {action}'
                    }
                    
        except Exception as e:
            logger.error(f"Failed to manage channel: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
        finally:
            await close_database()
    
    async def _add_channel(self, session, telegram_id: int, **kwargs) -> Dict[str, Any]:
        """Add a new channel."""
        # Check if channel already exists
        result = await session.execute(
            select(Channel).where(Channel.telegram_id == telegram_id)
        )
        existing_channel = result.scalar_one_or_none()
        
        if existing_channel:
            return {
                'success': False,
                'message': f'Channel {telegram_id} already exists'
            }
        
        # Get admin user for added_by_user_id
        admin_result = await session.execute(
            select(User).where(User.role == UserRole.ADMINISTRATOR).limit(1)
        )
        admin_user = admin_result.scalar_one()
        
        channel = Channel(
            telegram_id=telegram_id,
            title=kwargs.get('title', f'Channel {telegram_id}'),
            access_type=AccessType(kwargs.get('access_type', 'user')),
            added_by_user_id=admin_user.id,
            metadata=kwargs.get('metadata', {})
        )
        
        session.add(channel)
        await session.commit()
        
        return {
            'success': True,
            'message': f'Channel {telegram_id} added successfully'
        }
    
    async def _remove_channel(self, session, telegram_id: int) -> Dict[str, Any]:
        """Remove a channel and its mappings."""
        result = await session.execute(
            select(Channel).where(Channel.telegram_id == telegram_id)
        )
        channel = result.scalar_one_or_none()
        
        if not channel:
            return {
                'success': False,
                'message': f'Channel {telegram_id} not found'
            }
        
        # Remove associated mappings
        await session.execute(
            delete(ForwardingMapping).where(
                (ForwardingMapping.source_channel_id == channel.id) |
                (ForwardingMapping.dest_channel_id == channel.id)
            )
        )
        
        # Remove the channel
        await session.delete(channel)
        await session.commit()
        
        return {
            'success': True,
            'message': f'Channel {telegram_id} and its mappings removed successfully'
        }
    
    async def _update_channel(self, session, telegram_id: int, **kwargs) -> Dict[str, Any]:
        """Update channel properties."""
        result = await session.execute(
            select(Channel).where(Channel.telegram_id == telegram_id)
        )
        channel = result.scalar_one_or_none()
        
        if not channel:
            return {
                'success': False,
                'message': f'Channel {telegram_id} not found'
            }
        
        # Update allowed fields
        if 'title' in kwargs:
            channel.title = kwargs['title']
        if 'access_type' in kwargs:
            channel.access_type = AccessType(kwargs['access_type'])
        if 'metadata' in kwargs:
            channel.metadata = kwargs['metadata']
        
        await session.commit()
        
        return {
            'success': True,
            'message': f'Channel {telegram_id} updated successfully'
        }
    
    async def _toggle_channel(self, session, telegram_id: int, active: bool) -> Dict[str, Any]:
        """Activate or deactivate a channel."""
        result = await session.execute(
            select(Channel).where(Channel.telegram_id == telegram_id)
        )
        channel = result.scalar_one_or_none()
        
        if not channel:
            return {
                'success': False,
                'message': f'Channel {telegram_id} not found'
            }
        
        channel.is_active = active
        await session.commit()
        
        status = "activated" if active else "deactivated"
        return {
            'success': True,
            'message': f'Channel {telegram_id} {status} successfully'
        }
    
    async def create_mapping(self, source_id: int, dest_id: int, 
                           mode: str = "forward", enabled: bool = True) -> Dict[str, Any]:
        """Create a forwarding mapping between channels."""
        try:
            await init_database()
            
            async with get_db_session() as session:
                # Get source and destination channels
                source_result = await session.execute(
                    select(Channel).where(Channel.telegram_id == source_id)
                )
                source_channel = source_result.scalar_one_or_none()
                
                dest_result = await session.execute(
                    select(Channel).where(Channel.telegram_id == dest_id)
                )
                dest_channel = dest_result.scalar_one_or_none()
                
                if not source_channel:
                    return {
                        'success': False,
                        'message': f'Source channel {source_id} not found'
                    }
                
                if not dest_channel:
                    return {
                        'success': False,
                        'message': f'Destination channel {dest_id} not found'
                    }
                
                # Check if mapping already exists
                existing_result = await session.execute(
                    select(ForwardingMapping).where(
                        ForwardingMapping.source_channel_id == source_channel.id,
                        ForwardingMapping.dest_channel_id == dest_channel.id
                    )
                )
                existing_mapping = existing_result.scalar_one_or_none()
                
                if existing_mapping:
                    return {
                        'success': False,
                        'message': f'Mapping from {source_id} to {dest_id} already exists'
                    }
                
                # Create new mapping
                mapping = ForwardingMapping(
                    source_channel_id=source_channel.id,
                    dest_channel_id=dest_channel.id,
                    mode=ForwardingMode(mode),
                    enabled=enabled
                )
                
                session.add(mapping)
                await session.commit()
                
                return {
                    'success': True,
                    'message': f'Mapping created: {source_id} -> {dest_id} ({mode})'
                }
                
        except Exception as e:
            logger.error(f"Failed to create mapping: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
        finally:
            await close_database()
    
    async def cleanup_old_data(self, days_old: int = 30) -> Dict[str, Any]:
        """Clean up old message logs and deduplication cache entries."""
        try:
            await init_database()
            
            cutoff_date = datetime.utcnow() - timedelta(days=days_old)
            cleanup_stats = {
                'message_logs_deleted': 0,
                'dedup_cache_deleted': 0
            }
            
            async with get_db_session() as session:
                # Clean up old successful message logs
                message_result = await session.execute(
                    delete(MessageLog).where(
                        MessageLog.created_at < cutoff_date,
                        MessageLog.status == MessageStatus.SUCCESS
                    )
                )
                cleanup_stats['message_logs_deleted'] = message_result.rowcount
                
                # Clean up old deduplication cache entries
                dedup_result = await session.execute(
                    delete(DeduplicationCache).where(
                        DeduplicationCache.created_at < cutoff_date
                    )
                )
                cleanup_stats['dedup_cache_deleted'] = dedup_result.rowcount
                
                await session.commit()
            
            return {
                'success': True,
                'message': f'Cleaned up data older than {days_old} days',
                'stats': cleanup_stats
            }
            
        except Exception as e:
            logger.error(f"Failed to cleanup old data: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
        finally:
            await close_database()
    
    async def get_system_stats(self) -> Dict[str, Any]:
        """Get comprehensive system statistics."""
        try:
            await init_database()
            
            async with get_db_session() as session:
                # Basic counts
                user_count = await session.execute(select(func.count(User.id)))
                channel_count = await session.execute(select(func.count(Channel.id)))
                mapping_count = await session.execute(select(func.count(ForwardingMapping.id)))
                
                # Active mappings
                active_mappings = await session.execute(
                    select(func.count(ForwardingMapping.id)).where(ForwardingMapping.enabled == True)
                )
                
                # Recent message activity (last 24 hours)
                recent_cutoff = datetime.utcnow() - timedelta(hours=24)
                recent_messages = await session.execute(
                    select(MessageLog.status, func.count(MessageLog.id))
                    .where(MessageLog.created_at >= recent_cutoff)
                    .group_by(MessageLog.status)
                )
                recent_stats = dict(recent_messages.all())
                
                # Channel access types
                access_types = await session.execute(
                    select(Channel.access_type, func.count(Channel.id))
                    .group_by(Channel.access_type)
                )
                access_stats = dict(access_types.all())
                
                # Forwarding modes
                forwarding_modes = await session.execute(
                    select(ForwardingMapping.mode, func.count(ForwardingMapping.id))
                    .group_by(ForwardingMapping.mode)
                )
                mode_stats = dict(forwarding_modes.all())
                
                return {
                    'success': True,
                    'stats': {
                        'total_users': user_count.scalar(),
                        'total_channels': channel_count.scalar(),
                        'total_mappings': mapping_count.scalar(),
                        'active_mappings': active_mappings.scalar(),
                        'recent_24h_messages': {status.value: count for status, count in recent_stats.items()},
                        'channels_by_access': {access.value: count for access, count in access_stats.items()},
                        'mappings_by_mode': {mode.value: count for mode, count in mode_stats.items()},
                        'generated_at': datetime.utcnow().isoformat()
                    }
                }
                
        except Exception as e:
            logger.error(f"Failed to get system stats: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
        finally:
            await close_database()
    
    async def reset_failed_messages(self, max_age_hours: int = 24) -> Dict[str, Any]:
        """Reset failed messages for retry."""
        try:
            await init_database()
            
            cutoff_date = datetime.utcnow() - timedelta(hours=max_age_hours)
            
            async with get_db_session() as session:
                # Reset failed messages to pending for retry
                result = await session.execute(
                    update(MessageLog)
                    .where(
                        MessageLog.status == MessageStatus.FAILED,
                        MessageLog.created_at >= cutoff_date,
                        MessageLog.attempts < 3  # Don't retry if already at max attempts
                    )
                    .values(
                        status=MessageStatus.PENDING,
                        last_error=None,
                        updated_at=datetime.utcnow()
                    )
                )
                
                reset_count = result.rowcount
                await session.commit()
                
                return {
                    'success': True,
                    'message': f'Reset {reset_count} failed messages for retry',
                    'reset_count': reset_count
                }
                
        except Exception as e:
            logger.error(f"Failed to reset failed messages: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
        finally:
            await close_database()
