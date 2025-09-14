"""
Legacy Handler Migrator

This module provides backward compatibility by wrapping existing Pyrogram-based
handlers to work with the new python-telegram-bot architecture.
"""

import asyncio
from typing import Optional, Dict, Any, List
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
import structlog

from ..database.models import User, Channel, ForwardingMapping
from ..database.connection import get_session
from ..config.settings import settings
from ..core.forwarding_engine import ForwardingEngine
from ..clients.client_factory import ClientFactory

logger = structlog.get_logger(__name__)


class LegacyHandlerMigrator:
    """
    Migrates legacy Pyrogram handlers to work with python-telegram-bot.
    
    This class acts as a bridge between the old handler logic and the new
    architecture, allowing gradual migration while preserving functionality.
    """
    
    def __init__(self, client_factory: ClientFactory, forwarding_engine: ForwardingEngine):
        self.client_factory = client_factory
        self.forwarding_engine = forwarding_engine
        self.logger = logger.bind(component="legacy_migrator")
        
        # Legacy state tracking (simplified version of old logic)
        self.user_states: Dict[int, Dict[str, Any]] = {}
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle callback queries using legacy logic patterns.
        
        This method processes inline keyboard callbacks and routes them to
        appropriate legacy handler functions.
        """
        query = update.callback_query
        user = update.effective_user
        
        if not query.data:
            return
        
        try:
            # Parse callback data (legacy format)
            callback_parts = query.data.split('_')
            action = callback_parts[0] if callback_parts else ""
            
            self.logger.info("Processing legacy callback", 
                           action=action, 
                           user_id=user.id,
                           callback_data=query.data)
            
            # Route to appropriate legacy handler
            if action == "main":
                await self._handle_main_menu_legacy(update, context)
            elif action == "folders":
                await self._handle_folders_legacy(update, context)
            elif action == "lists":
                await self._handle_lists_legacy(update, context)
            elif action == "channels":
                await self._handle_channels_legacy(update, context)
            elif action == "mappings":
                await self._handle_mappings_legacy(update, context)
            elif action == "settings":
                await self._handle_settings_legacy(update, context)
            elif action == "admin":
                await self._handle_admin_legacy(update, context)
            else:
                # Unknown callback, provide fallback
                await query.edit_message_text(
                    "⚠️ This feature is being migrated to the new system. Please use /menu for available options.",
                    reply_markup=self._get_back_to_menu_keyboard()
                )
                
        except Exception as e:
            self.logger.error("Error in legacy callback handler", error=str(e), exc_info=e)
            await query.edit_message_text(
                "❌ An error occurred. Please try again or use /menu.",
                reply_markup=self._get_back_to_menu_keyboard()
            )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle text messages using legacy logic patterns.
        
        This method processes user text input and routes it based on
        current user state or message content.
        """
        user = update.effective_user
        message_text = update.message.text
        
        if not user or not message_text:
            return
        
        try:
            self.logger.info("Processing legacy message", 
                           user_id=user.id, 
                           message_length=len(message_text))
            
            # Check if user has an active state
            user_state = self.user_states.get(user.id, {})
            
            if user_state.get('awaiting_input'):
                await self._handle_user_input_legacy(update, context, user_state)
            else:
                # No active state, check for commands or channel references
                if message_text.startswith('/'):
                    await self._handle_command_legacy(update, context)
                elif message_text.startswith('@') or message_text.startswith('https://t.me/'):
                    await self._handle_channel_reference_legacy(update, context)
                else:
                    # General message, provide help
                    await update.message.reply_text(
                        "ℹ️ I didn't understand that. Use /menu to see available options or /help for commands."
                    )
                    
        except Exception as e:
            self.logger.error("Error in legacy message handler", error=str(e), exc_info=e)
            await update.message.reply_text(
                "❌ An error occurred while processing your message. Please try again."
            )
    
    async def _handle_main_menu_legacy(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle main menu navigation (legacy style)."""
        query = update.callback_query
        
        keyboard = [
            [
                InlineKeyboardButton("📁 Folders", callback_data="folders_list"),
                InlineKeyboardButton("📋 Lists", callback_data="lists_list")
            ],
            [
                InlineKeyboardButton("📺 Channels", callback_data="channels_list"),
                InlineKeyboardButton("🔗 Mappings", callback_data="mappings_list")
            ],
            [
                InlineKeyboardButton("⚙️ Settings", callback_data="settings_main"),
                InlineKeyboardButton("📊 Status", callback_data="status_system")
            ]
        ]
        
        await query.edit_message_text(
            "📋 **Main Menu**\n\nChoose an option to manage your forwarding setup:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    async def _handle_folders_legacy(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle folder management (legacy style)."""
        query = update.callback_query
        
        # Get user's folders from database
        async with get_session() as session:
            # TODO: Implement folder listing from new database schema
            folders = []  # Placeholder
        
        if not folders:
            keyboard = [
                [InlineKeyboardButton("➕ Create Folder", callback_data="folders_create")],
                [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
            ]
            
            await query.edit_message_text(
                "📁 **Folders**\n\nNo folders found. Create your first folder to organize your forwarding lists.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        else:
            # Show existing folders
            keyboard = []
            for folder in folders[:10]:  # Limit to 10 for display
                keyboard.append([
                    InlineKeyboardButton(f"📁 {folder.name}", callback_data=f"folders_view_{folder.id}")
                ])
            
            keyboard.extend([
                [InlineKeyboardButton("➕ Create Folder", callback_data="folders_create")],
                [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
            ])
            
            await query.edit_message_text(
                f"📁 **Folders** ({len(folders)})\n\nSelect a folder to manage:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
    
    async def _handle_lists_legacy(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle list management (legacy style)."""
        query = update.callback_query
        
        keyboard = [
            [InlineKeyboardButton("📋 View Lists", callback_data="lists_view")],
            [InlineKeyboardButton("➕ Create List", callback_data="lists_create")],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(
            "📋 **Lists Management**\n\nManage your forwarding lists:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    async def _handle_channels_legacy(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle channel management (legacy style)."""
        query = update.callback_query
        
        # Get channels from database
        async with get_session() as session:
            from sqlalchemy import select
            result = await session.execute(select(Channel).limit(10))
            channels = result.scalars().all()
        
        keyboard = []
        
        if channels:
            for channel in channels:
                status_emoji = "✅" if channel.is_active else "❌"
                keyboard.append([
                    InlineKeyboardButton(
                        f"{status_emoji} {channel.title or f'ID: {channel.telegram_id}'}", 
                        callback_data=f"channels_view_{channel.id}"
                    )
                ])
        
        keyboard.extend([
            [InlineKeyboardButton("➕ Add Channel", callback_data="channels_add")],
            [InlineKeyboardButton("🔍 Search Channels", callback_data="channels_search")],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ])
        
        channel_count = len(channels)
        await query.edit_message_text(
            f"📺 **Channels** ({channel_count})\n\nManage your source and destination channels:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    async def _handle_mappings_legacy(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle mapping management (legacy style)."""
        query = update.callback_query
        
        # Get mappings from database
        async with get_session() as session:
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload
            result = await session.execute(
                select(ForwardingMapping)
                .options(selectinload(ForwardingMapping.source_channel))
                .options(selectinload(ForwardingMapping.destination_channel))
                .limit(10)
            )
            mappings = result.scalars().all()
        
        keyboard = []
        
        if mappings:
            for mapping in mappings:
                status_emoji = "✅" if mapping.enabled else "❌"
                source_name = mapping.source_channel.title or f"ID: {mapping.source_channel.telegram_id}"
                dest_name = mapping.destination_channel.title or f"ID: {mapping.destination_channel.telegram_id}"
                
                keyboard.append([
                    InlineKeyboardButton(
                        f"{status_emoji} {source_name} → {dest_name}", 
                        callback_data=f"mappings_view_{mapping.id}"
                    )
                ])
        
        keyboard.extend([
            [InlineKeyboardButton("➕ Create Mapping", callback_data="mappings_create")],
            [InlineKeyboardButton("📊 Statistics", callback_data="mappings_stats")],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ])
        
        mapping_count = len(mappings)
        await query.edit_message_text(
            f"🔗 **Forwarding Mappings** ({mapping_count})\n\nManage your forwarding rules:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    async def _handle_settings_legacy(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle settings management (legacy style)."""
        query = update.callback_query
        
        keyboard = [
            [
                InlineKeyboardButton("🔧 General", callback_data="settings_general"),
                InlineKeyboardButton("🚀 Performance", callback_data="settings_performance")
            ],
            [
                InlineKeyboardButton("🔐 Security", callback_data="settings_security"),
                InlineKeyboardButton("📝 Logging", callback_data="settings_logging")
            ],
            [
                InlineKeyboardButton("💾 Backup", callback_data="settings_backup"),
                InlineKeyboardButton("🔄 Reset", callback_data="settings_reset")
            ],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(
            "⚙️ **Settings**\n\nConfigure your bot settings:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    async def _handle_admin_legacy(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle admin panel (legacy style)."""
        query = update.callback_query
        
        keyboard = [
            [
                InlineKeyboardButton("👥 Users", callback_data="admin_users"),
                InlineKeyboardButton("📊 Stats", callback_data="admin_stats")
            ],
            [
                InlineKeyboardButton("🔧 System", callback_data="admin_system"),
                InlineKeyboardButton("📋 Logs", callback_data="admin_logs")
            ],
            [
                InlineKeyboardButton("🗄️ Database", callback_data="admin_database"),
                InlineKeyboardButton("🔄 Maintenance", callback_data="admin_maintenance")
            ],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(
            "🔧 **Admin Panel**\n\nSystem administration tools:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    async def _handle_user_input_legacy(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_state: Dict[str, Any]) -> None:
        """Handle user input based on legacy state patterns."""
        user = update.effective_user
        message_text = update.message.text
        
        input_type = user_state.get('input_type')
        
        if input_type == 'channel_username':
            await self._process_channel_input_legacy(update, context, message_text)
        elif input_type == 'folder_name':
            await self._process_folder_input_legacy(update, context, message_text)
        elif input_type == 'list_name':
            await self._process_list_input_legacy(update, context, message_text)
        else:
            # Unknown input type, clear state
            self.user_states.pop(user.id, None)
            await update.message.reply_text(
                "❌ Unknown input type. Please start over using /menu."
            )
    
    async def _process_channel_input_legacy(self, update: Update, context: ContextTypes.DEFAULT_TYPE, channel_input: str) -> None:
        """Process channel input (username or URL)."""
        user = update.effective_user
        
        # Clear user state
        self.user_states.pop(user.id, None)
        
        # Basic validation
        if not (channel_input.startswith('@') or channel_input.startswith('https://t.me/')):
            await update.message.reply_text(
                "❌ Invalid channel format. Please provide a channel username (@channel) or URL (https://t.me/channel)."
            )
            return
        
        # Extract channel identifier
        if channel_input.startswith('https://t.me/'):
            channel_username = channel_input.split('/')[-1]
        else:
            channel_username = channel_input.lstrip('@')
        
        await update.message.reply_text(
            f"📺 Channel `{channel_username}` will be processed.\n\n"
            "⚠️ **Note**: Channel processing is being migrated to the new system. "
            "Full functionality will be available soon.",
            parse_mode='Markdown'
        )
    
    async def _process_folder_input_legacy(self, update: Update, context: ContextTypes.DEFAULT_TYPE, folder_name: str) -> None:
        """Process folder name input."""
        user = update.effective_user
        
        # Clear user state
        self.user_states.pop(user.id, None)
        
        if len(folder_name) < 1 or len(folder_name) > 50:
            await update.message.reply_text(
                "❌ Folder name must be between 1 and 50 characters."
            )
            return
        
        await update.message.reply_text(
            f"📁 Folder `{folder_name}` will be created.\n\n"
            "⚠️ **Note**: Folder management is being migrated to the new system. "
            "Full functionality will be available soon.",
            parse_mode='Markdown'
        )
    
    async def _process_list_input_legacy(self, update: Update, context: ContextTypes.DEFAULT_TYPE, list_name: str) -> None:
        """Process list name input."""
        user = update.effective_user
        
        # Clear user state
        self.user_states.pop(user.id, None)
        
        if len(list_name) < 1 or len(list_name) > 50:
            await update.message.reply_text(
                "❌ List name must be between 1 and 50 characters."
            )
            return
        
        await update.message.reply_text(
            f"📋 List `{list_name}` will be created.\n\n"
            "⚠️ **Note**: List management is being migrated to the new system. "
            "Full functionality will be available soon.",
            parse_mode='Markdown'
        )
    
    async def _handle_command_legacy(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle legacy commands that might not be registered."""
        message_text = update.message.text.lower()
        
        if message_text in ['/folders', '/lists', '/channels', '/mappings']:
            await update.message.reply_text(
                f"ℹ️ The command `{message_text}` is being migrated. Please use /menu to access these features."
            )
        else:
            await update.message.reply_text(
                f"❓ Unknown command: `{message_text}`\n\nUse /help to see available commands.",
                parse_mode='Markdown'
            )
    
    async def _handle_channel_reference_legacy(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle when user sends a channel reference directly."""
        message_text = update.message.text
        
        await update.message.reply_text(
            f"📺 I see you mentioned a channel: `{message_text}`\n\n"
            "To add channels to your forwarding setup, please use /menu → Channels → Add Channel.",
            parse_mode='Markdown'
        )
    
    def _get_back_to_menu_keyboard(self) -> InlineKeyboardMarkup:
        """Get a simple back to menu keyboard."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ])
    
    def set_user_state(self, user_id: int, input_type: str, **kwargs) -> None:
        """Set user state for input processing."""
        self.user_states[user_id] = {
            'awaiting_input': True,
            'input_type': input_type,
            **kwargs
        }
    
    def clear_user_state(self, user_id: int) -> None:
        """Clear user state."""
        self.user_states.pop(user_id, None)
    
    def get_user_state(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get current user state."""
        return self.user_states.get(user_id)
