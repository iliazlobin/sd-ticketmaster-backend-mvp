from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from ticketmaster.config import settings as app_settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


async def init_db() -> None:
    """Initialize the async database engine and session factory."""
    global _engine, _sessionmaker
    _engine = create_async_engine(app_settings.database_url, echo=False, pool_size=10)
    _sessionmaker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def close_db() -> None:
    """Close the database engine and dispose of the connection pool."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    _sessionmaker = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session."""
    if _sessionmaker is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _sessionmaker() as session:
        try:
            yield session
        finally:
            await session.close()
