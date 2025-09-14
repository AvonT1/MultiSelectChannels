"""
Main entry point for the Telegram Bot Forwarding System.

This module initializes the dual-client architecture (python-telegram-bot + Telethon),
sets up the forwarding engine, and starts the bot with the new handler registry.
"""

import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager

import structlog
from telegram.ext import Application

from src.config.settings import settings
from src.clients.client_factory import ClientFactory
from src.core.forwarding_engine import ForwardingEngine
from src.handlers.handler_registry import HandlerRegistry
from src.database.connection import init_database

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

# Set up Python logging
logging.basicConfig(
    level=logging.INFO if not settings.debug_mode else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = structlog.get_logger(__name__)


class BotApplication:
    """Main application class for the Telegram forwarding bot."""
    
    def __init__(self):
        self.client_factory: ClientFactory = None
        self.forwarding_engine: ForwardingEngine = None
        self.handler_registry: HandlerRegistry = None
        self.telegram_app: Application = None
        self._shutdown_event = asyncio.Event()
    
    async def initialize(self) -> None:
        """Initialize all components of the bot application."""
        logger.info("Initializing bot application...")
        
        # Initialize database
        await init_database()
        logger.info("Database initialized")
        
        # Initialize client factory
        self.client_factory = ClientFactory()
        await self.client_factory.initialize()
        logger.info("Client factory initialized")
        
        # Initialize forwarding engine
        self.forwarding_engine = ForwardingEngine(self.client_factory)
        await self.forwarding_engine.start()
        logger.info("Forwarding engine initialized")
        
        # Initialize handler registry
        self.handler_registry = HandlerRegistry(self.client_factory, self.forwarding_engine)
        await self.handler_registry.initialize()
        logger.info("Handler registry initialized")
        
        # Create Telegram application
        self.telegram_app = Application.builder().token(settings.bot_token).build()
        
        # Register handlers
        await self.handler_registry.register_handlers()
        logger.info("Bot handlers registered")
        
        logger.info("Bot application initialization complete")
    
    async def start(self) -> None:
        """Start the bot application."""
        logger.info("Starting bot application...")
        
        # Start background services
        # Health check server can be added later if needed
        
        # Start clients
        await self.client_factory.start_all()
        logger.info("All clients started")
        
        # Start forwarding engine
        await self.forwarding_engine.start()
        logger.info("Forwarding engine started")
        
        # Start Telegram bot
        await self.telegram_app.initialize()
        await self.telegram_app.start()
        await self.telegram_app.updater.start_polling(
            allowed_updates=['message', 'callback_query', 'inline_query'],
            drop_pending_updates=True
        )
        
        logger.info("Bot application started successfully")
        
        # Wait for shutdown signal
        await self._shutdown_event.wait()
    
    async def shutdown(self) -> None:
        """Gracefully shutdown the bot application."""
        logger.info("Shutting down bot application...")
        
        # Stop Telegram bot
        if self.telegram_app:
            await self.telegram_app.updater.stop()
            await self.telegram_app.stop()
            await self.telegram_app.shutdown()
            logger.info("Telegram bot stopped")
        
        # Stop forwarding engine
        if self.forwarding_engine:
            await self.forwarding_engine.stop()
            logger.info("Forwarding engine stopped")
        
        # Stop clients
        if self.client_factory:
            await self.client_factory.stop_all()
            logger.info("All clients stopped")
        
        logger.info("Bot application shutdown complete")
    
    def signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        self._shutdown_event.set()


async def main():
    """Main entry point for the bot application."""
    app = BotApplication()
    
    # Set up signal handlers
    for sig in [signal.SIGTERM, signal.SIGINT]:
        signal.signal(sig, app.signal_handler)
    
    try:
        # Initialize and start the application
        await app.initialize()
        await app.start()
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error("Fatal error in main application", error=str(e), exc_info=e)
        sys.exit(1)
    finally:
        # Ensure clean shutdown
        await app.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated by user")
    except Exception as e:
        logger.error("Application terminated with error", error=str(e), exc_info=e)
        sys.exit(1)
