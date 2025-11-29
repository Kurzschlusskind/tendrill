"""
Tendrill Database Session Management

Async SQLAlchemy Session mit Connection Pooling.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from tendrill.config import get_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

# Global engine instance
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """
    Gibt die SQLAlchemy Engine zurück.

    Lazy Initialization beim ersten Aufruf.
    """
    global _engine

    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            str(settings.database.url),
            pool_size=settings.database.pool_size,
            max_overflow=settings.database.max_overflow,
            pool_timeout=settings.database.pool_timeout,
            echo=settings.database.echo,
        )

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Gibt die Session Factory zurück."""
    global _session_factory

    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    return _session_factory


async def init_db() -> None:
    """
    Initialisiert die Datenbankverbindung.

    Wird beim App-Start aufgerufen.
    """
    # Engine erstellen und Connection testen
    engine = get_engine()
    async with engine.begin() as conn:
        # Einfacher Connection Test
        await conn.execute(text("SELECT 1"))


async def close_db() -> None:
    """
    Schließt alle Datenbankverbindungen.

    Wird beim App-Shutdown aufgerufen.
    """
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Context Manager für Datenbank-Sessions.

    Usage:
        async with get_session() as session:
            result = await session.execute(...)
    """
    factory = get_session_factory()
    session = factory()

    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency Injection für FastAPI.

    Usage:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with get_session() as session:
        yield session
