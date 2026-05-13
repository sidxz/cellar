"""Async database engine and session factory."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from cellar.infrastructure.persistence.settings import DatabaseSettings


def create_engine(settings: DatabaseSettings) -> AsyncEngine:
    """Create an async SQLAlchemy engine from settings."""
    return create_async_engine(
        settings.database_url,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_pre_ping=settings.pool_pre_ping,
        echo=settings.echo,
    )


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory bound to the given engine."""
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
