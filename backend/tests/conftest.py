"""Shared test fixtures — testcontainers PostgreSQL+RDKit, async sessions."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

RDKIT_IMAGE = "informaticsmatters/rdkit-cartridge-debian:Release_2024_03_3"


# ---------------------------------------------------------------------------
# Session-scoped: container, migrations, engine, session factory
# All tests share a single event loop (asyncio_default_test_loop_scope=session
# in pyproject.toml) so session-scoped async fixtures work correctly with
# asyncpg's event-loop-bound connections.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    """Start a PostgreSQL+RDKit container once per test session."""
    with PostgresContainer(
        image=RDKIT_IMAGE,
        username="chemvault",
        password="chemvault",
        dbname="chemvault",
        driver=None,
    ) as container:
        yield container


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer) -> str:
    """Async database URL pointing at the test container."""
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    return f"postgresql+asyncpg://chemvault:chemvault@{host}:{port}/chemvault"


@pytest.fixture(scope="session")
def _run_migrations(database_url: str) -> None:
    """Run Alembic migrations once (sync to avoid nested event loops)."""
    os.environ["DATABASE_URL"] = database_url
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")


@pytest.fixture(scope="session")
async def engine(
    database_url: str, _run_migrations: None
) -> AsyncIterator[AsyncEngine]:
    """Session-scoped async engine (created after migrations run)."""
    eng = create_async_engine(database_url)
    yield eng
    await eng.dispose()


@pytest.fixture(scope="session")
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session factory bound to the test engine."""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Function-scoped: isolated database session per test
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Function-scoped session that rolls back after each test."""
    async with session_factory() as session, session.begin():
        yield session
        await session.rollback()
