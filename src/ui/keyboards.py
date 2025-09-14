"""
Inline keyboard components for the Telegram bot interface.
Provides modern, intuitive UI elements for navigation and interaction.
"""
from typing import List, Dict, Any, Optional, Callable
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from dataclasses import dataclass
from enum import Enum

from src.database.models import Channel, ForwardingMapping, User, UserRole


class CallbackAction(Enum):
    """Callback action types for inline keyboards."""
    # Main menu actions
    MAIN_MENU = "main_menu"
    BACK = "back"
    CANCEL = "cancel"
    REFRESH = "refresh"
    
    # Channel management
    CHANNELS_LIST = "channels_list"
    CHANNEL_VIEW = "channel_view"
    CHANNEL_ADD = "channel_add"
    CHANNEL_REMOVE = "channel_remove"
    CHANNEL_TOGGLE = "channel_toggle"
    CHANNEL_EDIT = "channel_edit"
    
    # Mapping management
    MAPPINGS_LIST = "mappings_list"
    MAPPING_VIEW = "mapping_view"
    MAPPING_CREATE = "mapping_create"
    MAPPING_DELETE = "mapping_delete"
    MAPPING_TOGGLE = "mapping_toggle"
    MAPPING_EDIT = "mapping_edit"
    
    # Folder/List management (legacy compatibility)
    FOLDERS_LIST = "folders_list"
    FOLDER_VIEW = "folder_view"
    LISTS_VIEW = "lists_view"
    LIST_CONFIG = "list_config"
    
    # Settings and admin
    SETTINGS = "settings"
    ADMIN_PANEL = "admin_panel"
    SYSTEM_STATUS = "system_status"
    
    # Pagination
    PAGE_PREV = "page_prev"
    PAGE_NEXT = "page_next"
    PAGE_GOTO = "page_goto"
    
    # Confirmation dialogs
    CONFIRM_YES = "confirm_yes"
    CONFIRM_NO = "confirm_no"
    
    # Multi-select
    SELECT_ITEM = "select_item"
    SELECT_ALL = "select_all"
    SELECT_NONE = "select_none"
    SELECT_DONE = "select_done"


@dataclass
class PaginationInfo:
    """Pagination information for lists."""
    current_page: int
    total_pages: int
    items_per_page: int
    total_items: int


class KeyboardBuilder:
    """Builder for creating inline keyboards with consistent styling."""
    
    def __init__(self):
        self.buttons: List[List[InlineKeyboardButton]] = []
        self.current_row: List[InlineKeyboardButton] = []
    
    def add_button(self, text: str, callback_data: str) -> 'KeyboardBuilder':
        """Add a button to the current row."""
        self.current_row.append(InlineKeyboardButton(text, callback_data=callback_data))
        return self
    
    def add_url_button(self, text: str, url: str) -> 'KeyboardBuilder':
        """Add a URL button to the current row."""
        self.current_row.append(InlineKeyboardButton(text, url=url))
        return self
    
    def new_row(self) -> 'KeyboardBuilder':
        """Start a new row of buttons."""
        if self.current_row:
            self.buttons.append(self.current_row)
            self.current_row = []
        return self
    
    def add_row(self, buttons: List[tuple]) -> 'KeyboardBuilder':
        """Add a complete row of buttons. Each tuple is (text, callback_data)."""
        self.new_row()
        for text, callback_data in buttons:
            self.add_button(text, callback_data)
        return self
    
    def build(self) -> InlineKeyboardMarkup:
        """Build the final keyboard markup."""
        if self.current_row:
            self.buttons.append(self.current_row)
        return InlineKeyboardMarkup(self.buttons)


class MainMenuKeyboard:
    """Main menu keyboard for the bot."""
    
    @staticmethod
    def create(user_role: UserRole = UserRole.USER) -> InlineKeyboardMarkup:
        """Create the main menu keyboard based on user role."""
        builder = KeyboardBuilder()
        
        # Core functionality available to all users
        builder.add_row([
            ("📺 Channels", f"{CallbackAction.CHANNELS_LIST.value}:0"),
            ("🔗 Mappings", f"{CallbackAction.MAPPINGS_LIST.value}:0")
        ])
        
        builder.add_row([
            ("📁 Folders", f"{CallbackAction.FOLDERS_LIST.value}:0"),
            ("📋 Lists", f"{CallbackAction.LISTS_VIEW.value}:0")
        ])
        
        # Settings available to all users
        builder.add_row([
            ("⚙️ Settings", CallbackAction.SETTINGS.value)
        ])
        
        # Admin-only features
        if user_role == UserRole.ADMINISTRATOR:
            builder.add_row([
                ("🛠️ Admin Panel", CallbackAction.ADMIN_PANEL.value),
                ("📊 System Status", CallbackAction.SYSTEM_STATUS.value)
            ])
        
        builder.add_row([
            ("🔄 Refresh", CallbackAction.REFRESH.value)
        ])
        
        return builder.build()


