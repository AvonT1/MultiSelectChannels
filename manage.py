#!/usr/bin/env python3
"""
Management script for the Telegram forwarding bot system.
Provides CLI interface for migration, administration, and maintenance tasks.
"""
import asyncio
import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.management import MigrationCommands, AdminCommands
from src.config import settings


async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Telegram Bot Management CLI")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Migration commands
    migration_parser = subparsers.add_parser('migrate', help='Database migration commands')
    migration_subparsers = migration_parser.add_subparsers(dest='migrate_action')
    
    # migrate run
    run_parser = migration_subparsers.add_parser('run', help='Run SQLite to PostgreSQL migration')
    run_parser.add_argument('--sqlite-path', help='Path to SQLite database file')
    
    # migrate validate
    migration_subparsers.add_parser('validate', help='Validate migration integrity')
    
    # migrate status
    migration_subparsers.add_parser('status', help='Show migration status')
    
    # migrate health
    migration_subparsers.add_parser('health', help='Generate system health report')
    
    # migrate cleanup
    migration_subparsers.add_parser('cleanup', help='Clean up migration data')
    
    # Admin commands
    admin_parser = subparsers.add_parser('admin', help='Administrative commands')
    admin_subparsers = admin_parser.add_subparsers(dest='admin_action')
    
    # admin user
    user_parser = admin_subparsers.add_parser('user', help='User management')
    user_subparsers = user_parser.add_subparsers(dest='user_action')
    
    create_user_parser = user_subparsers.add_parser('create-admin', help='Create admin user')
    create_user_parser.add_argument('telegram_id', type=int, help='Telegram user ID')
    create_user_parser.add_argument('--username', help='Username (optional)')
    
    list_users_parser = user_subparsers.add_parser('list', help='List users')
    list_users_parser.add_argument('--role', choices=['user', 'administrator'], help='Filter by role')
    
    # admin channel
    channel_parser = admin_subparsers.add_parser('channel', help='Channel management')
    channel_subparsers = channel_parser.add_subparsers(dest='channel_action')
    
    add_channel_parser = channel_subparsers.add_parser('add', help='Add channel')
    add_channel_parser.add_argument('telegram_id', type=int, help='Channel Telegram ID')
    add_channel_parser.add_argument('--title', help='Channel title')
    add_channel_parser.add_argument('--access-type', choices=['bot', 'user'], default='user', help='Access type')
    
    remove_channel_parser = channel_subparsers.add_parser('remove', help='Remove channel')
    remove_channel_parser.add_argument('telegram_id', type=int, help='Channel Telegram ID')
    
    activate_channel_parser = channel_subparsers.add_parser('activate', help='Activate channel')
    activate_channel_parser.add_argument('telegram_id', type=int, help='Channel Telegram ID')
    
    deactivate_channel_parser = channel_subparsers.add_parser('deactivate', help='Deactivate channel')
    deactivate_channel_parser.add_argument('telegram_id', type=int, help='Channel Telegram ID')
    
    # admin mapping
    mapping_parser = admin_subparsers.add_parser('mapping', help='Mapping management')
    mapping_parser.add_argument('source_id', type=int, help='Source channel ID')
    mapping_parser.add_argument('dest_id', type=int, help='Destination channel ID')
    mapping_parser.add_argument('--mode', choices=['forward', 'copy'], default='forward', help='Forwarding mode')
    mapping_parser.add_argument('--disabled', action='store_true', help='Create mapping as disabled')
    
    # admin stats
    admin_subparsers.add_parser('stats', help='Show system statistics')
    
    # admin cleanup
    cleanup_parser = admin_subparsers.add_parser('cleanup', help='Clean up old data')
    cleanup_parser.add_argument('--days', type=int, default=30, help='Days old to clean up (default: 30)')
    
    # admin reset
    reset_parser = admin_subparsers.add_parser('reset-failed', help='Reset failed messages for retry')
    reset_parser.add_argument('--hours', type=int, default=24, help='Max age in hours (default: 24)')
    
    # Parse arguments
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == 'migrate':
            await handle_migration_commands(args)
        elif args.command == 'admin':
            await handle_admin_commands(args)
        else:
            print(f"Unknown command: {args.command}")
            return 1
            
    except KeyboardInterrupt:
        print("\n⏹️  Operation cancelled by user")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    
    return 0


async def handle_migration_commands(args):
    """Handle migration-related commands."""
    migration_commands = MigrationCommands()
    
    if args.migrate_action == 'run':
        print("🚀 Starting migration from SQLite to PostgreSQL...")
        result = await migration_commands.migrate_from_sqlite(args.sqlite_path)
        
        if result['success']:
            print("✅ Migration completed successfully!")
            
            if 'validation' in result:
                validation = result['validation']
                print(f"📊 Validation status: {validation['overall_status']}")
                
                if validation.get('warnings'):
                    print("⚠️  Warnings:")
                    for warning in validation['warnings']:
                        print(f"   - {warning}")
                
                if validation.get('recommendations'):
                    print("💡 Recommendations:")
                    for rec in validation['recommendations']:
                        print(f"   - {rec}")
        else:
            print(f"❌ Migration failed: {result.get('error', 'Unknown error')}")
    
    elif args.migrate_action == 'validate':
        print("🔍 Running migration validation...")
        result = await migration_commands.validate_migration()
        
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
    
    elif args.migrate_action == 'status':
        print("📈 Getting migration status...")
        status = await migration_commands.get_migration_status()
        
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
    
    elif args.migrate_action == 'health':
        print("🏥 Generating system health report...")
        result = await migration_commands.generate_health_report()
        
        print(f"📊 Overall status: {result['overall_status']}")
        
        if result.get('errors'):
            print("❌ Errors:")
            for error in result['errors']:
                print(f"   - {error}")
        
        if result.get('warnings'):
            print("⚠️  Warnings:")
            for warning in result['warnings']:
                print(f"   - {warning}")
    
    elif args.migrate_action == 'cleanup':
        print("🧹 Cleaning up migration data...")
        result = await migration_commands.cleanup_migration_data()
        
        if result['success']:
            print("✅ Cleanup completed successfully!")
        else:
            print(f"❌ Cleanup failed: {result.get('error', 'Unknown error')}")


