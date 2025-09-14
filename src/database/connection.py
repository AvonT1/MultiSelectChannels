"""
Database connection management with SQLAlchemy 2.0 and async support.
Provides connection pooling, session management, and migration support.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
)
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from src.config import get_database_url
from .models import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connections and sessions."""
    
    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or get_database_url()
        self._engine: Optional[AsyncEngine] = None
        self._sync_engine = None
        self._async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None
        self._sync_session_factory = None
    
    @property
    def engine(self) -> AsyncEngine:
        """Get or create async database engine."""
        if self._engine is None:
            # Convert postgresql:// to postgresql+asyncpg://
            async_url = self.database_url.replace("postgresql://", "postgresql+asyncpg://")
            self._engine = create_async_engine(
                async_url,
                echo=False,
                pool_pre_ping=True,
                pool_recycle=3600,
                max_overflow=20,
                pool_size=10
            )
        return self._engine
    
    @property
    def sync_engine(self):
        """Get or create synchronous database engine for migrations."""
        if self._sync_engine is None:
            # Use psycopg2 for sync operations
            sync_url = self.database_url.replace("postgresql://", "postgresql+psycopg2://")
            self._sync_engine = create_engine(
                sync_url,
                echo=False,
                pool_pre_ping=True,
                pool_recycle=3600
            )
        return self._sync_engine
    
    @property
    def async_session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Get or create async session factory."""
        if self._async_session_factory is None:
            self._async_session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
        return self._async_session_factory
    
    @property
    def sync_session_factory(self):
        """Get or create sync session factory."""
        if self._sync_session_factory is None:
            self._sync_session_factory = sessionmaker(
                bind=self.sync_engine,
                expire_on_commit=False
            )
        return self._sync_session_factory
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get async database session with automatic cleanup."""
        async with self.async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    
    def get_sync_session(self):
        """Get synchronous database session for migrations."""
        return self.sync_session_factory()
    
    async def create_tables(self):
        """Create all database tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")
    
    async def drop_tables(self):
        """Drop all database tables (use with caution)."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.warning("All database tables dropped")
    
    async def check_connection(self) -> bool:
        """Check if database connection is working."""
        try:
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Database connection check failed: {e}")
            return False
    
    async def close(self):
        """Close database connections."""
        if self._engine:
            await self._engine.dispose()
        if self._sync_engine:
            self._sync_engine.dispose()


# Global database manager instance
db_manager = DatabaseManager()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency function to get database session."""
    async with db_manager.get_session() as session:
        yield session


async def init_database():
    """Initialize database with tables and basic data."""
    logger.info("Initializing database...")
    
    # Check connection
    if not await db_manager.check_connection():
        raise RuntimeError("Cannot connect to database")
    
    # Create tables
    await db_manager.create_tables()
    
    logger.info("Database initialization completed")


async def close_database():
    """Close database connections."""
    await db_manager.close()
    logger.info("Database connections closed")