class ChannelKeyboards:
    """Keyboards for channel management."""
    
    @staticmethod
    def channels_list(channels: List[Channel], pagination: PaginationInfo, 
                     user_role: UserRole = UserRole.USER) -> InlineKeyboardMarkup:
        """Create keyboard for channels list with pagination."""
        builder = KeyboardBuilder()
        
        # Channel buttons (2 per row)
        for i in range(0, len(channels), 2):
            row_channels = channels[i:i+2]
            row_buttons = []
            
            for channel in row_channels:
                status_icon = "✅" if channel.is_active else "❌"
                access_icon = "🤖" if channel.access_type.value == "bot" else "👤"
                text = f"{status_icon}{access_icon} {channel.title[:20]}"
                callback = f"{CallbackAction.CHANNEL_VIEW.value}:{channel.id}"
                row_buttons.append((text, callback))
            
            builder.add_row(row_buttons)
        
        # Pagination controls
        if pagination.total_pages > 1:
            builder.new_row()
            if pagination.current_page > 0:
                builder.add_button("⬅️ Prev", 
                    f"{CallbackAction.PAGE_PREV.value}:{CallbackAction.CHANNELS_LIST.value}:{pagination.current_page-1}")
            
            builder.add_button(f"{pagination.current_page + 1}/{pagination.total_pages}", "noop")
            
            if pagination.current_page < pagination.total_pages - 1:
                builder.add_button("Next ➡️", 
                    f"{CallbackAction.PAGE_NEXT.value}:{CallbackAction.CHANNELS_LIST.value}:{pagination.current_page+1}")
        
        # Action buttons for admins
        if user_role == UserRole.ADMINISTRATOR:
            builder.add_row([
                ("➕ Add Channel", CallbackAction.CHANNEL_ADD.value)
            ])
        
        # Navigation
        builder.add_row([
            ("🏠 Main Menu", CallbackAction.MAIN_MENU.value),
            ("🔄 Refresh", f"{CallbackAction.CHANNELS_LIST.value}:0")
        ])
        
        return builder.build()
    
    @staticmethod
    def channel_view(channel: Channel, user_role: UserRole = UserRole.USER) -> InlineKeyboardMarkup:
        """Create keyboard for viewing a specific channel."""
        builder = KeyboardBuilder()
        
        # Channel actions for admins
        if user_role == UserRole.ADMINISTRATOR:
            toggle_text = "❌ Deactivate" if channel.is_active else "✅ Activate"
            toggle_action = f"{CallbackAction.CHANNEL_TOGGLE.value}:{channel.id}"
            
            builder.add_row([
                ("✏️ Edit", f"{CallbackAction.CHANNEL_EDIT.value}:{channel.id}"),
                (toggle_text, toggle_action)
            ])
            
            builder.add_row([
                ("🗑️ Remove", f"{CallbackAction.CHANNEL_REMOVE.value}:{channel.id}")
            ])
        
        # View mappings for this channel
        builder.add_row([
            ("🔗 View Mappings", f"{CallbackAction.MAPPINGS_LIST.value}:0:channel:{channel.id}")
        ])
        
        # Navigation
        builder.add_row([
            ("⬅️ Back", f"{CallbackAction.CHANNELS_LIST.value}:0"),
            ("🏠 Main Menu", CallbackAction.MAIN_MENU.value)
        ])
        
        return builder.build()
    
    @staticmethod
    def channel_confirmation(action: str, channel_id: int) -> InlineKeyboardMarkup:
        """Create confirmation keyboard for channel actions."""
        builder = KeyboardBuilder()
        
        builder.add_row([
            ("✅ Confirm", f"{CallbackAction.CONFIRM_YES.value}:{action}:{channel_id}"),
            ("❌ Cancel", f"{CallbackAction.CONFIRM_NO.value}:{action}:{channel_id}")
        ])
        
        return builder.build()


