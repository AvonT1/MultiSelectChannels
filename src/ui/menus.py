"""
Menu components and message formatters for the Telegram bot interface.
Provides consistent message formatting and menu structures.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from telegram import InlineKeyboardMarkup

from src.database.models import Channel, ForwardingMapping, User, UserRole, AccessType, ForwardingMode
from src.ui.keyboards import (
    MainMenuKeyboard, ChannelKeyboards, MappingKeyboards, 
    AdminKeyboards, SettingsKeyboards, PaginationInfo
)


class MenuFormatter:
    """Formats messages and creates menu interfaces."""
    
    @staticmethod
    def format_main_menu(user: User) -> tuple[str, InlineKeyboardMarkup]:
        """Format the main menu message and keyboard."""
        greeting = f"👋 Welcome, {user.username or 'User'}!"
        
        if user.role == UserRole.ADMINISTRATOR:
            greeting += " (Administrator)"
        
        message = f"""
{greeting}

🤖 **Telegram Forwarding Bot**

Choose an option from the menu below:

📺 **Channels** - Manage source and destination channels
🔗 **Mappings** - Configure forwarding rules
📁 **Folders** - Organize your forwarding lists
📋 **Lists** - View and manage forwarding lists
⚙️ **Settings** - Configure your preferences

{f"🛠️ **Admin Panel** - System administration" if user.role == UserRole.ADMINISTRATOR else ""}

🔄 Use the refresh button to update data
        """
        
        keyboard = MainMenuKeyboard.create(user.role)
        return message.strip(), keyboard
    
    @staticmethod
    def format_channels_list(channels: List[Channel], pagination: PaginationInfo, 
                           user_role: UserRole = UserRole.USER) -> tuple[str, InlineKeyboardMarkup]:
        """Format the channels list message and keyboard."""
        if not channels:
            message = """
📺 **Channel Management**

No channels configured yet.

Channels are the source and destination endpoints for message forwarding. You need to add channels before creating forwarding mappings.
            """
        else:
            active_count = sum(1 for ch in channels if ch.is_active)
            bot_access_count = sum(1 for ch in channels if ch.access_type == AccessType.BOT)
            user_access_count = sum(1 for ch in channels if ch.access_type == AccessType.USER)
            
            message = f"""
📺 **Channel Management**

**Statistics:**
• Total Channels: {pagination.total_items}
• Active: {active_count} | Inactive: {pagination.total_items - active_count}
• Bot Access: {bot_access_count} | User Access: {user_access_count}

**Page {pagination.current_page + 1} of {pagination.total_pages}**

Select a channel to view details:
            """
        
        keyboard = ChannelKeyboards.channels_list(channels, pagination, user_role)
        return message.strip(), keyboard
    
    @staticmethod
    def format_channel_view(channel: Channel, user_role: UserRole = UserRole.USER) -> tuple[str, InlineKeyboardMarkup]:
        """Format individual channel view message and keyboard."""
        status_icon = "✅ Active" if channel.is_active else "❌ Inactive"
        access_icon = "🤖 Bot Access" if channel.access_type == AccessType.BOT else "👤 User Access"
        
        # Get mapping counts (would need to be passed in or queried)
        source_mappings = len(channel.source_mappings) if hasattr(channel, 'source_mappings') else 0
        dest_mappings = len(channel.dest_mappings) if hasattr(channel, 'dest_mappings') else 0
        
        message = f"""
📺 **Channel Details**

**{channel.title}**
ID: `{channel.telegram_id}`

**Status:** {status_icon}
**Access Type:** {access_icon}
**Added:** {channel.created_at.strftime('%Y-%m-%d %H:%M')}

**Forwarding Statistics:**
• Source for {source_mappings} mappings
• Destination for {dest_mappings} mappings

{f"**Last Message:** {channel.last_processed_message_id}" if channel.last_processed_message_id else ""}

{f"**Metadata:** {channel.metadata}" if channel.metadata else ""}
        """
        
        keyboard = ChannelKeyboards.channel_view(channel, user_role)
        return message.strip(), keyboard
    
    @staticmethod
    def format_mappings_list(mappings: List[ForwardingMapping], pagination: PaginationInfo,
                           user_role: UserRole = UserRole.USER, 
                           channel_filter: Optional[Channel] = None) -> tuple[str, InlineKeyboardMarkup]:
        """Format the mappings list message and keyboard."""
        if not mappings:
            if channel_filter:
                message = f"""
