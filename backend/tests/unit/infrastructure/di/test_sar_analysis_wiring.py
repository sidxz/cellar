"""Unit tests for sar_analysis DI wiring."""

from __future__ import annotations

import pytest

from cellar.application.sar_analysis.build_scaffold_network import BuildScaffoldNetwork
from cellar.application.sar_analysis.cancel_scaffold_tree_job import CancelScaffoldTreeJob
from cellar.application.sar_analysis.get_scaffold_tree_job import GetScaffoldTreeJob
from cellar.application.sar_analysis.repositories import ScaffoldTreeJobRepository
from cellar.application.sar_analysis.run_scaffold_tree import RunScaffoldTree
from cellar.application.sar_analysis.start_scaffold_tree_job import (
    ScaffoldTreeOrchestrator,
    StartScaffoldTreeJob,
)
from cellar.infrastructure.di.container import create_container
from cellar.infrastructure.persistence.settings import DatabaseSettings
from cellar.infrastructure.rdkit.scaffold_network_builder import ScaffoldNetworkBuilder


@pytest.fixture
def test_settings() -> DatabaseSettings:
    """Minimal settings with a dummy URL (no real DB needed for wiring tests)."""
    return DatabaseSettings(database_url="postgresql+asyncpg://x:x@localhost:5432/x")


class TestSarAnalysisWiring:
    def test_resolves_scaffold_network_builder(
        self, test_settings: DatabaseSettings
    ) -> None:
        container = create_container(test_settings)
        builder = container[ScaffoldNetworkBuilder]
        assert builder is not None
        # Singleton
        assert container[ScaffoldNetworkBuilder] is container[ScaffoldNetworkBuilder]

    def test_resolves_job_repository(self, test_settings: DatabaseSettings) -> None:
        container = create_container(test_settings)
        repo = container[ScaffoldTreeJobRepository]
        assert repo is not None

    def test_resolves_build_scaffold_network(
        self, test_settings: DatabaseSettings
    ) -> None:
        container = create_container(test_settings)
        uc = container[BuildScaffoldNetwork]
        assert isinstance(uc, BuildScaffoldNetwork)

    def test_resolves_run_scaffold_tree(self, test_settings: DatabaseSettings) -> None:
        container = create_container(test_settings)
        runner = container[RunScaffoldTree]
        assert isinstance(runner, RunScaffoldTree)

    def test_resolves_start_scaffold_tree_job(
        self, test_settings: DatabaseSettings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # StartScaffoldTreeJob depends on ScaffoldTreeOrchestrator. In
        # production app.py supplies a TemporalScaffoldTreeOrchestrator at
        # lifespan startup; in tests/dev TEMPORAL_DISABLED=1 makes
        # _sar_analysis bind a Null one.
        monkeypatch.setenv("TEMPORAL_DISABLED", "1")
        container = create_container(test_settings)
        uc = container[StartScaffoldTreeJob]
        assert isinstance(uc, StartScaffoldTreeJob)

    def test_resolves_get_scaffold_tree_job(
        self, test_settings: DatabaseSettings
    ) -> None:
        # GetScaffoldTreeJob has no orchestrator dep — resolves either way.
        container = create_container(test_settings)
        uc = container[GetScaffoldTreeJob]
        assert isinstance(uc, GetScaffoldTreeJob)

    def test_resolves_cancel_scaffold_tree_job(
        self, test_settings: DatabaseSettings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Same orchestrator dependency as StartScaffoldTreeJob.
        monkeypatch.setenv("TEMPORAL_DISABLED", "1")
        container = create_container(test_settings)
        uc = container[CancelScaffoldTreeJob]
        assert isinstance(uc, CancelScaffoldTreeJob)

    def test_orchestrator_null_when_temporal_disabled(
        self, test_settings: DatabaseSettings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TEMPORAL_DISABLED", "1")
        container = create_container(test_settings)
        orch = container[ScaffoldTreeOrchestrator]
        assert orch.__class__.__name__ == "NullScaffoldTreeOrchestrator"

    def test_orchestrator_temporal_when_enabled(
        self, test_settings: DatabaseSettings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("TEMPORAL_DISABLED", raising=False)
        container = create_container(test_settings)
        # When Temporal is enabled at container-create time, _sar_analysis must
        # not bind a Null orchestrator. The Temporal binding is supplied later
        # by app.py's lifespan via TemporalScaffoldTreeOrchestrator override,
        # mirroring the export pattern. Until that override fires there is no
        # binding — resolving raises. We assert that the Null binding is NOT
        # in place by checking the class name if any resolution happens.
        try:
            orch = container[ScaffoldTreeOrchestrator]
        except Exception:
            return  # Expected — no Temporal client yet at container build.
        assert orch.__class__.__name__ != "NullScaffoldTreeOrchestrator"
