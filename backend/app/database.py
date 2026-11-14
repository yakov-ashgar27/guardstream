"""Async PostgreSQL engine and session management."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=10,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a database session."""
    async with SessionLocal() as session:
        yield session


async def init_db(retries: int = 20, delay_s: float = 1.5) -> None:
    """Create all tables, retrying while PostgreSQL is still starting up."""
    # Import models so they register on Base.metadata.
    from app import models  # noqa: F401

    for attempt in range(1, retries + 1):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database schema ready")
            return
        except (OperationalError, OSError, ConnectionError, Exception) as exc:  # noqa: BLE001
            logger.warning("Database not ready (attempt %d/%d): %s", attempt, retries, exc)
            await asyncio.sleep(delay_s)
    raise RuntimeError("Could not connect to PostgreSQL")


async def close_db() -> None:
    """Dispose of the connection pool."""
    await engine.dispose()
