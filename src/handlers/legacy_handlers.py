"""
Legacy handler migrator for preserving existing bot functionality.
Adapts the current SQLite-based handlers to work with the new architecture.
"""
import logging
from typing import Dict, Any, Optional

from telegram import Update
from telegram.ext import ContextTypes, Application

from src.clients import ClientFactory
from src.database import get_db_session

logger = logging.getLogger(__name__)


class LegacyHandlerMigrator:
    """Migrates and adapts existing bot handlers to new architecture."""
    
    def __init__(self, client_factory: ClientFactory):
        self.client_factory = client_factory
        self.user_states: Dict[str, str] = {}
        self.user_search_cache: Dict[str, Any] = {}
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the legacy handler migrator."""
        if self._initialized:
            return
        
        logger.info("Initializing legacy handler migrator...")
        
        # Initialize state tracking
        self.user_states = {}
        self.user_search_cache = {}
        
        self._initialized = True
        logger.info("Legacy handler migrator initialized")
    
    async def register_legacy_handlers(self, application: Application) -> None:
        """Register legacy handlers with the bot application."""
        logger.info("Registering legacy handlers...")
        
        # The legacy handlers will be integrated through the callback and message handlers
        # in the main handler registry. This method can be used for any additional
        # legacy-specific handler registration if needed.
        
        logger.info("Legacy handlers registered")
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle callback queries using legacy logic adapted for new architecture."""
        query = update.callback_query
        data = query.data
        user_id = query.from_user.id
        message = query.message
        
        logger.debug(f"Legacy callback handler: {data} from user {user_id}")
        
        # Parse callback data
        parts = data.split(':')
        action = parts[0]
        
        # Handle different callback actions
        if action == "noop":
            return
        
        # Main menu actions
        elif action == "main_menu":
            await self._show_main_menu(query, message)
        
        elif action == "manage_lists_root":
            await self._show_lists_management(query, message)
        
        # Legacy folder and list management
        elif action in ["view_folder", "create_folder_start", "rename_folder_start", "delete_folder_start"]:
            await self._handle_folder_actions(query, action, parts)
        
        elif action in ["config_list", "create_list_start", "rename_list_start", "delete_list_start"]:
            await self._handle_list_actions(query, action, parts)
        
        # Source and destination management
        elif action in ["add_sources_start", "add_dest_start", "config_dests"]:
            await self._handle_channel_management(query, action, parts)
        
        # Other legacy actions
        else:
            logger.warning(f"Unhandled legacy callback action: {action}")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle text messages using legacy state logic."""
        user_id = update.effective_user.id
        state_key = str(user_id)
        text = update.message.text.strip()
        
        if state_key not in self.user_states or not text:
            return
        
        logger.debug(f"Legacy message handler: user {user_id} in state {self.user_states[state_key]}")
        
        # Handle different user states
        state = self.user_states[state_key]
        parts = state.split(':')
        action = parts[0]
        
        if action == "waiting_for_folder_name":
            await self._handle_folder_name_input(update, text)
        
        elif action == "waiting_for_list_name":
            await self._handle_list_name_input(update, text, parts)
        
        elif action == "waiting_for_search_query":
            await self._handle_search_query_input(update, text, parts)
        
        elif action == "waiting_for_link":
            await self._handle_link_input(update, text, parts)
        
        else:
            logger.warning(f"Unhandled legacy message state: {action}")
    
    async def _show_main_menu(self, query, message) -> None:
        """Show the main menu (legacy compatible)."""
        menu_text = """🤖 **Telegram Forwarding Bot**

**Main Menu:**
• 📁 Manage forwarding lists
• ⚙️ System settings
• 📊 Statistics
• ℹ️ Help

Choose an option below:"""
        
        # TODO: Create main menu keyboard
        await message.edit_text(menu_text, parse_mode='Markdown')
    
    async def _show_lists_management(self, query, message) -> None:
        """Show lists management interface (legacy compatible)."""
        # This would integrate with the new database schema
        # For now, show a placeholder
        
        lists_text = """📁 **Forwarding Lists Management**

**Available Operations:**
• Create new forwarding list
• Edit existing lists
• Manage source channels
• Configure destination channels
• Set forwarding modes

