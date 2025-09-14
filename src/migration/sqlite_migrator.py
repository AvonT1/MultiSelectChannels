"""
SQLite to PostgreSQL migration utility.
Handles the transition from the existing SQLite database to the new PostgreSQL schema.
"""
import logging
import sqlite3
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from src.database import (
    get_db_session, User, Channel, ForwardingMapping, 
    LegacyFolder, LegacyList, AccessType, ForwardingMode, UserRole
)
from src.config import settings

logger = logging.getLogger(__name__)


class SQLiteMigrator:
    """Handles migration from SQLite database to PostgreSQL schema."""
    
    def __init__(self, sqlite_db_path: str = "userbot.db"):
        self.sqlite_db_path = sqlite_db_path
        self.migration_stats = {
            'folders_migrated': 0,
            'lists_migrated': 0,
            'sources_migrated': 0,
            'destinations_migrated': 0,
            'mappings_created': 0,
            'errors': []
        }
    
    async def migrate_all_data(self) -> Dict[str, Any]:
        """Migrate all data from SQLite to PostgreSQL."""
        logger.info("Starting complete SQLite to PostgreSQL migration...")
        
        if not Path(self.sqlite_db_path).exists():
            raise FileNotFoundError(f"SQLite database not found: {self.sqlite_db_path}")
        
        try:
            # Step 1: Create admin user
            await self._create_admin_user()
            
            # Step 2: Migrate legacy data to temporary tables
            await self._migrate_legacy_folders()
            await self._migrate_legacy_lists()
            
            # Step 3: Transform legacy data to new schema
            await self._transform_to_new_schema()
            
            # Step 4: Create forwarding mappings
            await self._create_forwarding_mappings()
            
            # Step 5: Validate migration
            await self._validate_migration()
            
            logger.info("Migration completed successfully", extra=self.migration_stats)
            return {
                'success': True,
                'stats': self.migration_stats,
                'message': 'Migration completed successfully'
            }
            
        except Exception as e:
            logger.error(f"Migration failed: {e}", exc_info=True)
            self.migration_stats['errors'].append(str(e))
            return {
                'success': False,
                'stats': self.migration_stats,
                'error': str(e)
            }
    
    async def _create_admin_user(self) -> None:
        """Create admin user from settings."""
        if not settings.admin_ids:
            logger.warning("No admin IDs configured, skipping admin user creation")
            return
        
        async with get_db_session() as session:
            for admin_id in settings.admin_ids:
                # Check if user already exists
                result = await session.execute(
                    select(User).where(User.telegram_id == admin_id)
                )
                existing_user = result.scalar_one_or_none()
                
                if not existing_user:
                    admin_user = User(
                        telegram_id=admin_id,
                        role=UserRole.ADMINISTRATOR
                    )
                    session.add(admin_user)
                    logger.info(f"Created admin user: {admin_id}")
            
            await session.commit()
    
    async def _migrate_legacy_folders(self) -> None:
        """Migrate folders from SQLite to legacy tables."""
        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT id, name FROM list_folders ORDER BY id")
            folders = cursor.fetchall()
            
            async with get_db_session() as session:
                for folder_id, name in folders:
                    legacy_folder = LegacyFolder(
                        id=folder_id,
                        name=name,
                        migrated=False
                    )
                    
                    # Use upsert to handle duplicates
                    stmt = insert(LegacyFolder).values(
                        id=folder_id,
                        name=name,
                        migrated=False
                    )
                    stmt = stmt.on_conflict_do_nothing(index_elements=['id'])
                    await session.execute(stmt)
                    
                    self.migration_stats['folders_migrated'] += 1
                
                await session.commit()
                logger.info(f"Migrated {len(folders)} folders to legacy tables")
                
        except sqlite3.Error as e:
            logger.error(f"Error migrating folders: {e}")
            self.migration_stats['errors'].append(f"Folder migration error: {e}")
        finally:
            conn.close()
    
    async def _migrate_legacy_lists(self) -> None:
        """Migrate forwarding lists from SQLite to legacy tables."""
        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT id, name, description, folder_id, notifications_enabled 
                FROM forwarding_lists ORDER BY id
            """)
            lists = cursor.fetchall()
            
            async with get_db_session() as session:
                for list_id, name, description, folder_id, notifications_enabled in lists:
                    legacy_list = LegacyList(
                        id=list_id,
                        name=name,
                        description=description,
                        folder_id=folder_id,
                        notifications_enabled=bool(notifications_enabled),
                        migrated=False
                    )
                    
                    # Use upsert to handle duplicates
                    stmt = insert(LegacyList).values(
                        id=list_id,
                        name=name,
                        description=description,
                        folder_id=folder_id,
                        notifications_enabled=bool(notifications_enabled),
                        migrated=False
                    )
                    stmt = stmt.on_conflict_do_nothing(index_elements=['id'])
                    await session.execute(stmt)
                    
                    self.migration_stats['lists_migrated'] += 1
                
                await session.commit()
                logger.info(f"Migrated {len(lists)} lists to legacy tables")
                
        except sqlite3.Error as e:
            logger.error(f"Error migrating lists: {e}")
            self.migration_stats['errors'].append(f"List migration error: {e}")
        finally:
            conn.close()
    
    async def _transform_to_new_schema(self) -> None:
        """Transform legacy data to new Channel schema."""
        # Get source and destination channels from SQLite
        source_channels = await self._get_source_channels()
        dest_channels = await self._get_destination_channels()
        
        # Combine and deduplicate channels
        all_channels = {}
        
        for channel_id, title in source_channels:
            all_channels[channel_id] = {
                'telegram_id': channel_id,
                'title': title,
                'is_source': True,
                'is_destination': False
            }
        
        for channel_id, title in dest_channels:
            if channel_id in all_channels:
                all_channels[channel_id]['is_destination'] = True
            else:
                all_channels[channel_id] = {
                    'telegram_id': channel_id,
                    'title': title or f"Channel {channel_id}",
                    'is_source': False,
                    'is_destination': True
                }
        
        # Create Channel records
        async with get_db_session() as session:
            # Get first admin user
            admin_result = await session.execute(
                select(User).where(User.role == UserRole.ADMINISTRATOR).limit(1)
            )
            admin_user = admin_result.scalar_one()
            
            for channel_data in all_channels.values():
                # Check if channel already exists
                result = await session.execute(
                    select(Channel).where(Channel.telegram_id == channel_data['telegram_id'])
                )
                existing_channel = result.scalar_one_or_none()
                
                if not existing_channel:
                    # Determine access type (default to USER for better compatibility)
                    access_type = AccessType.USER
                    
                    channel = Channel(
                        telegram_id=channel_data['telegram_id'],
                        title=channel_data['title'],
                        access_type=access_type,
                        added_by_user_id=admin_user.id,
                        metadata={
                            'migrated_from_sqlite': True,
                            'was_source': channel_data['is_source'],
                            'was_destination': channel_data['is_destination']
                        }
                    )
                    session.add(channel)
            
            await session.commit()
            logger.info(f"Created {len(all_channels)} channel records")
    
    async def _create_forwarding_mappings(self) -> None:
        """Create ForwardingMapping records from SQLite data."""
        mappings = await self._get_forwarding_mappings()
        
        async with get_db_session() as session:
            for source_id, dest_id, list_name in mappings:
                # Get source and destination channels
                source_result = await session.execute(
                    select(Channel).where(Channel.telegram_id == source_id)
                )
                source_channel = source_result.scalar_one_or_none()
                
                dest_result = await session.execute(
                    select(Channel).where(Channel.telegram_id == dest_id)
                )
                dest_channel = dest_result.scalar_one_or_none()
                
                if source_channel and dest_channel:
                    # Check if mapping already exists
                    existing_result = await session.execute(
                        select(ForwardingMapping).where(
                            ForwardingMapping.source_channel_id == source_channel.id,
                            ForwardingMapping.dest_channel_id == dest_channel.id
                        )
                    )
                    existing_mapping = existing_result.scalar_one_or_none()
                    
                    if not existing_mapping:
                        mapping = ForwardingMapping(
                            source_channel_id=source_channel.id,
                            dest_channel_id=dest_channel.id,
                            mode=ForwardingMode.FORWARD,  # Default mode
                            enabled=True
                        )
                        session.add(mapping)
                        self.migration_stats['mappings_created'] += 1
                else:
                    error_msg = f"Missing channels for mapping: {source_id} -> {dest_id}"
                    logger.warning(error_msg)
                    self.migration_stats['errors'].append(error_msg)
            
            await session.commit()
            logger.info(f"Created {self.migration_stats['mappings_created']} forwarding mappings")
    
    async def _get_source_channels(self) -> List[tuple]:
        """Get source channels from SQLite."""
        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT DISTINCT source_chat_id, source_chat_title 
                FROM list_sources 
                ORDER BY source_chat_id
            """)
            return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error getting source channels: {e}")
            return []
        finally:
            conn.close()
    
    async def _get_destination_channels(self) -> List[tuple]:
        """Get destination channels from SQLite."""
        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT DISTINCT destination_chat_id, NULL as title
                FROM list_destinations 
                ORDER BY destination_chat_id
            """)
            return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error getting destination channels: {e}")
            return []
        finally:
            conn.close()
    
    async def _get_forwarding_mappings(self) -> List[tuple]:
        """Get forwarding mappings from SQLite."""
        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT DISTINCT 
                    ls.source_chat_id,
                    ld.destination_chat_id,
                    fl.name as list_name
                FROM list_sources ls
                JOIN forwarding_lists fl ON ls.list_id = fl.id
                JOIN list_destinations ld ON ls.list_id = ld.list_id
                ORDER BY ls.source_chat_id, ld.destination_chat_id
            """)
            return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error getting forwarding mappings: {e}")
            return []
        finally:
            conn.close()
    
    async def _validate_migration(self) -> None:
        """Validate the migration results."""
        async with get_db_session() as session:
            # Count migrated records
            from sqlalchemy import func
            
            channel_count = await session.execute(select(func.count(Channel.id)))
            mapping_count = await session.execute(select(func.count(ForwardingMapping.id)))
            user_count = await session.execute(select(func.count(User.id)))
            
            validation_stats = {
                'channels': channel_count.scalar(),
                'mappings': mapping_count.scalar(),
                'users': user_count.scalar()
            }
            
            logger.info("Migration validation", extra=validation_stats)
            
            if validation_stats['channels'] == 0:
                self.migration_stats['errors'].append("No channels were migrated")
            
            if validation_stats['users'] == 0:
                self.migration_stats['errors'].append("No users were created")
    
    async def get_migration_status(self) -> Dict[str, Any]:
        """Get current migration status."""
        return {
            'stats': self.migration_stats,
            'sqlite_exists': Path(self.sqlite_db_path).exists(),
            'timestamp': datetime.utcnow().isoformat()
        }