async def handle_admin_commands(args):
    """Handle administrative commands."""
    admin_commands = AdminCommands()
    
    if args.admin_action == 'user':
        if args.user_action == 'create-admin':
            print(f"👤 Creating admin user {args.telegram_id}...")
            result = await admin_commands.create_admin_user(args.telegram_id, args.username)
            
            if result['success']:
                print(f"✅ {result['message']}")
            else:
                print(f"❌ {result.get('message', result.get('error', 'Unknown error'))}")
        
        elif args.user_action == 'list':
            from src.database.models import UserRole
            role_filter = UserRole(args.role) if args.role else None
            
            print("👥 Listing users...")
            result = await admin_commands.list_users(role_filter)
            
            if result['success']:
                print(f"Found {result['total_count']} users:")
                for user in result['users']:
                    print(f"   - {user['telegram_id']} ({user['role']}) - {user.get('username', 'No username')}")
            else:
                print(f"❌ {result.get('error', 'Unknown error')}")
    
    elif args.admin_action == 'channel':
        if args.channel_action == 'add':
            print(f"📺 Adding channel {args.telegram_id}...")
            result = await admin_commands.manage_channel(
                'add', args.telegram_id,
                title=args.title,
                access_type=args.access_type
            )
            
            if result['success']:
                print(f"✅ {result['message']}")
            else:
                print(f"❌ {result.get('message', result.get('error', 'Unknown error'))}")
        
        elif args.channel_action == 'remove':
            print(f"🗑️  Removing channel {args.telegram_id}...")
            result = await admin_commands.manage_channel('remove', args.telegram_id)
            
            if result['success']:
                print(f"✅ {result['message']}")
            else:
                print(f"❌ {result.get('message', result.get('error', 'Unknown error'))}")
        
        elif args.channel_action == 'activate':
            print(f"✅ Activating channel {args.telegram_id}...")
            result = await admin_commands.manage_channel('activate', args.telegram_id)
            
            if result['success']:
                print(f"✅ {result['message']}")
            else:
                print(f"❌ {result.get('message', result.get('error', 'Unknown error'))}")
        
        elif args.channel_action == 'deactivate':
            print(f"⏸️  Deactivating channel {args.telegram_id}...")
            result = await admin_commands.manage_channel('deactivate', args.telegram_id)
            
            if result['success']:
                print(f"✅ {result['message']}")
            else:
                print(f"❌ {result.get('message', result.get('error', 'Unknown error'))}")
    
    elif args.admin_action == 'mapping':
        print(f"🔗 Creating mapping {args.source_id} -> {args.dest_id}...")
        result = await admin_commands.create_mapping(
            args.source_id, args.dest_id,
            mode=args.mode,
            enabled=not args.disabled
        )
        
        if result['success']:
            print(f"✅ {result['message']}")
        else:
            print(f"❌ {result.get('message', result.get('error', 'Unknown error'))}")
    
    elif args.admin_action == 'stats':
        print("📊 Getting system statistics...")
        result = await admin_commands.get_system_stats()
        
        if result['success']:
            stats = result['stats']
            print(f"   Total Users: {stats['total_users']}")
            print(f"   Total Channels: {stats['total_channels']}")
            print(f"   Total Mappings: {stats['total_mappings']}")
            print(f"   Active Mappings: {stats['active_mappings']}")
            
            if stats.get('recent_24h_messages'):
                print("   Recent 24h Messages:")
                for status, count in stats['recent_24h_messages'].items():
                    print(f"     {status}: {count}")
        else:
            print(f"❌ {result.get('error', 'Unknown error')}")
    
    elif args.admin_action == 'cleanup':
        print(f"🧹 Cleaning up data older than {args.days} days...")
        result = await admin_commands.cleanup_old_data(args.days)
        
        if result['success']:
            print(f"✅ {result['message']}")
            stats = result['stats']
            print(f"   Message logs deleted: {stats['message_logs_deleted']}")
            print(f"   Dedup cache deleted: {stats['dedup_cache_deleted']}")
        else:
            print(f"❌ {result.get('error', 'Unknown error')}")
    
    elif args.admin_action == 'reset-failed':
        print(f"🔄 Resetting failed messages from last {args.hours} hours...")
        result = await admin_commands.reset_failed_messages(args.hours)
        
        if result['success']:
            print(f"✅ {result['message']}")
        else:
            print(f"❌ {result.get('error', 'Unknown error')}")


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
