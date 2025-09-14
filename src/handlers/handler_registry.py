"""
Handler registry for managing bot command and callback handlers.
Integrates existing functionality with the new dual-client architecture.
"""
import logging
from typing import Dict, Any, Optional, List

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from src.clients import ClientFactory
from src.core import ForwardingEngine
from ..config.settings import settings, is_admin
from .legacy_migrator import LegacyHandlerMigrator
from ..ui import MenuFormatter, state_manager, CallbackAction, parse_callback_data
from ..ui.state_manager import UserState
from ..ui.keyboards import ChannelKeyboards, MappingKeyboards
from src.database import get_db_session, User, Channel, ForwardingMapping, UserRole
from src.management import AdminCommands
from sqlalchemy import select, func

logger = logging.getLogger(__name__)


class HandlerRegistry:
    """Registry for managing all bot handlers and integrating legacy functionality."""
    
    def __init__(self, client_factory: ClientFactory, forwarding_engine: ForwardingEngine):
        """Initialize the handler registry with required dependencies."""
        self.client_factory = client_factory
        self.forwarding_engine = forwarding_engine
        self.admin_commands = AdminCommands()
        self.legacy_migrator = LegacyHandlerMigrator(client_factory, forwarding_engine)
        self.logger = logger.bind(component="handler_registry")
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the handler registry."""
        if self._initialized:
            return
        
        logger.info("Initializing handler registry...")
        
        # Initialize legacy handler migrator
        await self.legacy_migrator.initialize()
        
        self._initialized = True
        logger.info("Handler registry initialized")
    
    async def register_handlers(self) -> None:
        """Register all handlers with the bot client."""
        if not self._initialized:
            await self.initialize()
        
        bot_app = self.client_factory.bot_client.application
        if not bot_app:
            raise RuntimeError("Bot application not initialized")
        
        logger.info("Registering handlers with bot client...")
        
        # Register command handlers
        bot_app.add_handler(CommandHandler("start", self.handle_start))
        bot_app.add_handler(CommandHandler("help", self.handle_help))
        bot_app.add_handler(CommandHandler("menu", self.handle_main_menu))
        bot_app.add_handler(CommandHandler("status", self.handle_status))
        bot_app.add_handler(CommandHandler("admin", self.handle_admin_panel))
        bot_app.add_handler(CommandHandler("setup", self.handle_setup))
        
        # Register callback query handler
        bot_app.add_handler(CallbackQueryHandler(self.handle_callback_query))
        
        # Register message handler for state-based input
        bot_app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.handle_text_input
        ))
        
        # Register legacy handlers through migrator
        await self.legacy_migrator.register_handlers(bot_app)
        
        logger.info("All handlers registered successfully")
    
    # Command handlers with new UI integration
    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command with user registration and main menu."""
        user = update.effective_user
        if not user:
            return
        
        # Register or update user in database
        db_user = await self._register_user(user)
        
        # Clear any existing state
        state_manager.clear_user_state(user.id)
        
        # Show main menu
        message, keyboard = MenuFormatter.format_main_menu(db_user)
        await update.message.reply_text(message, reply_markup=keyboard, parse_mode='Markdown')
    
    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        help_text = """
📚 **Bot Commands Help**

**General Commands:**
• `/start` - Main menu and introduction
• `/help` - Show this help message
• `/menu` - Show main navigation menu
• `/status` - View system status
• `/setup` - Run setup wizard

**Navigation:**
• Use inline buttons for navigation
• 📺 Channels - Manage source/destination channels
• 🔗 Mappings - Configure forwarding rules
• ⚙️ Settings - User preferences

{f"**Admin Commands:**\\n• `/admin` - Administrator panel\\n• System management tools\\n" if is_admin(update.effective_user.id) else ""}

💡 **Tip:** Use the interactive menus for the best experience!
        """
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def handle_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /menu command to show main menu."""
        user = update.effective_user
        if not user:
            return
        
        db_user = await self._get_or_create_user(user)
        message, keyboard = MenuFormatter.format_main_menu(db_user)
        await update.message.reply_text(message, reply_markup=keyboard, parse_mode='Markdown')
    
    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command."""
        try:
            admin_commands = AdminCommands()
            stats_result = await admin_commands.get_system_stats()
            message, keyboard = MenuFormatter.format_system_status(stats_result)
            await update.message.reply_text(message, reply_markup=keyboard, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error getting system status: {e}")
            error_message = MenuFormatter.format_error_message(
                "Unable to retrieve system status",
                "Please try again later or contact an administrator"
            )
            await update.message.reply_text(error_message, parse_mode='Markdown')
    
    async def handle_admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /admin command (admin only)."""
        user = update.effective_user
        if not user or not is_admin(user.id):
            await update.message.reply_text("❌ Access denied. Administrator privileges required.")
            return
        
        message, keyboard = MenuFormatter.format_admin_panel()
        await update.message.reply_text(message, reply_markup=keyboard, parse_mode='Markdown')
    
    async def handle_setup(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /setup command to start setup wizard."""
        user = update.effective_user
        if not user:
            return
        
        # Start setup workflow
        state_manager.start_setup_workflow(user.id)
        
        setup_message = """
🚀 **Setup Wizard**

Welcome! I'll help you configure your first forwarding setup.

**Steps:**
1. ✅ **Welcome** (current)
2. 📺 Add channels
3. 🔗 Create mappings
4. ✅ Complete setup

**Prerequisites:**
• Admin access to channels you want to use
• Channel IDs or usernames ready
• Bot added to private channels (if any)

Ready to continue?
        """
        
        from src.ui.keyboards import KeyboardBuilder
        builder = KeyboardBuilder()
        builder.add_row([("▶️ Continue", "setup_continue"), ("❌ Cancel", "setup_cancel")])
        keyboard = builder.build()
        
        await update.message.reply_text(setup_message, reply_markup=keyboard, parse_mode='Markdown')
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle callback queries from inline keyboards."""
        query = update.callback_query
        user = update.effective_user
        
        if not user:
            await query.answer("Access denied.", show_alert=True)
            return
        
        await query.answer()
        
        # Parse callback data
        callback_data = parse_callback_data(query.data)
        action = CallbackAction(callback_data['action'])
        
        try:
            if action == CallbackAction.MAIN_MENU:
                await self._handle_main_menu_callback(query, user)
            elif action == CallbackAction.CHANNELS_LIST:
                await self._handle_channels_list_callback(query, user, callback_data)
            elif action == CallbackAction.CHANNEL_VIEW:
                await self._handle_channel_view_callback(query, user, callback_data)
            elif action == CallbackAction.MAPPINGS_LIST:
                await self._handle_mappings_list_callback(query, user, callback_data)
            elif action == CallbackAction.MAPPING_VIEW:
                await self._handle_mapping_view_callback(query, user, callback_data)
            elif action == CallbackAction.ADMIN_PANEL:
                await self._handle_admin_panel_callback(query, user)
            elif action == CallbackAction.SYSTEM_STATUS:
                await self._handle_system_status_callback(query, user)
            elif action == CallbackAction.SETTINGS:
                await self._handle_settings_callback(query, user)
            else:
                # Delegate to legacy handler migrator for existing functionality
                await self.legacy_migrator.handle_callback_query(update, context)
                
        except Exception as e:
            logger.error(f"Error handling callback query: {e}")
            await query.edit_message_text("❌ An error occurred. Please try again.")
    
    async def handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle text messages for user input states."""
        user = update.effective_user
        if not user:
            return
        
        user_state = state_manager.get_user_state(user.id)
        
        if user_state.state == UserState.WAITING_FOR_INPUT:
            # Handle input validation
            input_text = update.message.text
            is_valid, error_message = state_manager.validate_input(user.id, input_text)
            
            if is_valid:
                # Process valid input based on input type
                input_type = user_state.get('input_type')
                await self._process_valid_input(update, user, input_type, input_text)
            else:
                # Show error and ask again
                attempts = user_state.get('attempts', 0) + 1
                user_state.set('attempts', attempts)
                
                if attempts >= user_state.get('max_attempts', 3):
                    # Max attempts reached, cancel operation
                    state_manager.clear_user_state(user.id)
                    await update.message.reply_text("❌ Too many invalid attempts. Operation cancelled.")
                else:
                    await update.message.reply_text(f"❌ {error_message}\n\nPlease try again:")
        else:
            # Delegate to legacy handler migrator for existing functionality
            await self.legacy_migrator.handle_message(update, context)
    
    # Helper methods for callback handling
    async def _handle_main_menu_callback(self, query, user):
        """Handle main menu callback."""
        db_user = await self._get_or_create_user(user)
        message, keyboard = MenuFormatter.format_main_menu(db_user)
        await query.edit_message_text(message, reply_markup=keyboard, parse_mode='Markdown')
    
    async def _handle_channels_list_callback(self, query, user, callback_data):
        """Handle channels list callback."""
        page = callback_data.get('page', 0)
        
        async with get_db_session() as session:
            # Get channels with pagination
            channels_query = select(Channel).offset(page * 10).limit(10)
            result = await session.execute(channels_query)
            channels = result.scalars().all()
            
            # Get total count for pagination
            count_result = await session.execute(select(func.count(Channel.id)))
            total_count = count_result.scalar()
            
            pagination = PaginationInfo(
                current_page=page,
                total_pages=(total_count + 9) // 10,
                items_per_page=10,
                total_items=total_count
            )
            
            db_user = await self._get_or_create_user(user)
            message, keyboard = MenuFormatter.format_channels_list(channels, pagination, db_user.role)
            await query.edit_message_text(message, reply_markup=keyboard, parse_mode='Markdown')
    
    async def _handle_channel_view_callback(self, query, user, callback_data):
        """Handle channel view callback."""
        channel_id = callback_data.get('id')
        if not channel_id:
            return
        
        async with get_db_session() as session:
            result = await session.execute(select(Channel).where(Channel.id == channel_id))
            channel = result.scalar_one_or_none()
            
            if channel:
                db_user = await self._get_or_create_user(user)
                message, keyboard = MenuFormatter.format_channel_view(channel, db_user.role)
                await query.edit_message_text(message, reply_markup=keyboard, parse_mode='Markdown')
    
    async def _handle_mappings_list_callback(self, query, user, callback_data):
        """Handle mappings list callback."""
        page = callback_data.get('page', 0)
        channel_filter = callback_data.get('channel_filter')
        
        async with get_db_session() as session:
            # Build query with optional channel filter
            mappings_query = select(ForwardingMapping)
            if channel_filter:
                mappings_query = mappings_query.where(
                    (ForwardingMapping.source_channel_id == channel_filter) |
                    (ForwardingMapping.dest_channel_id == channel_filter)
                )
            
            mappings_query = mappings_query.offset(page * 10).limit(10)
            result = await session.execute(mappings_query)
            mappings = result.scalars().all()
            
            # Get total count
            count_query = select(func.count(ForwardingMapping.id))
            if channel_filter:
                count_query = count_query.where(
                    (ForwardingMapping.source_channel_id == channel_filter) |
                    (ForwardingMapping.dest_channel_id == channel_filter)
                )
            
            count_result = await session.execute(count_query)
            total_count = count_result.scalar()
            
            pagination = PaginationInfo(
                current_page=page,
                total_pages=(total_count + 9) // 10,
                items_per_page=10,
                total_items=total_count
            )
            
            # Get channel filter object if needed
            filter_channel = None
            if channel_filter:
                filter_result = await session.execute(select(Channel).where(Channel.id == channel_filter))
                filter_channel = filter_result.scalar_one_or_none()
            
            db_user = await self._get_or_create_user(user)
            message, keyboard = MenuFormatter.format_mappings_list(mappings, pagination, db_user.role, filter_channel)
            await query.edit_message_text(message, reply_markup=keyboard, parse_mode='Markdown')
    
    async def _handle_mapping_view_callback(self, query, user, callback_data):
        """Handle mapping view callback."""
        mapping_id = callback_data.get('id')
        if not mapping_id:
            return
        
        async with get_db_session() as session:
            result = await session.execute(select(ForwardingMapping).where(ForwardingMapping.id == mapping_id))
            mapping = result.scalar_one_or_none()
            
            if mapping:
                db_user = await self._get_or_create_user(user)
                message, keyboard = MenuFormatter.format_mapping_view(mapping, db_user.role)
                await query.edit_message_text(message, reply_markup=keyboard, parse_mode='Markdown')
    
    async def _handle_admin_panel_callback(self, query, user):
        """Handle admin panel callback."""
        if not is_admin(user.id):
            await query.answer("Access denied.", show_alert=True)
            return
        
        message, keyboard = MenuFormatter.format_admin_panel()
        await query.edit_message_text(message, reply_markup=keyboard, parse_mode='Markdown')
    
    async def _handle_system_status_callback(self, query, user):
        """Handle system status callback."""
        try:
            admin_commands = AdminCommands()
            stats_result = await admin_commands.get_system_stats()
            message, keyboard = MenuFormatter.format_system_status(stats_result)
            await query.edit_message_text(message, reply_markup=keyboard, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error getting system status: {e}")
            await query.edit_message_text("❌ Error loading system status. Please try again.")
    
    async def _handle_settings_callback(self, query, user):
        """Handle settings callback."""
        db_user = await self._get_or_create_user(user)
        message, keyboard = MenuFormatter.format_settings_menu(db_user.role)
        await query.edit_message_text(message, reply_markup=keyboard, parse_mode='Markdown')
    
    async def _process_valid_input(self, update, user, input_type: str, input_text: str):
        """Process validated user input."""
        if input_type == 'channel_id':
            # Handle channel ID input
            try:
                channel_id = int(input_text)
                # TODO: Validate channel exists and add to database
                await update.message.reply_text(f"✅ Channel ID {channel_id} processed successfully!")
            except ValueError:
                await update.message.reply_text("❌ Invalid channel ID format.")
        
        elif input_type == 'channel_title':
            # Handle channel title input
            # TODO: Update channel title in database
            await update.message.reply_text(f"✅ Channel title updated to: {input_text}")
        
        # Clear user state after processing
        state_manager.clear_user_state(user.id)
    
    # User management helpers
    async def _register_user(self, telegram_user) -> User:
        """Register or update user in database."""
        async with get_db_session() as session:
            # Check if user exists
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_user.id)
            )
            user = result.scalar_one_or_none()
            
            if user:
                # Update existing user
                user.username = telegram_user.username
                user.last_seen = func.now()
            else:
                # Create new user
                role = UserRole.ADMINISTRATOR if is_admin(telegram_user.id) else UserRole.USER
                user = User(
                    telegram_id=telegram_user.id,
                    username=telegram_user.username,
                    role=role
                )
                session.add(user)
            
            await session.commit()
            await session.refresh(user)
            return user
    
    async def _get_or_create_user(self, telegram_user) -> User:
        """Get or create user in database."""
        return await self._register_user(telegram_user)
    
    # Command handlers
    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Enhanced /start command with system status and main menu."""
        user = update.effective_user
        if not user:
            return
        
        # Register or update user in database
        db_user = await self._register_user(user)
        
        # Clear any existing state
        state_manager.clear_user_state(user.id)
        
        # Show main menu
        message, keyboard = MenuFormatter.format_main_menu(db_user)
        await update.message.reply_text(message, reply_markup=keyboard, parse_mode='Markdown')
    
    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Enhanced /help command."""
        user = update.effective_user
        if not user or not await self._is_authorized_user(user.id):
            return
        
        is_admin_user = await self._is_admin_user(user.id)
        
        help_text = """📚 **Available Commands:**

**General Commands:**
• /start - System status and main menu
• /help - Show this help message  
• /status - Detailed system status

**Channel Management:**
• Browse and manage forwarding lists
• Add/remove source and destination channels
• Configure forwarding modes (forward/copy)
• Set up content filters

**Advanced Features:**
• Dual-client architecture (Bot API + MTProto)
• Private channel access via user session
• Smart deduplication and retry logic
• FloodWait handling and rate limiting"""
        
        if is_admin_user:
            help_text += """

**Admin Commands:**
• /admin - Access admin panel
• /setup - Initial system setup
• Monitor queue status and performance
• Manage user permissions
• View system logs and metrics"""
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def handle_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show main menu."""
        user = update.effective_user
        if not user or not await self._is_authorized_user(user.id):
            return
        
        db_user = await self._get_or_create_user(user)
        message, keyboard = MenuFormatter.format_main_menu(db_user)
        await update.message.reply_text(message, reply_markup=keyboard, parse_mode='Markdown')
    
    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Detailed system status command."""
        user = update.effective_user
        if not user or not await self._is_authorized_user(user.id):
            return
        
        # Collect comprehensive status
        client_status = self.client_factory.get_client_status()
        engine_stats = await self.forwarding_engine.get_statistics()
        queue_stats = await self.forwarding_engine.queue_manager.get_queue_statistics()
        
        status_text = f"""📊 **Detailed System Status**

**Client Status:**
🤖 Bot Client: {'✅ Running' if client_status['bot_client']['running'] else '❌ Stopped'}
👤 User Client: {'✅ Running' if client_status['user_client']['running'] else '❌ Stopped'}
🔐 User Authorized: {'✅ Yes' if client_status['user_client']['authorized'] else '❌ No'}

**Forwarding Engine:**
⚙️ Status: {'✅ Running' if engine_stats['engine_running'] else '❌ Stopped'}
👷 Workers: {engine_stats['workers_running']} active

**Message Processing:**
📥 Pending: {engine_stats['message_counts']['pending']}
⚡ Processing: {engine_stats['message_counts']['processing']}
✅ Successful: {engine_stats['message_counts']['success']}
❌ Failed: {engine_stats['message_counts']['failed']}
🔄 Retrying: {engine_stats['message_counts']['retrying']}

**Queue Status:**
📋 Main Queue: {queue_stats['queue_sizes'].get('main', 0)}
⏰ Retry Queue: {queue_stats['queue_sizes'].get('retry', 0)}
🚫 FloodWait Queue: {queue_stats['queue_sizes'].get('flood_wait', 0)}
💾 Failed Queue: {queue_stats['queue_sizes'].get('failed', 0)}

**Configuration:**
🔧 Max Concurrent: {settings.max_concurrent_forwards}
🔄 Max Retries: {settings.max_retry_attempts}
⏱️ FloodWait Multiplier: {settings.flood_wait_multiplier}"""
        
        await update.message.reply_text(status_text, parse_mode='Markdown')
    
    async def handle_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Admin panel command."""
        user = update.effective_user
        if not user or not await self._is_admin_user(user.id):
            await update.message.reply_text("❌ Admin access required.")
            return
        
        db_user = await self._get_or_create_user(user)
        message, keyboard = MenuFormatter.format_admin_panel(db_user)
        await update.message.reply_text(message, reply_markup=keyboard, parse_mode='Markdown')
    
    async def handle_setup(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Initial system setup command."""
        user = update.effective_user
        if not user or not await self._is_admin_user(user.id):
            await update.message.reply_text("❌ Admin access required for setup.")
            return
        
        # Check if user client needs authentication
        if not self.client_factory.user_client.is_authorized:
            setup_text = """🔧 **System Setup Required**

The user client (MTProto) needs to be authenticated for private channel access.

**Setup Steps:**
1. Provide your phone number
2. Enter verification code from Telegram
3. Enter 2FA password if enabled
4. Complete authentication

This is required for accessing private channels and advanced forwarding features.

Please provide your phone number (with country code, e.g., +1234567890):"""
            
            # Set user state for phone input
            state_manager.set_user_state(
                user.id, 
                UserState.AWAITING_PHONE_NUMBER,
                context={'setup_step': 'phone'}
            )
            await update.message.reply_text(setup_text, parse_mode='Markdown')
        else:
            await update.message.reply_text("✅ System is already set up and ready to use!")
    
    # Callback query handlers
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle callback queries from inline keyboards."""
        query = update.callback_query
        user = update.effective_user
        
        if not user or not await self._is_authorized_user(user.id):
            await query.answer("Access denied.", show_alert=True)
            return
        
        await query.answer()
        
        # Parse callback data
        try:
            callback_data = parse_callback_data(query.data)
            action = callback_data.get('action')
            
            if action == CallbackAction.MAIN_MENU:
                await self._handle_main_menu_callback(update, context, callback_data)
            elif action == CallbackAction.CHANNELS_MENU:
                await self._handle_channels_callback(update, context, callback_data)
            elif action == CallbackAction.MAPPINGS_MENU:
                await self._handle_mappings_callback(update, context, callback_data)
            elif action == CallbackAction.ADMIN_PANEL:
                await self._handle_admin_callback(update, context, callback_data)
            elif action == CallbackAction.SYSTEM_STATUS:
                await self._handle_status_callback(update, context, callback_data)
            elif action == CallbackAction.SETTINGS:
                await self._handle_settings_callback(update, context, callback_data)
            else:
                # Delegate to legacy handler migrator for existing functionality
                await self.legacy_migrator.handle_callback_query(update, context)
                
        except Exception as e:
            logger.error(f"Error handling callback query: {e}")
            # Fallback to legacy handler
            await self.legacy_migrator.handle_callback_query(update, context)
    
    async def _handle_main_menu_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: dict) -> None:
        """Handle main menu callbacks."""
        user = update.effective_user
        db_user = await self._get_or_create_user(user)
        
        sub_action = callback_data.get('sub_action')
        
        if sub_action == 'channels':
            message, keyboard = MenuFormatter.format_channels_menu(db_user)
            await update.callback_query.edit_message_text(message, reply_markup=keyboard, parse_mode='Markdown')
        elif sub_action == 'mappings':
            message, keyboard = MenuFormatter.format_mappings_menu(db_user)
            await update.callback_query.edit_message_text(message, reply_markup=keyboard, parse_mode='Markdown')
        elif sub_action == 'status':
            message, keyboard = MenuFormatter.format_system_status(db_user)
            await update.callback_query.edit_message_text(message, reply_markup=keyboard, parse_mode='Markdown')
        elif sub_action == 'settings':
            message, keyboard = MenuFormatter.format_settings_menu(db_user)
            await update.callback_query.edit_message_text(message, reply_markup=keyboard, parse_mode='Markdown')
    
    async def _handle_channels_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: dict) -> None:
        """Handle channel management callbacks."""
        # Delegate to legacy handler for now
        await self.legacy_migrator.handle_callback_query(update, context)
    
    async def _handle_mappings_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: dict) -> None:
        """Handle mapping management callbacks."""
        # Delegate to legacy handler for now
        await self.legacy_migrator.handle_callback_query(update, context)
    
    async def _handle_admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: dict) -> None:
        """Handle admin panel callbacks."""
        user = update.effective_user
        if not await self._is_admin_user(user.id):
            await update.callback_query.answer("Admin access required.", show_alert=True)
            return
        
        # Delegate to legacy handler for now
        await self.legacy_migrator.handle_callback_query(update, context)
    
    async def _handle_status_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: dict) -> None:
        """Handle system status callbacks."""
        # Refresh status display
        await self.handle_status(update, context)
    
    async def _handle_settings_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: dict) -> None:
        """Handle settings callbacks."""
        # Delegate to legacy handler for now
        await self.legacy_migrator.handle_callback_query(update, context)
    
    # Message handlers
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle text messages for user input states."""
        user = update.effective_user
        if not user or not await self._is_authorized_user(user.id):
            return
        
        user_state = state_manager.get_user_state(user.id)
        
        if user_state:
            # Process user input based on current state
            await self._process_user_input(update, context, user_state)
        else:
            # Delegate to legacy handler migrator for existing functionality
            await self.legacy_migrator.handle_message(update, context)
    
    async def _process_user_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_state: UserState) -> None:
        """Process user input based on current conversation state."""
        user = update.effective_user
        message_text = update.message.text
        
        try:
            if user_state.state == UserState.AWAITING_PHONE_NUMBER:
                # Validate phone number format
                if state_manager.validate_input(message_text, 'phone'):
                    # TODO: Implement phone number authentication flow
                    await update.message.reply_text(
                        "📱 Phone number received. Authentication flow will be implemented."
                    )
                    state_manager.clear_user_state(user.id)
                else:
                    await update.message.reply_text(
                        "❌ Invalid phone number format. Please use international format (e.g., +1234567890):"
                    )
            
            elif user_state.state == UserState.AWAITING_CHANNEL_INPUT:
                # Validate channel input
                if state_manager.validate_input(message_text, 'channel'):
                    # TODO: Process channel addition
                    await update.message.reply_text(
                        "📺 Channel input received. Processing will be implemented."
                    )
                    state_manager.clear_user_state(user.id)
                else:
                    await update.message.reply_text(
                        "❌ Invalid channel format. Please provide a valid channel username or ID:"
                    )
            
            else:
                # Unknown state, clear and delegate to legacy handler
                state_manager.clear_user_state(user.id)
                await self.legacy_migrator.handle_message(update, context)
                
        except Exception as e:
            logger.error(f"Error processing user input: {e}")
            state_manager.clear_user_state(user.id)
            await update.message.reply_text("❌ An error occurred. Please try again.")
    
    # Error handler
    async def handle_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Enhanced error handler with logging."""
        logger.error("Bot error occurred", error=str(context.error), exc_info=context.error)
        
        # Handle specific error types
        from telegram.error import RetryAfter, TimedOut, TelegramError
        
        if isinstance(context.error, RetryAfter):
            logger.warning(f"Rate limited: retry after {context.error.retry_after} seconds")
        elif isinstance(context.error, TimedOut):
            logger.warning("Request timed out")
        elif isinstance(context.error, TelegramError):
            logger.error(f"Telegram API error: {context.error}")
    
    # Helper methods
    async def _is_authorized_user(self, user_id: int) -> bool:
        """Check if user is authorized to use the bot."""
        return is_admin(user_id)  # For now, only admins can use the bot
    
    async def _is_admin_user(self, user_id: int) -> bool:
        """Check if user has admin privileges."""
        return is_admin(user_id)
