"""Unit tests for sar_analysis DI wiring."""

from __future__ import annotations

import pytest
from lagom.exceptions import UnresolvableType

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
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.scaffold_tree_job_repository import (  # noqa: E501
    SQLAlchemyScaffoldTreeJobRepository,
)
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
        assert container[ScaffoldNetworkBuilder] is container[ScaffoldNetworkBuilder]

    def test_resolves_job_repository(self, test_settings: DatabaseSettings) -> None:
        container = create_container(test_settings)
        repo = container[ScaffoldTreeJobRepository]
        assert isinstance(repo, SQLAlchemyScaffoldTreeJobRepository)

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
        # With Temporal enabled, _sar_analysis binds no orchestrator: app.py's
        # lifespan supplies TemporalScaffoldTreeOrchestrator once the client is up.
        with pytest.raises(UnresolvableType):
            container[ScaffoldTreeOrchestrator]

    def test_decomposition_use_cases_resolve_with_temporal_disabled(
        self, test_settings: DatabaseSettings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Start/Cancel depend on RGroupDecompositionOrchestrator; under
        # TEMPORAL_DISABLED=1 _sar_analysis binds the Null one (mirrors the
        # scaffold-tree pattern). RunDecomposition is what that Null wraps.
        monkeypatch.setenv("TEMPORAL_DISABLED", "1")
        from cellar.application.sar_analysis.cancel_decomposition_run import (
            CancelDecompositionRun,
        )
        from cellar.application.sar_analysis.decomposition_rows import FetchDecompositionRows
        from cellar.application.sar_analysis.get_decomposition_run import GetDecompositionRun
        from cellar.application.sar_analysis.run_decomposition import RunDecomposition
        from cellar.application.sar_analysis.start_decomposition_run import StartDecompositionRun

        container = create_container(test_settings)
        assert isinstance(container[RunDecomposition], RunDecomposition)
        assert isinstance(container[StartDecompositionRun], StartDecompositionRun)
        assert isinstance(container[GetDecompositionRun], GetDecompositionRun)
        assert isinstance(container[CancelDecompositionRun], CancelDecompositionRun)
        assert isinstance(container[FetchDecompositionRows], FetchDecompositionRows)

    def test_activity_projection_use_cases_resolve_with_temporal_disabled(
        self, test_settings: DatabaseSettings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Start/Cancel depend on SarActivityProjectionOrchestrator; under
        # TEMPORAL_DISABLED=1 _sar_analysis binds the Null one. RunActivityProjection
        # is what that Null wraps; FetchActivityHeatmap has no orchestrator dep.
        monkeypatch.setenv("TEMPORAL_DISABLED", "1")
        from cellar.application.sar_analysis.activity_heatmap import FetchActivityHeatmap
        from cellar.application.sar_analysis.cancel_activity_projection import (
            CancelActivityProjection,
        )
        from cellar.application.sar_analysis.get_activity_projection import GetActivityProjection
        from cellar.application.sar_analysis.run_activity_projection import RunActivityProjection
        from cellar.application.sar_analysis.start_activity_projection import (
            SarActivityProjectionOrchestrator,
            StartActivityProjection,
        )

        container = create_container(test_settings)
        assert isinstance(container[RunActivityProjection], RunActivityProjection)
        assert isinstance(container[StartActivityProjection], StartActivityProjection)
        assert isinstance(container[GetActivityProjection], GetActivityProjection)
        assert isinstance(container[CancelActivityProjection], CancelActivityProjection)
        orch = container[SarActivityProjectionOrchestrator]
        assert orch.__class__.__name__ == "NullSarActivityProjectionOrchestrator"
        assert isinstance(container[FetchActivityHeatmap], FetchActivityHeatmap)