🔗 **Mappings for {channel_filter.title}**

No forwarding mappings configured for this channel.

Create mappings to start forwarding messages between channels.
                """
            else:
                message = """
🔗 **Forwarding Mappings**

No forwarding mappings configured yet.

Mappings define how messages are forwarded from source channels to destination channels.
                """
        else:
            enabled_count = sum(1 for m in mappings if m.enabled)
            forward_count = sum(1 for m in mappings if m.mode == ForwardingMode.FORWARD)
            copy_count = sum(1 for m in mappings if m.mode == ForwardingMode.COPY)
            
            title = f"🔗 **Mappings for {channel_filter.title}**" if channel_filter else "🔗 **Forwarding Mappings**"
            
            message = f"""
{title}

**Statistics:**
• Total Mappings: {pagination.total_items}
• Enabled: {enabled_count} | Disabled: {pagination.total_items - enabled_count}
• Forward Mode: {forward_count} | Copy Mode: {copy_count}

**Page {pagination.current_page + 1} of {pagination.total_pages}**

Select a mapping to view details:
            """
        
        keyboard = MappingKeyboards.mappings_list(mappings, pagination, user_role, 
                                                channel_filter.id if channel_filter else None)
        return message.strip(), keyboard
    
    @staticmethod
    def format_mapping_view(mapping: ForwardingMapping, user_role: UserRole = UserRole.USER) -> tuple[str, InlineKeyboardMarkup]:
        """Format individual mapping view message and keyboard."""
        status_icon = "✅ Enabled" if mapping.enabled else "❌ Disabled"
        mode_icon = "📤 Forward" if mapping.mode == ForwardingMode.FORWARD else "📋 Copy"
        
        source_title = mapping.source_channel.title if mapping.source_channel else "Unknown Channel"
        dest_title = mapping.dest_channel.title if mapping.dest_channel else "Unknown Channel"
        
        message = f"""
🔗 **Mapping Details**

**Source:** {source_title}
**Destination:** {dest_title}

**Status:** {status_icon}
**Mode:** {mode_icon}
**Created:** {mapping.created_at.strftime('%Y-%m-%d %H:%M')}

**Mode Explanation:**
• **Forward:** Preserves original author and channel info
• **Copy:** Copies message content as if sent by the bot

**Statistics:**
• Messages processed: {getattr(mapping, 'messages_processed', 0)}
• Last activity: {getattr(mapping, 'last_activity', 'Never')}
        """
        
        keyboard = MappingKeyboards.mapping_view(mapping, user_role)
        return message.strip(), keyboard
    
    @staticmethod
    def format_admin_panel() -> tuple[str, InlineKeyboardMarkup]:
        """Format the admin panel message and keyboard."""
        message = """
🛠️ **Administrator Panel**

Welcome to the system administration panel. Here you can manage users, channels, mappings, and monitor system health.

**Available Tools:**
• **User Management** - Create admins, manage user roles
• **Channel Management** - Add/remove channels, bulk operations
• **Mapping Management** - Create/modify forwarding rules
• **System Statistics** - View performance metrics
• **Data Cleanup** - Remove old logs and cache entries
• **Reset Failed Messages** - Retry failed forwarding attempts
• **Migration Tools** - Database migration utilities
• **Health Check** - System integrity validation

⚠️ **Warning:** Admin actions can affect system operation. Use with caution.
        """
        
        keyboard = AdminKeyboards.admin_panel()
        return message.strip(), keyboard
    
    @staticmethod
    def format_system_status(stats: Dict[str, Any]) -> tuple[str, InlineKeyboardMarkup]:
        """Format system status message and keyboard."""
        if not stats.get('success'):
            message = f"""
📊 **System Status**

❌ **Error loading system statistics**

{stats.get('error', 'Unknown error occurred')}

Try refreshing or check system logs for more details.
            """
        else:
            system_stats = stats['stats']
            recent_messages = system_stats.get('recent_24h_messages', {})
            
            message = f"""
📊 **System Status**

**Database Statistics:**
• Users: {system_stats.get('total_users', 0)}
• Channels: {system_stats.get('total_channels', 0)}
• Total Mappings: {system_stats.get('total_mappings', 0)}
• Active Mappings: {system_stats.get('active_mappings', 0)}