class MappingKeyboards:
    """Keyboards for forwarding mapping management."""
    
    @staticmethod
    def mappings_list(mappings: List[ForwardingMapping], pagination: PaginationInfo,
                     user_role: UserRole = UserRole.USER, channel_filter: Optional[int] = None) -> InlineKeyboardMarkup:
        """Create keyboard for mappings list with pagination."""
        builder = KeyboardBuilder()
        
        # Mapping buttons
        for mapping in mappings:
            status_icon = "✅" if mapping.enabled else "❌"
            mode_icon = "📤" if mapping.mode.value == "forward" else "📋"
            
            source_title = mapping.source_channel.title[:15] if mapping.source_channel else "Unknown"
            dest_title = mapping.dest_channel.title[:15] if mapping.dest_channel else "Unknown"
            
            text = f"{status_icon}{mode_icon} {source_title} → {dest_title}"
            callback = f"{CallbackAction.MAPPING_VIEW.value}:{mapping.id}"
            
            builder.add_row([(text, callback)])
        
        # Pagination controls
        if pagination.total_pages > 1:
            builder.new_row()
            if pagination.current_page > 0:
                prev_callback = f"{CallbackAction.PAGE_PREV.value}:{CallbackAction.MAPPINGS_LIST.value}:{pagination.current_page-1}"
                if channel_filter:
                    prev_callback += f":channel:{channel_filter}"
                builder.add_button("⬅️ Prev", prev_callback)
            
            builder.add_button(f"{pagination.current_page + 1}/{pagination.total_pages}", "noop")
            
            if pagination.current_page < pagination.total_pages - 1:
                next_callback = f"{CallbackAction.PAGE_NEXT.value}:{CallbackAction.MAPPINGS_LIST.value}:{pagination.current_page+1}"
                if channel_filter:
                    next_callback += f":channel:{channel_filter}"
                builder.add_button("Next ➡️", next_callback)
        
        # Action buttons for admins
        if user_role == UserRole.ADMINISTRATOR:
            builder.add_row([
                ("➕ Create Mapping", CallbackAction.MAPPING_CREATE.value)
            ])
        
        # Navigation
        back_action = CallbackAction.MAIN_MENU.value
        if channel_filter:
            back_action = f"{CallbackAction.CHANNEL_VIEW.value}:{channel_filter}"
        
        refresh_callback = f"{CallbackAction.MAPPINGS_LIST.value}:0"
        if channel_filter:
            refresh_callback += f":channel:{channel_filter}"
        
        builder.add_row([
            ("⬅️ Back", back_action),
            ("🔄 Refresh", refresh_callback)
        ])
        
        return builder.build()
    
    @staticmethod
    def mapping_view(mapping: ForwardingMapping, user_role: UserRole = UserRole.USER) -> InlineKeyboardMarkup:
        """Create keyboard for viewing a specific mapping."""
        builder = KeyboardBuilder()
        
        # Mapping actions for admins
        if user_role == UserRole.ADMINISTRATOR:
            toggle_text = "❌ Disable" if mapping.enabled else "✅ Enable"
            toggle_action = f"{CallbackAction.MAPPING_TOGGLE.value}:{mapping.id}"
            
            builder.add_row([
                ("✏️ Edit", f"{CallbackAction.MAPPING_EDIT.value}:{mapping.id}"),
                (toggle_text, toggle_action)
            ])
            
            builder.add_row([
                ("🗑️ Delete", f"{CallbackAction.MAPPING_DELETE.value}:{mapping.id}")
            ])
        
        # Navigation
        builder.add_row([
            ("⬅️ Back", f"{CallbackAction.MAPPINGS_LIST.value}:0"),
            ("🏠 Main Menu", CallbackAction.MAIN_MENU.value)
        ])
        
        return builder.build()


class AdminKeyboards:
    """Keyboards for admin panel functionality."""
    
    @staticmethod
    def admin_panel() -> InlineKeyboardMarkup:
        """Create the admin panel keyboard."""
        builder = KeyboardBuilder()
        
        builder.add_row([
            ("👥 User Management", "admin_users"),
            ("📺 Channel Management", "admin_channels")
        ])
        
        builder.add_row([
            ("🔗 Mapping Management", "admin_mappings"),
            ("📊 System Statistics", CallbackAction.SYSTEM_STATUS.value)
        ])
        
        builder.add_row([
            ("🧹 Data Cleanup", "admin_cleanup"),
            ("🔄 Reset Failed Messages", "admin_reset_failed")
        ])
        
        builder.add_row([
            ("🚀 Migration Tools", "admin_migration"),
            ("🏥 Health Check", "admin_health")
        ])
        
        builder.add_row([
            ("🏠 Main Menu", CallbackAction.MAIN_MENU.value)
        ])
        
        return builder.build()
    
    @staticmethod
    def system_status() -> InlineKeyboardMarkup:
        """Create keyboard for system status view."""
        builder = KeyboardBuilder()
        
        builder.add_row([
            ("🔄 Refresh Status", CallbackAction.SYSTEM_STATUS.value),
            ("🏥 Health Report", "admin_health")
        ])
        
        builder.add_row([
            ("⬅️ Back", CallbackAction.ADMIN_PANEL.value),
            ("🏠 Main Menu", CallbackAction.MAIN_MENU.value)
        ])
        
        return builder.build()


