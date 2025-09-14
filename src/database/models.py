"""
SQLAlchemy 2.0 models for the enhanced Telegram forwarding bot.
Implements the comprehensive data model with channels, mappings, message logs, and users.
"""
import enum
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import (
    BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, 
    JSON, String, Text, UniqueConstraint, Index
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class AccessType(enum.Enum):
    """Channel access type enumeration."""
    BOT = "bot"
    USER = "user"


class ForwardingMode(enum.Enum):
    """Message forwarding mode enumeration."""
    FORWARD = "forward"  # Preserve original author/forward header
    COPY = "copy"       # Copy content without forward header


class MessageStatus(enum.Enum):
    """Message processing status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


class UserRole(enum.Enum):
    """User role enumeration."""
    ADMINISTRATOR = "administrator"
    OPERATOR = "operator"


class User(Base):
    """User model for bot administrators and operators."""
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False, default=UserRole.OPERATOR)
    session_encrypted_pointer: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    added_channels: Mapped[List["Channel"]] = relationship("Channel", back_populates="added_by_user")


class Channel(Base):
    """Channel model for source and destination channels."""
    __tablename__ = "channels"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    access_type: Mapped[AccessType] = mapped_column(Enum(AccessType), nullable=False)
    last_processed_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    added_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    added_by_user: Mapped[User] = relationship("User", back_populates="added_channels")
    source_mappings: Mapped[List["ForwardingMapping"]] = relationship(
        "ForwardingMapping", 
        foreign_keys="ForwardingMapping.source_channel_id",
        back_populates="source_channel"
    )
    dest_mappings: Mapped[List["ForwardingMapping"]] = relationship(
        "ForwardingMapping",
        foreign_keys="ForwardingMapping.dest_channel_id", 
        back_populates="dest_channel"
    )
    source_messages: Mapped[List["MessageLog"]] = relationship("MessageLog", back_populates="source_channel")


class ForwardingMapping(Base):
    """Mapping between source and destination channels."""
    __tablename__ = "mappings"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_channel_id: Mapped[int] = mapped_column(Integer, ForeignKey("channels.id"), nullable=False)
    dest_channel_id: Mapped[int] = mapped_column(Integer, ForeignKey("channels.id"), nullable=False)
    mode: Mapped[ForwardingMode] = mapped_column(Enum(ForwardingMode), nullable=False, default=ForwardingMode.FORWARD)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    source_channel: Mapped[Channel] = relationship(
        "Channel", 
        foreign_keys=[source_channel_id],
        back_populates="source_mappings"
    )
    dest_channel: Mapped[Channel] = relationship(
        "Channel",
        foreign_keys=[dest_channel_id],
        back_populates="dest_mappings"
    )
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('source_channel_id', 'dest_channel_id', name='unique_mapping'),
        Index('idx_source_enabled', 'source_channel_id', 'enabled'),
    )


class MessageLog(Base):
    """Log of processed messages with status tracking."""
    __tablename__ = "messages_log"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_channel_id: Mapped[int] = mapped_column(Integer, ForeignKey("channels.id"), nullable=False)
    source_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dest_channel_ids: Mapped[List[int]] = mapped_column(JSON, nullable=False)  # Array of destination channel IDs
    status: Mapped[MessageStatus] = mapped_column(Enum(MessageStatus), nullable=False, default=MessageStatus.PENDING)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    forwarded_message_ids: Mapped[Optional[Dict[str, int]]] = mapped_column(JSON, nullable=True)  # {dest_channel_id: forwarded_msg_id}
    processing_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    source_channel: Mapped[Channel] = relationship("Channel", back_populates="source_messages")
    
    # Constraints and Indexes
    __table_args__ = (
        UniqueConstraint('source_channel_id', 'source_message_id', name='unique_source_message'),
        Index('idx_status_attempts', 'status', 'attempts'),
        Index('idx_created_at', 'created_at'),
    )


class DeduplicationCache(Base):
    """Cache for message deduplication using content hashes."""
    __tablename__ = "deduplication_cache"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    source_channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # TTL index for automatic cleanup (PostgreSQL specific)
    __table_args__ = (
        Index('idx_created_at_ttl', 'created_at'),
    )


class FloodWaitLog(Base):
    """Log of FloodWait exceptions for monitoring and analysis."""
    __tablename__ = "flood_wait_log"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'bot' or 'user'
    wait_duration: Mapped[int] = mapped_column(Integer, nullable=False)  # Seconds to wait
    operation_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'forward_message', 'copy_message', etc.
    channel_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Indexes
    __table_args__ = (
        Index('idx_client_type_created', 'client_type', 'created_at'),
        Index('idx_resolved_at', 'resolved_at'),
    )


# Legacy compatibility models for migration
class LegacyFolder(Base):
    """Legacy folder model for migration from SQLite."""
    __tablename__ = "legacy_folders"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    migrated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LegacyList(Base):
    """Legacy forwarding list model for migration from SQLite."""
    __tablename__ = "legacy_lists"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    folder_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    migrated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
