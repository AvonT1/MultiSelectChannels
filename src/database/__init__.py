"""Database module for the Telegram forwarding bot."""

from .models import (
    Base, User, Channel, ForwardingMapping, MessageLog, 
    DeduplicationCache, FloodWaitLog, LegacyFolder, LegacyList,
    AccessType, ForwardingMode, MessageStatus, UserRole
)
from .connection import DatabaseManager, get_db_session

__all__ = [
    "Base",
    "User", 
    "Channel",
    "ForwardingMapping",
    "MessageLog",
    "DeduplicationCache", 
    "FloodWaitLog",
    "LegacyFolder",
    "LegacyList",
    "AccessType",
    "ForwardingMode", 
    "MessageStatus",
    "UserRole",
    "DatabaseManager",
    "get_db_session"
]