class SettingsKeyboards:
    """Keyboards for user settings."""
    
    @staticmethod
    def settings_menu(user_role: UserRole = UserRole.USER) -> InlineKeyboardMarkup:
        """Create the settings menu keyboard."""
        builder = KeyboardBuilder()
        
        builder.add_row([
            ("🔔 Notifications", "settings_notifications"),
            ("🎨 Interface", "settings_interface")
        ])
        
        builder.add_row([
            ("📊 Statistics", "settings_stats"),
            ("ℹ️ About", "settings_about")
        ])
        
        if user_role == UserRole.ADMINISTRATOR:
            builder.add_row([
                ("🛠️ Admin Settings", "settings_admin")
            ])
        
        builder.add_row([
            ("🏠 Main Menu", CallbackAction.MAIN_MENU.value)
        ])
        
        return builder.build()


class ConfirmationKeyboards:
    """Keyboards for confirmation dialogs."""
    
    @staticmethod
    def yes_no_confirmation(action: str, item_id: Optional[int] = None) -> InlineKeyboardMarkup:
        """Create a yes/no confirmation keyboard."""
        builder = KeyboardBuilder()
        
        yes_callback = f"{CallbackAction.CONFIRM_YES.value}:{action}"
        no_callback = f"{CallbackAction.CONFIRM_NO.value}:{action}"
        
        if item_id is not None:
            yes_callback += f":{item_id}"
            no_callback += f":{item_id}"
        
        builder.add_row([
            ("✅ Yes", yes_callback),
            ("❌ No", no_callback)
        ])
        
        return builder.build()
    
    @staticmethod
    def cancel_only() -> InlineKeyboardMarkup:
        """Create a cancel-only keyboard."""
        builder = KeyboardBuilder()
        builder.add_row([("❌ Cancel", CallbackAction.CANCEL.value)])
        return builder.build()


class MultiSelectKeyboard:
    """Keyboard for multi-select operations."""
    
    @staticmethod
    def create(items: List[Dict[str, Any]], selected_ids: List[int], 
              action_prefix: str, pagination: Optional[PaginationInfo] = None) -> InlineKeyboardMarkup:
        """Create a multi-select keyboard."""
        builder = KeyboardBuilder()
        
        # Item selection buttons
        for item in items:
            item_id = item['id']
            is_selected = item_id in selected_ids
            
            icon = "✅" if is_selected else "⬜"
            text = f"{icon} {item['title'][:25]}"
            callback = f"{CallbackAction.SELECT_ITEM.value}:{action_prefix}:{item_id}"
            
            builder.add_row([(text, callback)])
        
        # Pagination if needed
        if pagination and pagination.total_pages > 1:
            builder.new_row()
            if pagination.current_page > 0:
                builder.add_button("⬅️ Prev", 
                    f"{CallbackAction.PAGE_PREV.value}:{action_prefix}:{pagination.current_page-1}")
            
            builder.add_button(f"{pagination.current_page + 1}/{pagination.total_pages}", "noop")
            
            if pagination.current_page < pagination.total_pages - 1:
                builder.add_button("Next ➡️", 
                    f"{CallbackAction.PAGE_NEXT.value}:{action_prefix}:{pagination.current_page+1}")
        
        # Bulk selection controls
        builder.add_row([
            ("✅ Select All", f"{CallbackAction.SELECT_ALL.value}:{action_prefix}"),
            ("⬜ Select None", f"{CallbackAction.SELECT_NONE.value}:{action_prefix}")
        ])
        
        # Action buttons
        builder.add_row([
            ("✅ Done", f"{CallbackAction.SELECT_DONE.value}:{action_prefix}"),
            ("❌ Cancel", CallbackAction.CANCEL.value)
        ])
        
        return builder.build()


# Utility functions for callback data parsing
def parse_callback_data(callback_data: str) -> Dict[str, Any]:
    """Parse callback data into components."""
    parts = callback_data.split(':')
    
    result = {
        'action': parts[0] if parts else None,
        'params': parts[1:] if len(parts) > 1 else []
    }
    
    # Parse common patterns
    if len(parts) >= 2:
        try:
            result['id'] = int(parts[1])
        except (ValueError, IndexError):
            pass
    
    # Parse pagination
    if 'page' in callback_data:
        try:
            page_index = parts.index('page') + 1
            if page_index < len(parts):
                result['page'] = int(parts[page_index])
        except (ValueError, IndexError):
            pass
    
    # Parse filters
    if 'channel' in callback_data:
        try:
            channel_index = parts.index('channel') + 1
            if channel_index < len(parts):
                result['channel_filter'] = int(parts[channel_index])
        except (ValueError, IndexError):
            pass
    
    return result


def build_callback_data(action: CallbackAction, *args) -> str:
    """Build callback data string from action and arguments."""
    parts = [action.value]
    parts.extend(str(arg) for arg in args)
    return ':'.join(parts)
