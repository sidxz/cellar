"""Shared test fixtures — testcontainers PostgreSQL+RDKit, async sessions, UoW, auth."""

from __future__ import annotations

import os
import uuid
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

from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from chem_vault.application.admin.admin_delete_registry import _REGISTRY
from tests.fakes.fake_auth import FakeAuth

RDKIT_IMAGE = "informaticsmatters/rdkit-cartridge-debian:Release_2024_03_3"

# ---------------------------------------------------------------------------
# Markers — allow separating fast unit tests from slow integration tests
# ---------------------------------------------------------------------------
# Usage:
#   pytest -m "not integration"    # unit tests only (no Docker)
#   pytest -m integration          # integration tests only
#   pytest                         # all tests


def pytest_collection_modifyitems(config, items):  # type: ignore[no-untyped-def]
    """Auto-mark tests under tests/integration/ with the 'integration' marker."""
    for item in items:
        if "/integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)


# ---------------------------------------------------------------------------
# Admin delete registry — clear/restore per test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _admin_delete_registry_isolation() -> Iterator[None]:
    """Clear and restore admin-delete registry state around each test.

    The registry is populated during DI bootstrap and persists across
    test runs. This fixture ensures tests don't interfere with each other.
    """
    snapshot = dict(_REGISTRY)
    _REGISTRY.clear()
    yield
    _REGISTRY.clear()
    _REGISTRY.update(snapshot)


# ---------------------------------------------------------------------------
# Session-scoped: container, migrations, engine, session factory
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
# Function-scoped: isolated database session, UoW, auth
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Function-scoped session that rolls back after each test."""
    async with session_factory() as session, session.begin():
        yield session
        await session.rollback()


@pytest.fixture
def uow(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncUnitOfWork:
    """Function-scoped Unit of Work for integration tests."""
    return AsyncUnitOfWork(session_factory)


@pytest.fixture
def fake_auth() -> FakeAuth:
    """Default editor auth context for tests."""
    return FakeAuth(role="editor")


@pytest.fixture
def admin_auth() -> FakeAuth:
    """Admin auth context for tests."""
    return FakeAuth(role="admin")


@pytest.fixture
def workspace_id() -> uuid.UUID:
    """Stable workspace ID for a test."""
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    """Stable user ID for a test."""
    return uuid.uuid4()
