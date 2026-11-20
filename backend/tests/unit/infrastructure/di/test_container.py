"""Unit tests for the DI container — verify wiring resolves correctly."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from cellar.application.audit.audit_recording_service import AuditRecordingService
from cellar.application.cdd_import.check_cdd_molecule_identifiers import (
    CheckCddMoleculeIdentifiers,
)
from cellar.application.screening.instrument_export import InstrumentReaders
from cellar.application.screening.readout_calculation_engine import ReadoutCalculationEngine
from cellar.infrastructure.cdd.client import CddVaultClient
from cellar.infrastructure.di.container import create_container
from cellar.infrastructure.instrument_readers import default_readers
from cellar.infrastructure.messaging.event_dispatcher import EventDispatcher
from cellar.infrastructure.persistence.settings import DatabaseSettings
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


@pytest.fixture
def test_settings() -> DatabaseSettings:
    """Minimal settings with a dummy URL (no real DB needed for wiring tests)."""
    return DatabaseSettings(database_url="postgresql+asyncpg://x:x@localhost:5432/x")


class TestContainer:
    def test_engine_is_singleton(self, test_settings: DatabaseSettings) -> None:
        container = create_container(test_settings)
        assert container[AsyncEngine] is container[AsyncEngine]

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

    def test_resolves_instrument_readers(self, test_settings: DatabaseSettings) -> None:
        readers = create_container(test_settings)[InstrumentReaders]
        assert [r.id for r in readers] == [r.id for r in default_readers()]
        assert len(readers) >= 1

    def test_calculation_engine_gets_melting_steps_and_batches(
        self, test_settings: DatabaseSettings
    ) -> None:
        engine = create_container(test_settings)[ReadoutCalculationEngine]
        assert engine._melting_step_repo is not None
        assert engine._batch_repo is not None

    def test_resolves_the_vault_molecule_identifier_check(
        self, test_settings: DatabaseSettings
    ) -> None:
        check = create_container(test_settings)[CheckCddMoleculeIdentifiers]
        assert isinstance(check._gateway, CddVaultClient)

    def test_overrides_replace_production_definitions(
        self, test_settings: DatabaseSettings
    ) -> None:
        """Tests stub any adapter without the registrar guarding its definition."""
        from cellar.infrastructure.temporal.settings import TemporalSettings

        stub = object()
        container = create_container(test_settings, overrides={TemporalSettings: stub})
        assert container[TemporalSettings] is stub

    def test_overridden_cdd_client_reaches_the_use_cases(
        self, test_settings: DatabaseSettings
    ) -> None:
        stub = object()
        container = create_container(test_settings, overrides={CddVaultClient: stub})
        assert container[CheckCddMoleculeIdentifiers]._gateway is stub
