"""
Main application entry point for the enhanced Telegram forwarding bot.
Integrates dual-client architecture with forwarding engine and queue management.
"""
import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager
from typing import Optional

import structlog
import uvloop
from src.config import settings
from src.database import init_database, close_database
from src.clients import ClientFactory, get_client_factory
from src.core import ForwardingEngine
from src.handlers import HandlerRegistry

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

logger = structlog.get_logger(__name__)


class TelegramForwardingBot:
    """Main application class for the Telegram forwarding bot."""
    
    def __init__(self):
        self.client_factory: Optional[ClientFactory] = None
        self.forwarding_engine: Optional[ForwardingEngine] = None
        self.handler_registry: Optional[HandlerRegistry] = None
        self._shutdown_event = asyncio.Event()
        self._running = False
    
    async def initialize(self) -> None:
        """Initialize all application components."""
        logger.info("Initializing Telegram Forwarding Bot...")
        
        # Initialize database
        await init_database()
        logger.info("Database initialized")
        
        # Initialize client factory
        self.client_factory = await get_client_factory()
        logger.info("Client factory initialized")
        
        # Initialize forwarding engine
        self.forwarding_engine = ForwardingEngine(self.client_factory)
        logger.info("Forwarding engine initialized")
        
        # Initialize handler registry
        self.handler_registry = HandlerRegistry(self.client_factory, self.forwarding_engine)
        await self.handler_registry.initialize()
        logger.info("Handler registry initialized")
        
        logger.info("Bot initialization completed successfully")
    
    async def start(self) -> None:
        """Start all bot components."""
        if self._running:
            return
        
        logger.info("Starting Telegram Forwarding Bot...")
        
        try:
            # Start clients
            await self.client_factory.start_all()
            logger.info("All clients started")
            
            # Start forwarding engine
            await self.forwarding_engine.start()
            logger.info("Forwarding engine started")
            
            # Register handlers with clients
            await self.handler_registry.register_handlers()
            logger.info("Handlers registered")
            
            self._running = True
            logger.info("🚀 Telegram Forwarding Bot is now running!")
            
            # Log system status
            await self._log_system_status()
            
        except Exception as e:
            logger.error("Failed to start bot", error=str(e), exc_info=True)
            await self.stop()
            raise
    
    async def stop(self) -> None:
        """Stop all bot components gracefully."""
        if not self._running:
            return
        
        logger.info("Stopping Telegram Forwarding Bot...")
        self._running = False
        
        try:
            # Stop forwarding engine
            if self.forwarding_engine:
                await self.forwarding_engine.stop()
                logger.info("Forwarding engine stopped")
            
            # Stop clients
            if self.client_factory:
                await self.client_factory.stop_all()
                logger.info("All clients stopped")
            
            # Close database connections
            await close_database()
            logger.info("Database connections closed")
            
            logger.info("✅ Telegram Forwarding Bot stopped gracefully")
            
        except Exception as e:
            logger.error("Error during shutdown", error=str(e), exc_info=True)
    
    async def run(self) -> None:
        """Run the bot until shutdown signal."""
        await self.initialize()
        await self.start()
        
        # Wait for shutdown signal
        await self._shutdown_event.wait()
        
        await self.stop()
    
    async def _log_system_status(self) -> None:
        """Log current system status."""
        try:
            # Client status
            client_status = self.client_factory.get_client_status()
            logger.info("Client status", **client_status)
            
            # Forwarding engine status
            if self.forwarding_engine:
                engine_stats = await self.forwarding_engine.get_statistics()
                logger.info("Forwarding engine status", **engine_stats)
            
        except Exception as e:
            logger.warning("Failed to get system status", error=str(e))
    
    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating shutdown...")
            self._shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    @property
    def is_running(self) -> bool:
        """Check if bot is currently running."""
        return self._running


async def main():
    """Main application entry point."""
    # Use uvloop for better performance on Unix systems
    if sys.platform != 'win32':
        uvloop.install()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('bot.log', encoding='utf-8')
        ]
    )
    
    # Create and run bot
    bot = TelegramForwardingBot()
    bot._setup_signal_handlers()
    
    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error("Unexpected error in main", error=str(e), exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
