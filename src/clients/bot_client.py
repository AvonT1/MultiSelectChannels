"""
Bot API client manager using python-telegram-bot v20.x.
Handles all bot interactions and preserves existing handler functionality.
"""
import logging
from typing import Optional, Dict, Any, List
from telegram import Bot, Update
from telegram.ext import Application, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.error import TelegramError, RetryAfter, TimedOut

from src.config import settings
from src.database import get_db_session, User, UserRole

logger = logging.getLogger(__name__)


class BotClientManager:
    """Manages the Telegram Bot API client and handlers."""
    
    def __init__(self):
        self.application: Optional[Application] = None
        self.bot: Optional[Bot] = None
        self._is_running = False
    
    async def initialize(self) -> None:
        """Initialize the bot application and register handlers."""
        logger.info("Initializing Bot API client...")
        
        # Create application
        self.application = Application.builder().token(settings.bot_token).build()
        self.bot = self.application.bot
        
        # Register handlers
        await self._register_handlers()
        
        logger.info("Bot API client initialized successfully")
    
    async def _register_handlers(self) -> None:
        """Register all bot command and callback handlers."""
        app = self.application
        
        # Command handlers
        app.add_handler(CommandHandler("start", self._start_command))
        app.add_handler(CommandHandler("help", self._help_command))
        app.add_handler(CommandHandler("admin", self._admin_command))
        app.add_handler(CommandHandler("status", self._status_command))
        
        # Callback query handlers
        app.add_handler(CallbackQueryHandler(self._callback_query_handler))
        
        # Message handlers for user input states
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._message_handler))
        
        # Error handler
        app.add_error_handler(self._error_handler)
    
    async def _start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        user = update.effective_user
        if not user:
            return
        
        # Check if user is authorized
        if not await self._is_authorized_user(user.id):
            await update.message.reply_text(
                "❌ Access denied. This bot is restricted to authorized users only."
            )
            return
        
        welcome_text = (
            "🤖 **Telegram Forwarding Bot**\n\n"
            "Welcome to the advanced message forwarding system!\n\n"
            "**Features:**\n"
            "• Multi-channel forwarding with dual-client support\n"
            "• Private channel access via user session\n"
            "• Smart deduplication and retry mechanisms\n"
            "• FloodWait handling and rate limiting\n\n"
            "Use /help to see available commands."
        )
        
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
    
    async def _help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        user = update.effective_user
        if not user or not await self._is_authorized_user(user.id):
            return
        
        help_text = (
            "📚 **Available Commands:**\n\n"
            "**General:**\n"
            "• /start - Start the bot\n"
            "• /help - Show this help message\n"
            "• /status - Show system status\n\n"
            "**Admin Only:**\n"
            "• /admin - Access admin panel\n\n"
            "**Navigation:**\n"
            "Use the inline keyboard buttons to navigate through the bot's features."
        )
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def _admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /admin command (admin only)."""
        user = update.effective_user
        if not user:
            return
        
        if not await self._is_admin_user(user.id):
            await update.message.reply_text("❌ Admin access required.")
            return
        
        admin_text = (
            "🔧 **Admin Panel**\n\n"
            "**System Management:**\n"
            "• View forwarding statistics\n"
            "• Manage user permissions\n"
            "• Monitor queue status\n"
            "• Handle FloodWait incidents\n\n"
            "Use the buttons below to access admin functions."
        )
        
        # TODO: Add admin keyboard
        await update.message.reply_text(admin_text, parse_mode='Markdown')
    
    async def _status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command."""
        user = update.effective_user
        if not user or not await self._is_authorized_user(user.id):
            return
        
        # TODO: Implement status collection from various components
        status_text = (
            "📊 **System Status**\n\n"
            "🟢 Bot Client: Online\n"
            "🟡 User Client: Checking...\n"
            "🟢 Database: Connected\n"
            "🟢 Redis: Connected\n\n"
            "**Queue Status:**\n"
            "• Pending messages: 0\n"
            "• Processing: 0\n"
            "• Failed: 0\n"
        )
        
        await update.message.reply_text(status_text, parse_mode='Markdown')
    
    async def _callback_query_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle callback queries from inline keyboards."""
        query = update.callback_query
        user = update.effective_user
        
        if not user or not await self._is_authorized_user(user.id):
            await query.answer("Access denied.", show_alert=True)
            return
        
        await query.answer()
        
        # TODO: Implement callback handling logic
        # This will integrate with the existing handler system
        logger.info(f"Callback query: {query.data} from user {user.id}")
    
    async def _message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle text messages for user input states."""
        user = update.effective_user
        if not user or not await self._is_authorized_user(user.id):
            return
        
        # TODO: Implement state-based message handling
        # This will integrate with the existing user state system
        logger.info(f"Message from user {user.id}: {update.message.text}")
    
    async def _error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors in bot operations."""
        logger.error(f"Bot error: {context.error}", exc_info=context.error)
        
        # Handle specific error types
        if isinstance(context.error, RetryAfter):
            logger.warning(f"Rate limited by Telegram: retry after {context.error.retry_after} seconds")
        elif isinstance(context.error, TimedOut):
            logger.warning("Request timed out")
        elif isinstance(context.error, TelegramError):
            logger.error(f"Telegram API error: {context.error}")
    
    async def _is_authorized_user(self, user_id: int) -> bool:
        """Check if user is authorized to use the bot."""
        # Check admin list first
        if user_id in settings.admin_ids:
            return True
        
        # Check database for registered users
        async with get_db_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()
            return user is not None
    
    async def _is_admin_user(self, user_id: int) -> bool:
        """Check if user has admin privileges."""
        # Check admin list
        if user_id in settings.admin_ids:
            return True
        
        # Check database for admin role
        async with get_db_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(User).where(
                    User.telegram_id == user_id,
                    User.role == UserRole.ADMINISTRATOR
                )
            )
            user = result.scalar_one_or_none()
            return user is not None
    
    async def start(self) -> None:
        """Start the bot application."""
        if not self.application:
            await self.initialize()
        
        logger.info("Starting Bot API client...")
        await self.application.initialize()
        await self.application.start()
        self._is_running = True
        logger.info("Bot API client started successfully")
    
    async def stop(self) -> None:
        """Stop the bot application."""
        if self.application and self._is_running:
            logger.info("Stopping Bot API client...")
            await self.application.stop()
            await self.application.shutdown()
            self._is_running = False
            logger.info("Bot API client stopped")
    
    async def send_message(self, chat_id: int, text: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Send a message via Bot API."""
        if not self.bot:
            logger.error("Bot not initialized")
            return None
        
        try:
            message = await self.bot.send_message(chat_id=chat_id, text=text, **kwargs)
            return {
                'message_id': message.message_id,
                'chat_id': message.chat_id,
                'date': message.date
            }
        except TelegramError as e:
            logger.error(f"Failed to send message via Bot API: {e}")
            return None
    
    async def forward_message(self, chat_id: int, from_chat_id: int, message_id: int, **kwargs) -> Optional[Dict[str, Any]]:
        """Forward a message via Bot API."""
        if not self.bot:
            logger.error("Bot not initialized")
            return None
        
        try:
            message = await self.bot.forward_message(
                chat_id=chat_id,
                from_chat_id=from_chat_id,
                message_id=message_id,
                **kwargs
            )
            return {
                'message_id': message.message_id,
                'chat_id': message.chat_id,
                'date': message.date
            }
        except TelegramError as e:
            logger.error(f"Failed to forward message via Bot API: {e}")
            return None
    
    async def copy_message(self, chat_id: int, from_chat_id: int, message_id: int, **kwargs) -> Optional[Dict[str, Any]]:
        """Copy a message via Bot API."""
        if not self.bot:
            logger.error("Bot not initialized")
            return None
        
        try:
            message_id_result = await self.bot.copy_message(
                chat_id=chat_id,
                from_chat_id=from_chat_id,
                message_id=message_id,
                **kwargs
            )
            return {
                'message_id': message_id_result.message_id,
                'chat_id': chat_id
            }
        except TelegramError as e:
            logger.error(f"Failed to copy message via Bot API: {e}")
            return None
    
    @property
    def is_running(self) -> bool:
        """Check if bot is currently running."""
        return self._is_running
