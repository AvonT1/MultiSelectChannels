"""
Migration management commands for database transitions and data validation.
"""
import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime

from src.migration import SQLiteMigrator, DataValidator
from src.database import init_database, close_database
from src.config import settings

logger = logging.getLogger(__name__)


class MigrationCommands:
    """Management commands for database migration operations."""
    
    def __init__(self):
        self.migrator = SQLiteMigrator()
        self.validator = DataValidator()
    
    async def migrate_from_sqlite(self, sqlite_path: Optional[str] = None) -> Dict[str, Any]:
        """Execute complete migration from SQLite to PostgreSQL."""
        logger.info("Starting SQLite to PostgreSQL migration...")
        
        try:
            # Initialize database connection
            await init_database()
            
            # Use provided path or default
            if sqlite_path:
                self.migrator.sqlite_db_path = sqlite_path
            
            # Execute migration
            result = await self.migrator.migrate_all_data()
            
            if result['success']:
                logger.info("Migration completed successfully")
                
                # Run validation
                validation_result = await self.validator.validate_migration_integrity()
                result['validation'] = validation_result
                
                if validation_result['overall_status'] == 'failed':
                    logger.warning("Migration completed but validation failed")
                    result['warnings'] = ['Migration completed but validation detected issues']
            
            return result
            
        except Exception as e:
            logger.error(f"Migration failed: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
        finally:
            await close_database()
    
    async def validate_migration(self) -> Dict[str, Any]:
        """Validate migration integrity and data consistency."""
        logger.info("Running migration validation...")
        
        try:
            await init_database()
            result = await self.validator.validate_migration_integrity()
            
            logger.info(f"Validation completed with status: {result['overall_status']}")
            return result
            
        except Exception as e:
            logger.error(f"Validation failed: {e}", exc_info=True)
            return {
                'overall_status': 'error',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
        finally:
            await close_database()
    
    async def get_migration_status(self) -> Dict[str, Any]:
        """Get current migration status and statistics."""
        try:
            await init_database()
            
            # Get basic migration info
            status = await self.migrator.get_migration_status()
            
            # Add database statistics
            from sqlalchemy import select, func
            from src.database import get_db_session, User, Channel, ForwardingMapping
            
            async with get_db_session() as session:
                user_count = await session.execute(select(func.count(User.id)))
                channel_count = await session.execute(select(func.count(Channel.id)))
                mapping_count = await session.execute(select(func.count(ForwardingMapping.id)))
                
                status['database_stats'] = {
                    'users': user_count.scalar(),
                    'channels': channel_count.scalar(),
                    'mappings': mapping_count.scalar()
                }
            
            return status
            
        except Exception as e:
            logger.error(f"Failed to get migration status: {e}")
            return {
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
        finally:
            await close_database()
    
    async def generate_health_report(self) -> Dict[str, Any]:
        """Generate comprehensive system health report."""
        logger.info("Generating system health report...")
        
        try:
            await init_database()
            report = await self.validator.get_system_health_report()
            
            logger.info("Health report generated successfully")
            return report
            
        except Exception as e:
            logger.error(f"Failed to generate health report: {e}", exc_info=True)
            return {
                'overall_status': 'error',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
        finally:
            await close_database()
    
    async def cleanup_migration_data(self) -> Dict[str, Any]:
        """Clean up temporary migration data and optimize database."""
        logger.info("Starting migration cleanup...")
        
        try:
            await init_database()
            
            from src.database import get_db_session, LegacyFolder, LegacyList
            from sqlalchemy import delete
            
            async with get_db_session() as session:
                # Mark legacy data as migrated
                await session.execute(
                    delete(LegacyFolder).where(LegacyFolder.migrated == True)
                )
                await session.execute(
                    delete(LegacyList).where(LegacyList.migrated == True)
                )
                
                await session.commit()
            
            # Run database maintenance
            cleanup_stats = await self._run_database_maintenance()
            
            return {
                'success': True,
                'message': 'Migration cleanup completed',
                'stats': cleanup_stats,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
        finally:
            await close_database()
    
    async def _run_database_maintenance(self) -> Dict[str, Any]:
        """Run database maintenance operations."""
        from src.database import get_db_session
        
        async with get_db_session() as session:
            # Run VACUUM and ANALYZE equivalent operations
            await session.execute("VACUUM ANALYZE;")
            
            # Update table statistics
            await session.execute("ANALYZE;")
            
            return {
                'maintenance_completed': True,
                'operations': ['vacuum', 'analyze']
            }


# CLI-style command functions for direct execution
async def run_migration(sqlite_path: Optional[str] = None):
    """CLI command to run migration."""
    commands = MigrationCommands()
    result = await commands.migrate_from_sqlite(sqlite_path)
    
    if result['success']:
        print("✅ Migration completed successfully!")
        if 'validation' in result:
            validation = result['validation']
            print(f"📊 Validation status: {validation['overall_status']}")
            if validation['warnings']:
                print("⚠️  Warnings:")
                for warning in validation['warnings']:
                    print(f"   - {warning}")
    else:
        print(f"❌ Migration failed: {result.get('error', 'Unknown error')}")
    
    return result


async def run_validation():
    """CLI command to run validation."""
    commands = MigrationCommands()
    result = await commands.validate_migration()
    
    print(f"📊 Validation status: {result['overall_status']}")
    
    if result.get('errors'):
        print("❌ Errors:")
        for error in result['errors']:
            print(f"   - {error}")
    
    if result.get('warnings'):
        print("⚠️  Warnings:")
        for warning in result['warnings']:
            print(f"   - {warning}")
    
    if result.get('recommendations'):
        print("💡 Recommendations:")
        for rec in result['recommendations']:
            print(f"   - {rec}")
    
    return result


async def show_status():
    """CLI command to show migration status."""
    commands = MigrationCommands()
    status = await commands.get_migration_status()
    
    print("📈 Migration Status:")
    if 'database_stats' in status:
        stats = status['database_stats']
        print(f"   Users: {stats['users']}")
        print(f"   Channels: {stats['channels']}")
        print(f"   Mappings: {stats['mappings']}")
    
    if 'stats' in status:
        migration_stats = status['stats']
        print(f"   Folders migrated: {migration_stats.get('folders_migrated', 0)}")
        print(f"   Lists migrated: {migration_stats.get('lists_migrated', 0)}")
        print(f"   Mappings created: {migration_stats.get('mappings_created', 0)}")
    
    return status


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m src.management.migration_commands <command>")
        print("Commands: migrate, validate, status, health")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "migrate":
        sqlite_path = sys.argv[2] if len(sys.argv) > 2 else None
        asyncio.run(run_migration(sqlite_path))
    elif command == "validate":
        asyncio.run(run_validation())
    elif command == "status":
        asyncio.run(show_status())
    elif command == "health":
        commands = MigrationCommands()
        result = asyncio.run(commands.generate_health_report())
        print(f"🏥 Health Report: {result['overall_status']}")
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