**Migration Notice:**
Your existing lists from the SQLite database will be migrated to the new PostgreSQL schema automatically."""
        
        # TODO: Create lists management keyboard
        await message.edit_text(lists_text, parse_mode='Markdown')
    
    async def _handle_folder_actions(self, query, action: str, parts: list) -> None:
        """Handle folder-related actions (legacy compatible)."""
        logger.info(f"Handling folder action: {action}")
        
        # Placeholder for folder management logic
        # This would need to be adapted to work with the new database schema
        
        await query.answer("Folder management will be available after migration.")
    
    async def _handle_list_actions(self, query, action: str, parts: list) -> None:
        """Handle list-related actions (legacy compatible)."""
        logger.info(f"Handling list action: {action}")
        
        # Placeholder for list management logic
        # This would need to be adapted to work with the new database schema
        
        await query.answer("List management will be available after migration.")
    
    async def _handle_channel_management(self, query, action: str, parts: list) -> None:
        """Handle channel management actions (legacy compatible)."""
        logger.info(f"Handling channel action: {action}")
        
        # This would integrate with the new Channel and ForwardingMapping models
        
        await query.answer("Channel management will be available after migration.")
    
    async def _handle_folder_name_input(self, update, text: str) -> None:
        """Handle folder name input (legacy compatible)."""
        user_id = update.effective_user.id
        
        # Remove user from state
        self.user_states.pop(str(user_id), None)
        
        # TODO: Create folder in new database schema
        await update.message.reply_text(f"✅ Folder '{text}' will be created after migration.")
        await update.message.delete()
    
    async def _handle_list_name_input(self, update, text: str, parts: list) -> None:
        """Handle list name input (legacy compatible)."""
        user_id = update.effective_user.id
        
        # Remove user from state
        self.user_states.pop(str(user_id), None)
        
        # TODO: Create list in new database schema
        await update.message.reply_text(f"✅ List '{text}' will be created after migration.")
        await update.message.delete()
    
    async def _handle_search_query_input(self, update, text: str, parts: list) -> None:
        """Handle search query input (legacy compatible)."""
        user_id = update.effective_user.id
        
        # Remove user from state
        self.user_states.pop(str(user_id), None)
        
        # Use the new user client for searching
        try:
            dialogs = await self.client_factory.user_client.get_dialogs(limit=100)
            
            # Filter dialogs based on search query
            search_results = [
                dialog for dialog in dialogs 
                if text.lower() in dialog['title'].lower()
            ]
            
            self.user_search_cache[str(user_id)] = search_results
            
            result_text = f"🔍 Found {len(search_results)} results for '{text}'"
            if search_results:
                result_text += "\n\nTop results:\n"
                for i, dialog in enumerate(search_results[:5]):
                    result_text += f"{i+1}. {dialog['title']} ({dialog['type']})\n"
            
            await update.message.reply_text(result_text)
            
        except Exception as e:
            logger.error(f"Error in search: {e}")
            await update.message.reply_text("❌ Search failed. Please try again.")
        
        await update.message.delete()
    
    async def _handle_link_input(self, update, text: str, parts: list) -> None:
        """Handle link/ID input (legacy compatible)."""
        user_id = update.effective_user.id
        
        # Remove user from state
        self.user_states.pop(str(user_id), None)
        
        # Use the new user client to get chat info
        try:
            chat_info = await self.client_factory.user_client.get_entity_info(text)
            
            if chat_info:
                await update.message.reply_text(
                    f"✅ Found: {chat_info['title']} ({chat_info['type']})\n"
                    f"This channel will be added after migration."
                )
            else:
                await update.message.reply_text("❌ Could not find or access this chat.")
                
        except Exception as e:
            logger.error(f"Error getting chat info: {e}")
            await update.message.reply_text("❌ Failed to get chat information.")
        
        await update.message.delete()
    
    def set_user_state(self, user_id: int, state: str) -> None:
        """Set user state for input handling."""
        self.user_states[str(user_id)] = state
    
    def get_user_state(self, user_id: int) -> Optional[str]:
        """Get current user state."""
        return self.user_states.get(str(user_id))
    
    def clear_user_state(self, user_id: int) -> None:
        """Clear user state."""
        self.user_states.pop(str(user_id), None)
