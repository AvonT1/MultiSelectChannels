"""Handler registry for migrating existing bot functionality to new architecture."""

from .handler_registry import HandlerRegistry
from .legacy_migrator import LegacyHandlerMigrator

__all__ = [
    "HandlerRegistry",
    "LegacyHandlerMigrator"
]
