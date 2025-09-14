"""
Data validation utilities for migration and system integrity checks.
"""
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from sqlalchemy import select, func
from src.database import (
    get_db_session, User, Channel, ForwardingMapping, 
    MessageLog, DeduplicationCache, AccessType, ForwardingMode
)

logger = logging.getLogger(__name__)


class DataValidator:
    """Validates data integrity and migration completeness."""
    
    async def validate_migration_integrity(self) -> Dict[str, Any]:
        """Comprehensive validation of migrated data."""
        logger.info("Starting migration integrity validation...")
        
        validation_results = {
            'overall_status': 'unknown',
            'checks': {},
            'warnings': [],
            'errors': [],
            'recommendations': []
        }
        
        # Run all validation checks
        checks = [
            self._check_user_data,
            self._check_channel_data,
            self._check_mapping_data,
            self._check_orphaned_records,
            self._check_access_types,
            self._check_data_consistency
        ]
        
        for check in checks:
            try:
                check_name = check.__name__.replace('_check_', '')
                result = await check()
                validation_results['checks'][check_name] = result
                
                if result.get('errors'):
                    validation_results['errors'].extend(result['errors'])
                if result.get('warnings'):
                    validation_results['warnings'].extend(result['warnings'])
                if result.get('recommendations'):
                    validation_results['recommendations'].extend(result['recommendations'])
                    
            except Exception as e:
                logger.error(f"Validation check {check.__name__} failed: {e}")
                validation_results['errors'].append(f"Check {check.__name__} failed: {str(e)}")
        
        # Determine overall status
        if validation_results['errors']:
            validation_results['overall_status'] = 'failed'
        elif validation_results['warnings']:
            validation_results['overall_status'] = 'warning'
        else:
            validation_results['overall_status'] = 'passed'
        
        logger.info(f"Migration validation completed with status: {validation_results['overall_status']}")
        return validation_results
    
    async def _check_user_data(self) -> Dict[str, Any]:
        """Validate user data integrity."""
        async with get_db_session() as session:
            result = {
                'status': 'passed',
                'errors': [],
                'warnings': [],
                'recommendations': [],
                'stats': {}
            }
            
            # Count users by role
            user_counts = await session.execute(
                select(User.role, func.count(User.id)).group_by(User.role)
            )
            role_counts = dict(user_counts.all())
            result['stats']['users_by_role'] = {role.value: count for role, count in role_counts.items()}
            
            # Check for admin users
            admin_count = role_counts.get('administrator', 0)
            if admin_count == 0:
                result['errors'].append("No administrator users found")
                result['status'] = 'failed'
            
            # Check for duplicate telegram_ids
            duplicate_check = await session.execute(
                select(User.telegram_id, func.count(User.id))
                .group_by(User.telegram_id)
                .having(func.count(User.id) > 1)
            )
            duplicates = duplicate_check.all()
            
            if duplicates:
                result['errors'].append(f"Found {len(duplicates)} duplicate telegram_ids in users")
                result['status'] = 'failed'
            
            return result
    
    async def _check_channel_data(self) -> Dict[str, Any]:
        """Validate channel data integrity."""
        async with get_db_session() as session:
            result = {
                'status': 'passed',
                'errors': [],
                'warnings': [],
                'recommendations': [],
                'stats': {}
            }
            
            # Count channels by access type
            channel_counts = await session.execute(
                select(Channel.access_type, func.count(Channel.id)).group_by(Channel.access_type)
            )
            access_counts = dict(channel_counts.all())
            result['stats']['channels_by_access'] = {access.value: count for access, count in access_counts.items()}
            
            # Check for channels without titles
            no_title_count = await session.execute(
                select(func.count(Channel.id)).where(
                    (Channel.title == '') | (Channel.title.is_(None))
                )
            )
            no_title = no_title_count.scalar()
            
            if no_title > 0:
                result['warnings'].append(f"Found {no_title} channels without titles")
            
            # Check for duplicate telegram_ids
            duplicate_check = await session.execute(
                select(Channel.telegram_id, func.count(Channel.id))
                .group_by(Channel.telegram_id)
                .having(func.count(Channel.id) > 1)
            )
            duplicates = duplicate_check.all()
            
            if duplicates:
                result['errors'].append(f"Found {len(duplicates)} duplicate telegram_ids in channels")
                result['status'] = 'failed'
            
            # Check for inactive channels
            inactive_count = await session.execute(
                select(func.count(Channel.id)).where(Channel.is_active == False)
            )
            inactive = inactive_count.scalar()
            
            if inactive > 0:
                result['warnings'].append(f"Found {inactive} inactive channels")
            
            return result
    
    async def _check_mapping_data(self) -> Dict[str, Any]:
        """Validate forwarding mapping data."""
        async with get_db_session() as session:
            result = {
                'status': 'passed',
                'errors': [],
                'warnings': [],
                'recommendations': [],
                'stats': {}
            }
            
            # Count mappings by mode
            mapping_counts = await session.execute(
                select(ForwardingMapping.mode, func.count(ForwardingMapping.id))
                .group_by(ForwardingMapping.mode)
            )
            mode_counts = dict(mapping_counts.all())
            result['stats']['mappings_by_mode'] = {mode.value: count for mode, count in mode_counts.items()}
            
            # Count enabled vs disabled mappings
            enabled_count = await session.execute(
                select(func.count(ForwardingMapping.id)).where(ForwardingMapping.enabled == True)
            )
            disabled_count = await session.execute(
                select(func.count(ForwardingMapping.id)).where(ForwardingMapping.enabled == False)
            )
            
            result['stats']['enabled_mappings'] = enabled_count.scalar()
            result['stats']['disabled_mappings'] = disabled_count.scalar()
            
            # Check for self-referencing mappings
            self_ref_count = await session.execute(
                select(func.count(ForwardingMapping.id)).where(
                    ForwardingMapping.source_channel_id == ForwardingMapping.dest_channel_id
                )
            )
            self_refs = self_ref_count.scalar()
            
            if self_refs > 0:
                result['errors'].append(f"Found {self_refs} self-referencing mappings")
                result['status'] = 'failed'
            
            # Check for mappings with missing channels
            missing_source = await session.execute(
                select(func.count(ForwardingMapping.id))
                .outerjoin(Channel, ForwardingMapping.source_channel_id == Channel.id)
                .where(Channel.id.is_(None))
            )
            missing_dest = await session.execute(
                select(func.count(ForwardingMapping.id))
                .outerjoin(Channel, ForwardingMapping.dest_channel_id == Channel.id)
                .where(Channel.id.is_(None))
            )
            
            missing_src_count = missing_source.scalar()
            missing_dst_count = missing_dest.scalar()
            
            if missing_src_count > 0:
                result['errors'].append(f"Found {missing_src_count} mappings with missing source channels")
                result['status'] = 'failed'
            
            if missing_dst_count > 0:
                result['errors'].append(f"Found {missing_dst_count} mappings with missing destination channels")
                result['status'] = 'failed'
            
            return result
    
    async def _check_orphaned_records(self) -> Dict[str, Any]:
        """Check for orphaned records without proper relationships."""
        async with get_db_session() as session:
            result = {
                'status': 'passed',
                'errors': [],
                'warnings': [],
                'recommendations': [],
                'stats': {}
            }
            
            # Check for channels without any mappings (neither source nor destination)
            orphaned_channels = await session.execute(
                select(func.count(Channel.id))
                .outerjoin(ForwardingMapping, 
                          (Channel.id == ForwardingMapping.source_channel_id) |
                          (Channel.id == ForwardingMapping.dest_channel_id))
                .where(ForwardingMapping.id.is_(None))
            )
            orphaned_count = orphaned_channels.scalar()
            
            if orphaned_count > 0:
                result['warnings'].append(f"Found {orphaned_count} channels without any mappings")
                result['recommendations'].append("Consider removing unused channels or creating mappings")
            
            # Check for message logs with missing channels
            orphaned_logs = await session.execute(
                select(func.count(MessageLog.id))
                .outerjoin(Channel, MessageLog.source_channel_id == Channel.id)
                .where(Channel.id.is_(None))
            )
            orphaned_log_count = orphaned_logs.scalar()
            
            if orphaned_log_count > 0:
                result['warnings'].append(f"Found {orphaned_log_count} message logs with missing source channels")
            
            result['stats']['orphaned_channels'] = orphaned_count
            result['stats']['orphaned_message_logs'] = orphaned_log_count
            
            return result
    
    async def _check_access_types(self) -> Dict[str, Any]:
        """Validate channel access type assignments."""
        async with get_db_session() as session:
            result = {
                'status': 'passed',
                'errors': [],
                'warnings': [],
                'recommendations': [],
                'stats': {}
            }
            
            # Count channels by access type
            bot_channels = await session.execute(
                select(func.count(Channel.id)).where(Channel.access_type == AccessType.BOT)
            )
            user_channels = await session.execute(
                select(func.count(Channel.id)).where(Channel.access_type == AccessType.USER)
            )
            
            bot_count = bot_channels.scalar()
            user_count = user_channels.scalar()
            
            result['stats']['bot_access_channels'] = bot_count
            result['stats']['user_access_channels'] = user_count
            
            # Warn if all channels are set to USER access (might indicate migration default)
            if user_count > 0 and bot_count == 0:
                result['warnings'].append("All channels are set to USER access type")
                result['recommendations'].append("Review channel access types and update BOT-accessible channels")
            
            # Check for mappings that might have access conflicts
            conflicting_mappings = await session.execute(
                select(func.count(ForwardingMapping.id))
                .join(Channel.source_mappings)
                .join(Channel.dest_mappings)
                .where(
                    (Channel.access_type == AccessType.BOT) &
                    (ForwardingMapping.mode == ForwardingMode.FORWARD)
                )
            )
            
            return result
    
    async def _check_data_consistency(self) -> Dict[str, Any]:
        """Check overall data consistency and relationships."""
        async with get_db_session() as session:
            result = {
                'status': 'passed',
                'errors': [],
                'warnings': [],
                'recommendations': [],
                'stats': {}
            }
            
            # Check for reasonable data volumes
            total_channels = await session.execute(select(func.count(Channel.id)))
            total_mappings = await session.execute(select(func.count(ForwardingMapping.id)))
            total_users = await session.execute(select(func.count(User.id)))
            
            channel_count = total_channels.scalar()
            mapping_count = total_mappings.scalar()
            user_count = total_users.scalar()
            
            result['stats']['total_channels'] = channel_count
            result['stats']['total_mappings'] = mapping_count
            result['stats']['total_users'] = user_count
            
            # Validate reasonable ratios
            if mapping_count == 0 and channel_count > 0:
                result['warnings'].append("Channels exist but no forwarding mappings configured")
                result['recommendations'].append("Create forwarding mappings to enable message forwarding")
            
            if channel_count > 1000:
                result['warnings'].append(f"Large number of channels ({channel_count}) may impact performance")
                result['recommendations'].append("Consider archiving unused channels")
            
            if mapping_count > channel_count * 10:
                result['warnings'].append("Unusually high mapping-to-channel ratio detected")
            
            return result
    
    async def get_system_health_report(self) -> Dict[str, Any]:
        """Generate comprehensive system health report."""
        logger.info("Generating system health report...")
        
        validation_results = await self.validate_migration_integrity()
        
        # Add runtime statistics
        async with get_db_session() as session:
            # Recent message processing stats
            from datetime import timedelta
            recent_cutoff = datetime.utcnow() - timedelta(hours=24)
            
            recent_messages = await session.execute(
                select(MessageLog.status, func.count(MessageLog.id))
                .where(MessageLog.created_at >= recent_cutoff)
                .group_by(MessageLog.status)
            )
            recent_stats = dict(recent_messages.all())
            
            # Deduplication cache stats
            cache_size = await session.execute(select(func.count(DeduplicationCache.id)))
            
            validation_results['runtime_stats'] = {
                'recent_24h_messages': {status.value: count for status, count in recent_stats.items()},
                'deduplication_cache_size': cache_size.scalar(),
                'report_generated_at': datetime.utcnow().isoformat()
            }
        
        return validation_results
