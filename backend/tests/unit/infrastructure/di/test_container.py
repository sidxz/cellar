"""Unit tests for the DI container — verify wiring resolves correctly."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from chem_vault.application.audit.audit_recording_service import AuditRecordingService
from chem_vault.infrastructure.di.container import create_container
from chem_vault.infrastructure.messaging.event_dispatcher import EventDispatcher
from chem_vault.infrastructure.persistence.settings import DatabaseSettings
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


@pytest.fixture
def test_settings() -> DatabaseSettings:
    """Minimal settings with a dummy URL (no real DB needed for wiring tests)."""
    return DatabaseSettings(database_url="postgresql+asyncpg://x:x@localhost:5432/x")


class TestContainer:
    def test_resolves_engine(self, test_settings: DatabaseSettings) -> None:
        container = create_container(test_settings)
        engine = container[AsyncEngine]
        assert engine is not None

    def test_engine_is_singleton(self, test_settings: DatabaseSettings) -> None:
        container = create_container(test_settings)
        assert container[AsyncEngine] is container[AsyncEngine]

    def test_resolves_session_factory(
        self, test_settings: DatabaseSettings
    ) -> None:
        container = create_container(test_settings)
        factory = container[async_sessionmaker]
        assert factory is not None

    def test_resolves_uow(self, test_settings: DatabaseSettings) -> None:
        container = create_container(test_settings)
        uow = container[AsyncUnitOfWork]
        assert isinstance(uow, AsyncUnitOfWork)

    def test_uow_is_not_singleton(
        self, test_settings: DatabaseSettings
    ) -> None:
        container = create_container(test_settings)
        uow1 = container[AsyncUnitOfWork]
        uow2 = container[AsyncUnitOfWork]
        assert uow1 is not uow2

    def test_resolves_event_dispatcher(
        self, test_settings: DatabaseSettings
    ) -> None:
        container = create_container(test_settings)
        dispatcher = container[EventDispatcher]
        assert isinstance(dispatcher, EventDispatcher)

    def test_event_dispatcher_is_singleton(
        self, test_settings: DatabaseSettings
    ) -> None:
        container = create_container(test_settings)
        assert container[EventDispatcher] is container[EventDispatcher]

    def test_resolves_audit_service(
        self, test_settings: DatabaseSettings
    ) -> None:
        container = create_container(test_settings)
        service = container[AuditRecordingService]
        assert isinstance(service, AuditRecordingService)
