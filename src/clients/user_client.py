"""
User client manager using Telethon for MTProto access.
Handles private channels, user session, and advanced message operations.
"""
import logging
from typing import Optional, Dict, Any, List, Union
from pathlib import Path

from telethon import TelegramClient, events
from telethon.errors import (
    FloodWaitError, ChannelPrivateError, PeerIdInvalidError, 
    SessionPasswordNeededError, PhoneCodeInvalidError
)
from telethon.tl.types import (
    Channel, Chat, User as TelethonUser, Message,
    PeerChannel, PeerChat, PeerUser
)

from src.config import settings
from src.database import get_db_session, FloodWaitLog

logger = logging.getLogger(__name__)


class UserClientManager:
    """Manages the Telethon user client for MTProto operations."""
    
    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self._is_running = False
        self._message_handlers = []
    
    async def initialize(self) -> None:
        """Initialize the Telethon user client."""
        logger.info("Initializing Telethon user client...")
        
        # Ensure session directory exists
        session_path = settings.user_session_file_path
        session_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create client
        self.client = TelegramClient(
            str(session_path.with_suffix('')),  # Remove .session extension
            settings.api_id,
            settings.api_hash,
            device_model="Forwarding Bot",
            system_version="1.0",
            app_version="1.0.0"
        )
        
        # Register event handlers
        await self._register_event_handlers()
        
        logger.info("Telethon user client initialized successfully")
    
    async def _register_event_handlers(self) -> None:
        """Register Telethon event handlers for message capture."""
        if not self.client:
            return
        
        @self.client.on(events.NewMessage)
        async def new_message_handler(event):
            """Handle new messages from monitored channels."""
            try:
                await self._handle_new_message(event)
            except Exception as e:
                logger.error(f"Error handling new message: {e}", exc_info=True)
        
        self._message_handlers.append(new_message_handler)
    
    async def _handle_new_message(self, event) -> None:
        """Process new messages for forwarding."""
        message = event.message
        chat = await event.get_chat()
        
        # Skip if not from a channel/group we monitor
        if not hasattr(chat, 'id'):
            return
        
        logger.debug(f"New message from {chat.id}: {message.id}")
        
        # TODO: Check if this channel is in our forwarding mappings
        # TODO: Queue message for forwarding processing
        # This will be implemented in the forwarding core
    
    async def start(self) -> None:
        """Start the user client and authenticate if needed."""
        if not self.client:
            await self.initialize()
        
        logger.info("Starting Telethon user client...")
        
        try:
            await self.client.start()
            
            # Check if we're authorized
            if not await self.client.is_user_authorized():
                logger.error("User client not authorized. Please run authentication setup.")
                return
            
            self._is_running = True
            logger.info("Telethon user client started successfully")
            
            # Log user info
            me = await self.client.get_me()
            logger.info(f"Logged in as: {me.first_name} (@{me.username or 'no_username'})")
            
        except Exception as e:
            logger.error(f"Failed to start user client: {e}")
            raise
    
    async def stop(self) -> None:
        """Stop the user client."""
        if self.client and self._is_running:
            logger.info("Stopping Telethon user client...")
            await self.client.disconnect()
            self._is_running = False
            logger.info("Telethon user client stopped")
    
    async def authenticate_user(self, phone: str) -> Dict[str, Any]:
        """Authenticate user with phone number (interactive setup)."""
        if not self.client:
            await self.initialize()
        
        try:
            await self.client.connect()
            
            if await self.client.is_user_authorized():
                return {"status": "already_authorized", "message": "User already authenticated"}
            
            # Send code request
            sent_code = await self.client.send_code_request(phone)
            
            return {
                "status": "code_sent",
                "phone_code_hash": sent_code.phone_code_hash,
                "message": "Verification code sent to your phone"
            }
            
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return {"status": "error", "message": str(e)}
    
    async def verify_code(self, phone: str, code: str, phone_code_hash: str, password: Optional[str] = None) -> Dict[str, Any]:
        """Verify authentication code and complete login."""
        if not self.client:
            return {"status": "error", "message": "Client not initialized"}
        
        try:
            await self.client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            return {"status": "success", "message": "Authentication successful"}
            
        except SessionPasswordNeededError:
            if password:
                try:
                    await self.client.sign_in(password=password)
                    return {"status": "success", "message": "Authentication successful"}
                except Exception as e:
                    return {"status": "error", "message": f"2FA password error: {e}"}
            else:
                return {"status": "2fa_required", "message": "2FA password required"}
                
        except PhoneCodeInvalidError:
            return {"status": "error", "message": "Invalid verification code"}
        except Exception as e:
            logger.error(f"Code verification error: {e}")
            return {"status": "error", "message": str(e)}
    
    async def get_dialogs(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get user's dialogs (chats, channels, groups)."""
        if not self.client or not self._is_running:
            return []
        
        try:
            dialogs = []
            async for dialog in self.client.iter_dialogs(limit=limit):
                entity = dialog.entity
                
                dialog_info = {
                    'id': entity.id,
                    'title': getattr(entity, 'title', None) or getattr(entity, 'first_name', 'Unknown'),
                    'type': 'channel' if isinstance(entity, Channel) else 'chat' if isinstance(entity, Chat) else 'user',
                    'username': getattr(entity, 'username', None),
                    'is_private': getattr(entity, 'megagroup', False) if isinstance(entity, Channel) else False,
                    'participant_count': getattr(entity, 'participants_count', None),
                    'unread_count': dialog.unread_count
                }
                dialogs.append(dialog_info)
            
            return dialogs
            
        except Exception as e:
            logger.error(f"Error getting dialogs: {e}")
            return []
    
    async def get_entity_info(self, entity_id: Union[int, str]) -> Optional[Dict[str, Any]]:
        """Get information about a specific entity (channel, chat, user)."""
        if not self.client or not self._is_running:
            return None
        
        try:
            entity = await self.client.get_entity(entity_id)
            
            return {
                'id': entity.id,
                'title': getattr(entity, 'title', None) or getattr(entity, 'first_name', 'Unknown'),
                'type': 'channel' if isinstance(entity, Channel) else 'chat' if isinstance(entity, Chat) else 'user',
                'username': getattr(entity, 'username', None),
                'is_private': getattr(entity, 'megagroup', False) if isinstance(entity, Channel) else False,
                'participant_count': getattr(entity, 'participants_count', None),
                'access_hash': getattr(entity, 'access_hash', None)
            }
            
        except (PeerIdInvalidError, ChannelPrivateError, ValueError) as e:
            logger.warning(f"Cannot access entity {entity_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error getting entity info for {entity_id}: {e}")
            return None
    
    async def send_message(self, chat_id: int, text: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Send a message via user client."""
        if not self.client or not self._is_running:
            logger.error("User client not running")
            return None
        
        try:
            message = await self.client.send_message(chat_id, text, **kwargs)
            return {
                'message_id': message.id,
                'chat_id': message.peer_id.channel_id if hasattr(message.peer_id, 'channel_id') else chat_id,
                'date': message.date
            }
        except FloodWaitError as e:
            await self._log_flood_wait('send_message', e.seconds, chat_id)
            logger.warning(f"FloodWait on send_message: {e.seconds} seconds")
            return None
        except Exception as e:
            logger.error(f"Failed to send message via user client: {e}")
            return None
    
    async def forward_message(self, to_chat: int, from_chat: int, message_id: int, **kwargs) -> Optional[Dict[str, Any]]:
        """Forward a message via user client."""
        if not self.client or not self._is_running:
            logger.error("User client not running")
            return None
        
        try:
            messages = await self.client.forward_messages(to_chat, message_id, from_chat, **kwargs)
            if messages:
                message = messages[0]
                return {
                    'message_id': message.id,
                    'chat_id': message.peer_id.channel_id if hasattr(message.peer_id, 'channel_id') else to_chat,
                    'date': message.date
                }
            return None
        except FloodWaitError as e:
            await self._log_flood_wait('forward_message', e.seconds, to_chat)
            logger.warning(f"FloodWait on forward_message: {e.seconds} seconds")
            return None
        except Exception as e:
            logger.error(f"Failed to forward message via user client: {e}")
            return None
    
    async def copy_message(self, to_chat: int, from_chat: int, message_id: int, **kwargs) -> Optional[Dict[str, Any]]:
        """Copy a message (send without forward header) via user client."""
        if not self.client or not self._is_running:
            logger.error("User client not running")
            return None
        
        try:
            # Get the original message
            message = await self.client.get_messages(from_chat, ids=message_id)
            if not message:
                return None
            
            # Send as new message (copy content)
            sent_message = await self.client.send_message(
                to_chat,
                message.text or message.raw_text or "",
                file=message.media if message.media else None,
                **kwargs
            )
            
            return {
                'message_id': sent_message.id,
                'chat_id': sent_message.peer_id.channel_id if hasattr(sent_message.peer_id, 'channel_id') else to_chat,
                'date': sent_message.date
            }
        except FloodWaitError as e:
            await self._log_flood_wait('copy_message', e.seconds, to_chat)
            logger.warning(f"FloodWait on copy_message: {e.seconds} seconds")
            return None
        except Exception as e:
            logger.error(f"Failed to copy message via user client: {e}")
            return None
    
    async def get_messages(self, chat_id: int, message_ids: Union[int, List[int]], **kwargs) -> List[Dict[str, Any]]:
        """Get messages from a chat."""
        if not self.client or not self._is_running:
            return []
        
        try:
            messages = await self.client.get_messages(chat_id, ids=message_ids, **kwargs)
            if not isinstance(messages, list):
                messages = [messages] if messages else []
            
            result = []
            for msg in messages:
                if msg:
                    result.append({
                        'id': msg.id,
                        'text': msg.text or msg.raw_text or "",
                        'date': msg.date,
                        'media': bool(msg.media),
                        'from_id': msg.from_id.user_id if msg.from_id else None
                    })
            
            return result
        except Exception as e:
            logger.error(f"Error getting messages: {e}")
            return []
    
    async def check_chat_access(self, chat_id: int) -> Dict[str, Any]:
        """Check if user client has access to a specific chat."""
        try:
            entity = await self.get_entity_info(chat_id)
            if entity:
                return {"has_access": True, "entity": entity}
            else:
                return {"has_access": False, "error": "Cannot access chat"}
        except Exception as e:
            return {"has_access": False, "error": str(e)}
    
    async def _log_flood_wait(self, operation_type: str, wait_duration: int, channel_id: Optional[int] = None) -> None:
        """Log FloodWait incident to database."""
        try:
            async with get_db_session() as session:
                flood_log = FloodWaitLog(
                    client_type="user",
                    wait_duration=wait_duration,
                    operation_type=operation_type,
                    channel_id=channel_id
                )
                session.add(flood_log)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to log FloodWait: {e}")
    
    @property
    def is_running(self) -> bool:
        """Check if user client is currently running."""
        return self._is_running
    
    @property
    def is_authorized(self) -> bool:
        """Check if user client is authorized."""
        if not self.client:
            return False
        try:
            return self.client.is_connected() and self._is_running
        except:
            return False