**Channel Access Types:**
{MenuFormatter._format_dict_stats(system_stats.get('channels_by_access', {}))}

**Mapping Modes:**
{MenuFormatter._format_dict_stats(system_stats.get('mappings_by_mode', {}))}

**Recent Activity (24h):**
{MenuFormatter._format_dict_stats(recent_messages) if recent_messages else "• No recent activity"}

**Generated:** {system_stats.get('generated_at', 'Unknown')}
            """
        
        keyboard = AdminKeyboards.system_status()
        return message.strip(), keyboard
    
    @staticmethod
    def format_settings_menu(user_role: UserRole = UserRole.USER) -> tuple[str, InlineKeyboardMarkup]:
        """Format the settings menu message and keyboard."""
        message = """
⚙️ **Settings**

Configure your bot preferences and view account information.

**Available Options:**
• **Notifications** - Configure alert preferences
• **Interface** - Customize display options
• **Statistics** - View your usage statistics
• **About** - Bot information and version

{f"• **Admin Settings** - Administrative preferences" if user_role == UserRole.ADMINISTRATOR else ""}

Select an option to continue:
        """
        
        keyboard = SettingsKeyboards.settings_menu(user_role)
        return message.strip(), keyboard
    
    @staticmethod
    def format_confirmation_dialog(action: str, item_name: str, 
                                 warning: Optional[str] = None) -> str:
        """Format a confirmation dialog message."""
        message = f"""
⚠️ **Confirmation Required**

Are you sure you want to **{action}** the following item?

**{item_name}**

{f"⚠️ **Warning:** {warning}" if warning else ""}

This action cannot be undone. Please confirm your choice:
        """
        
        return message.strip()
    
    @staticmethod
    def format_error_message(error: str, context: Optional[str] = None) -> str:
        """Format an error message."""
        message = f"""
❌ **Error**

{error}

{f"**Context:** {context}" if context else ""}

Please try again or contact an administrator if the problem persists.
        """
        
        return message.strip()
    
    @staticmethod
    def format_success_message(message: str, details: Optional[str] = None) -> str:
        """Format a success message."""
        formatted = f"""
✅ **Success**

{message}

{details if details else ""}
        """
        
        return formatted.strip()
    
    @staticmethod
    def _format_dict_stats(stats_dict: Dict[str, Any]) -> str:
        """Helper to format dictionary statistics."""
        if not stats_dict:
            return "• No data available"
        
        lines = []
        for key, value in stats_dict.items():
            formatted_key = key.replace('_', ' ').title()
            lines.append(f"• {formatted_key}: {value}")
        
        return '\n'.join(lines)


class LegacyMenuFormatter:
    """Formatter for legacy menu compatibility."""
    
    @staticmethod
    def format_folders_list(folders: List[Dict[str, Any]], pagination: PaginationInfo) -> tuple[str, InlineKeyboardMarkup]:
        """Format legacy folders list for backward compatibility."""
        message = """
📁 **Folders**

Legacy folder view for backward compatibility.

Note: The system has been upgraded to use Channels and Mappings. This view shows your migrated folder structure.

Use the new Channel and Mapping management for better functionality.
        """
        
        # Create a simple keyboard for now
        from src.ui.keyboards import KeyboardBuilder, CallbackAction
        builder = KeyboardBuilder()
        builder.add_row([("🏠 Main Menu", CallbackAction.MAIN_MENU.value)])
        keyboard = builder.build()
        
        return message.strip(), keyboard
    
    @staticmethod
    def format_lists_view(lists: List[Dict[str, Any]], pagination: PaginationInfo) -> tuple[str, InlineKeyboardMarkup]:
        """Format legacy lists view for backward compatibility."""
        message = """
📋 **Lists**

Legacy list view for backward compatibility.

Note: The system has been upgraded to use Channels and Mappings. This view shows your migrated list structure.

Use the new Channel and Mapping management for better functionality.
        """
        
        # Create a simple keyboard for now
        from src.ui.keyboards import KeyboardBuilder, CallbackAction
        builder = KeyboardBuilder()
        builder.add_row([("🏠 Main Menu", CallbackAction.MAIN_MENU.value)])
        keyboard = builder.build()
        
        return message.strip(), keyboard
