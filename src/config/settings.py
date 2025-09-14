"""
Enhanced configuration management with Pydantic settings.
Supports environment variables and secure credential handling.
"""
import os
from pathlib import Path
from typing import List, Optional
from pydantic import Field, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with validation and type safety."""
    
    # Telegram API Configuration
    api_id: int = Field(..., description="Telegram API ID from my.telegram.org")
    api_hash: str = Field(..., description="Telegram API Hash from my.telegram.org")
    bot_token: str = Field(..., description="Bot token from @BotFather")
    
    # User Session Configuration
    user_session_file_path: Path = Field(
        default=Path("./sessions/user_session.session"),
        description="Path to Telethon user session file"
    )
    
    # Database Configuration
    database_url: str = Field(..., description="PostgreSQL database URL")
    
    # Redis Configuration
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL"
    )
    
    # Security Configuration
    admin_ids: List[int] = Field(default_factory=list, description="List of admin user IDs")
    secret_key: str = Field(..., description="Secret key for encryption")
    
    # Performance Configuration
    max_concurrent_forwards: int = Field(default=10, ge=1, le=100)
    max_retry_attempts: int = Field(default=3, ge=1, le=10)
    flood_wait_multiplier: float = Field(default=1.5, ge=1.0, le=5.0)
    
    # Logging Configuration
    log_level: str = Field(default="INFO", regex="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    debug_mode: bool = Field(default=False)
    
    # Optional: Sentry Configuration
    sentry_dsn: Optional[str] = Field(default=None)
    
    # Optional: Celery Configuration
    celery_broker_url: Optional[str] = Field(default=None)
    celery_result_backend: Optional[str] = Field(default=None)
    
    # Optional: Prometheus Metrics
    enable_metrics: bool = Field(default=False)
    metrics_port: int = Field(default=8000, ge=1024, le=65535)
    
    @validator('admin_ids', pre=True)
    def parse_admin_ids(cls, v):
        """Parse comma-separated admin IDs from environment variable."""
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(',') if x.strip()]
        return v
    
    @validator('user_session_file_path', pre=True)
    def parse_session_path(cls, v):
        """Ensure session directory exists."""
        path = Path(v)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings instance."""
    return settings


def is_admin(user_id: int) -> bool:
    """Check if user ID is in admin list."""
    return user_id in settings.admin_ids


def get_database_url() -> str:
    """Get database URL for SQLAlchemy."""
    return settings.database_url


def get_redis_url() -> str:
    """Get Redis URL for connection."""
    return settings.redis_url
