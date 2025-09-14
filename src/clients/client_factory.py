"""
Client factory for managing dual Telegram clients.
Provides unified interface for bot and user client operations.
"""
import logging
from typing import Optional, Dict, Any, List, Union
from enum import Enum

from .bot_client import BotClientManager
from .user_client import UserClientManager
from src.database import AccessType

logger = logging.getLogger(__name__)


class ClientType(Enum):
    """Client type enumeration."""
    BOT = "bot"
    USER = "user"
    AUTO = "auto"  # Automatically choose best client


class ClientFactory:
    """Factory for managing and coordinating dual Telegram clients."""
    
    def __init__(self):
        self.bot_client = BotClientManager()
        self.user_client = UserClientManager()
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize both clients."""
        if self._initialized:
            return
        
        logger.info("Initializing client factory...")
        
        # Initialize both clients
        await self.bot_client.initialize()
        await self.user_client.initialize()
        
        self._initialized = True
        logger.info("Client factory initialized successfully")
    
    async def start_all(self) -> None:
        """Start both bot and user clients."""
        if not self._initialized:
            await self.initialize()
        
        logger.info("Starting all clients...")
        
        # Start bot client
        await self.bot_client.start()
        
        # Start user client
        await self.user_client.start()
        
        logger.info("All clients started successfully")
    
    async def stop_all(self) -> None:
        """Stop both clients."""
        logger.info("Stopping all clients...")
        
        await self.bot_client.stop()
        await self.user_client.stop()
        
        logger.info("All clients stopped")
    
    def get_optimal_client(self, source_access: AccessType, dest_access: AccessType) -> ClientType:
        """Determine the optimal client for a forwarding operation."""
        # If both source and destination are accessible via bot, prefer bot client
        if source_access == AccessType.BOT and dest_access == AccessType.BOT:
            return ClientType.BOT
        
        # If either requires user access, use user client
        if source_access == AccessType.USER or dest_access == AccessType.USER:
            return ClientType.USER
        
        # Default to bot client
        return ClientType.BOT
    
    async def send_message(self, chat_id: int, text: str, client_type: ClientType = ClientType.AUTO, **kwargs) -> Optional[Dict[str, Any]]:
        """Send message using specified or optimal client."""
        if client_type == ClientType.BOT or (client_type == ClientType.AUTO and self.bot_client.is_running):
            return await self.bot_client.send_message(chat_id, text, **kwargs)
        elif client_type == ClientType.USER or (client_type == ClientType.AUTO and self.user_client.is_running):
            return await self.user_client.send_message(chat_id, text, **kwargs)
        else:
            logger.error("No suitable client available for send_message")
            return None
    
    async def forward_message(self, to_chat: int, from_chat: int, message_id: int, 
                            client_type: ClientType = ClientType.AUTO, **kwargs) -> Optional[Dict[str, Any]]:
        """Forward message using specified or optimal client."""
        if client_type == ClientType.BOT:
            return await self.bot_client.forward_message(to_chat, from_chat, message_id, **kwargs)
        elif client_type == ClientType.USER:
            return await self.user_client.forward_message(to_chat, from_chat, message_id, **kwargs)
        elif client_type == ClientType.AUTO:
            # Try bot first, fallback to user
            result = await self.bot_client.forward_message(to_chat, from_chat, message_id, **kwargs)
            if result is None and self.user_client.is_running:
                result = await self.user_client.forward_message(to_chat, from_chat, message_id, **kwargs)
            return result
        else:
            logger.error("Invalid client type for forward_message")
            return None
    
    async def copy_message(self, to_chat: int, from_chat: int, message_id: int,
                         client_type: ClientType = ClientType.AUTO, **kwargs) -> Optional[Dict[str, Any]]:
        """Copy message using specified or optimal client."""
        if client_type == ClientType.BOT:
            return await self.bot_client.copy_message(to_chat, from_chat, message_id, **kwargs)
        elif client_type == ClientType.USER:
            return await self.user_client.copy_message(to_chat, from_chat, message_id, **kwargs)
        elif client_type == ClientType.AUTO:
            # Try bot first, fallback to user
            result = await self.bot_client.copy_message(to_chat, from_chat, message_id, **kwargs)
            if result is None and self.user_client.is_running:
                result = await self.user_client.copy_message(to_chat, from_chat, message_id, **kwargs)
            return result
        else:
            logger.error("Invalid client type for copy_message")
            return None
    
    async def get_chat_info(self, chat_id: Union[int, str], client_type: ClientType = ClientType.AUTO) -> Optional[Dict[str, Any]]:
        """Get chat information using specified or optimal client."""
        if client_type == ClientType.USER or (client_type == ClientType.AUTO and self.user_client.is_running):
            return await self.user_client.get_entity_info(chat_id)
        elif client_type == ClientType.BOT:
            # Bot client doesn't have get_entity_info, would need to implement
            logger.warning("Bot client get_chat_info not implemented")
            return None
        else:
            return None
    
    async def check_chat_access(self, chat_id: int, client_type: ClientType = ClientType.AUTO) -> Dict[str, Any]:
        """Check chat access using specified client."""
        if client_type == ClientType.USER or client_type == ClientType.AUTO:
            return await self.user_client.check_chat_access(chat_id)
        else:
            # For bot client, we'd need to implement similar functionality
            return {"has_access": False, "error": "Bot client access check not implemented"}
    
    def get_client_status(self) -> Dict[str, Any]:
        """Get status of both clients."""
        return {
            "bot_client": {
                "running": self.bot_client.is_running,
                "initialized": self.bot_client.application is not None
            },
            "user_client": {
                "running": self.user_client.is_running,
                "authorized": self.user_client.is_authorized,
                "initialized": self.user_client.client is not None
            },
            "factory_initialized": self._initialized
        }
    
    async def authenticate_user_client(self, phone: str) -> Dict[str, Any]:
        """Authenticate user client (setup helper)."""
        return await self.user_client.authenticate_user(phone)
    
    async def verify_user_code(self, phone: str, code: str, phone_code_hash: str, password: Optional[str] = None) -> Dict[str, Any]:
        """Verify user client authentication code."""
        return await self.user_client.verify_code(phone, code, phone_code_hash, password)


# Global client factory instance
client_factory = ClientFactory()


async def get_client_factory() -> ClientFactory:
    """Get the global client factory instance."""
    if not client_factory._initialized:
        await client_factory.initialize()
    return client_factory
