"""SAR analysis bindings: scaffold-tree + UMAP cluster + R-group decomposition jobs + use cases.

Wires:
- ``ScaffoldNetworkBuilder``         — Singleton (pure RDKit wrapper)
- ``ScaffoldTreeJobRepository``      — SQLAlchemy impl, per-resolve UoW
- ``BuildScaffoldNetwork``           — Singleton-less factory (fresh UoW each call)
- ``RunScaffoldTree``                — Activity runner used by the Temporal worker
- ``ScaffoldTreeOrchestrator``       — Null when ``TEMPORAL_DISABLED=1``; the live
  ``TemporalScaffoldTreeOrchestrator`` is bound later by ``app.py``'s lifespan
  once the Temporal client is available — same pattern as ``register_export``.
- ``StartScaffoldTreeJob`` / ``GetScaffoldTreeJob`` / ``CancelScaffoldTreeJob``
- ``MorganFingerprintLoader``        — lean session-per-call FP reader
- ``UmapEmbedder``                   — thin umap-learn wrapper (Singleton)
- ``ButinaClusterer``                — Singleton (threshold=0.4)
- ``MaxMinPickerAdapter``            — Singleton (seed=42)
- ``UmapJobRepository``             — SQLAlchemy impl, per-resolve session
- ``ComputeUmapCluster``            — per-resolve (holds loader + embedder + clusterer)
- ``RunUmapCluster``                 — Activity runner used by the Temporal worker
- ``UmapClusterOrchestrator``       — Null when ``TEMPORAL_DISABLED=1``; live
  ``TemporalUmapClusterOrchestrator`` bound by ``app.py``'s lifespan.
- ``StartUmapClusterJob`` / ``GetUmapClusterJob`` / ``CancelUmapClusterJob``

Note: ``MurckoScaffoldCalculator`` is already registered by ``register_core``.
"""

from __future__ import annotations

import os

from lagom import Container, Singleton
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.application.sar_analysis.build_scaffold_network import BuildScaffoldNetwork
from cellar.application.sar_analysis.cancel_decomposition_run import CancelDecompositionRun
from cellar.application.sar_analysis.cancel_scaffold_tree_job import CancelScaffoldTreeJob
from cellar.application.sar_analysis.cancel_umap_cluster_job import CancelUmapClusterJob
from cellar.application.sar_analysis.compute_umap_cluster import ComputeUmapCluster
from cellar.application.sar_analysis.decomposition_members import DecompositionMemberStream
from cellar.application.sar_analysis.decomposition_rows import FetchDecompositionRows
from cellar.application.sar_analysis.get_decomposition_run import GetDecompositionRun
from cellar.application.sar_analysis.get_scaffold_tree_job import GetScaffoldTreeJob
from cellar.application.sar_analysis.get_umap_cluster_job import GetUmapClusterJob
from cellar.application.sar_analysis.cancel_activity_projection import CancelActivityProjection
from cellar.application.sar_analysis.get_activity_projection import GetActivityProjection
from cellar.application.sar_analysis.run_activity_projection import RunActivityProjection
from cellar.application.sar_analysis.start_activity_projection import (
    SarActivityProjectionOrchestrator,
    StartActivityProjection,
)
from cellar.application.sar_analysis.repositories import (
    RGroupDecompositionRunRepository,
    SarActivityProjectionRepository,
    ScaffoldTreeJobRepository,
    UmapJobRepository,
)
from cellar.application.screening.molecule_activity_service import MoleculeActivityService
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_repository import (  # noqa: E501
    SQLAlchemySarActivityProjectionRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (  # noqa: E501
    SQLAlchemyDoseResponseCurveRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.readout_data_repository import (
    SQLAlchemyReadoutDataRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.run_repository import (
    SQLAlchemyRunRepository,
)
from cellar.application.sar_analysis.run_decomposition import RunDecomposition
from cellar.application.sar_analysis.run_scaffold_tree import RunScaffoldTree
from cellar.application.sar_analysis.run_umap_cluster import RunUmapCluster
from cellar.application.sar_analysis.start_decomposition_run import (
    RGroupDecompositionOrchestrator,
    StartDecompositionRun,
)
from cellar.application.sar_analysis.start_scaffold_tree_job import (
    ScaffoldTreeOrchestrator,
    StartScaffoldTreeJob,
)
from cellar.application.sar_analysis.start_umap_cluster_job import (
    StartUmapClusterJob,
    UmapClusterOrchestrator,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (  # noqa: E501
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.collection_repository import (  # noqa: E501
    SQLAlchemyCollectionRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.decomposition_row_reader import (
    SQLAlchemyDecompositionRowReader,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.rgroup_decomposition_run_repository import (  # noqa: E501
    SQLAlchemyRGroupDecompositionRunRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.scaffold_tree_job_repository import (  # noqa: E501
    SQLAlchemyScaffoldTreeJobRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.umap_job_repository import (
    SQLAlchemyUmapJobRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from cellar.infrastructure.rdkit.butina_clusterer import ButinaClusterer
from cellar.infrastructure.rdkit.maxmin_picker import MaxMinPickerAdapter
from cellar.infrastructure.rdkit.scaffold_network_builder import ScaffoldNetworkBuilder
from cellar.infrastructure.rdkit.streaming_rgroup_decomposer import StreamingRGroupDecomposer
from cellar.infrastructure.rdkit.umap_embedder import UmapEmbedder
from cellar.infrastructure.sar_analysis.morgan_fingerprint_loader import MorganFingerprintLoader


def register_sar_analysis(container: Container) -> None:
    # --- Scaffold network builder (pure RDKit wrapper, no deps) ---
    container.define(ScaffoldNetworkBuilder, Singleton(ScaffoldNetworkBuilder))

    # --- ScaffoldTreeJobRepository ---
    # Per-resolve fresh UoW so request-scoped sessions don't bleed across
    # callers — same pattern as ExportJobRepository in _export.py.
    def _job_repo(c: Container) -> ScaffoldTreeJobRepository:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SQLAlchemyScaffoldTreeJobRepository(uow)  # type: ignore[return-value]

    container.define(ScaffoldTreeJobRepository, _job_repo)

    # --- BuildScaffoldNetwork ---
    # Fresh UoW per resolve so each builder call carries its own session for
    # both the molecule fetch and the cache lookup.
    def _build_scaffold_network(c: Container) -> BuildScaffoldNetwork:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return BuildScaffoldNetwork(
            molecule_fetcher=SQLAlchemyMoleculeRepository(uow),
            job_repository=SQLAlchemyScaffoldTreeJobRepository(uow),
            uow=uow,
            network_builder=c[ScaffoldNetworkBuilder],
        )

    container.define(BuildScaffoldNetwork, _build_scaffold_network)

    # --- Streaming R-group decomposer (pure RDKit wrapper, no deps) → Singleton ---
    container.define(StreamingRGroupDecomposer, Singleton(StreamingRGroupDecomposer))

    # --- RGroupDecompositionRunRepository — per-resolve fresh UoW ---
    def _rgroup_run_repo(c: Container) -> RGroupDecompositionRunRepository:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SQLAlchemyRGroupDecompositionRunRepository(uow)  # type: ignore[return-value]

    container.define(RGroupDecompositionRunRepository, _rgroup_run_repo)

    # --- RunDecomposition — in-process runner the Temporal activity wraps. The
    # member stream + repo share one UoW so streaming + persistence are one tx. ---
    def _run_decomposition(c: Container) -> RunDecomposition:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        members = DecompositionMemberStream(
            molecule_fetcher=SQLAlchemyMoleculeRepository(uow),
            collection_reader=SQLAlchemyCollectionRepository(uow),
        )
        return RunDecomposition(
            members=members,
            decomposer=c[StreamingRGroupDecomposer],
            repository=SQLAlchemyRGroupDecompositionRunRepository(uow),
            uow=uow,
        )

    container.define(RunDecomposition, _run_decomposition)

    # --- RGroupDecompositionOrchestrator — Null when TEMPORAL_DISABLED=1; live
    # TemporalRGroupDecompositionOrchestrator bound by app.py's lifespan. ---
    if os.environ.get("TEMPORAL_DISABLED") == "1":
        from cellar.infrastructure.temporal.orchestrators.rgroup_decomposition import (
            NullRGroupDecompositionOrchestrator,
        )

        def _null_rgroup_orchestrator(c: Container) -> NullRGroupDecompositionOrchestrator:
            return NullRGroupDecompositionOrchestrator(c[RunDecomposition])

        container.define(RGroupDecompositionOrchestrator, _null_rgroup_orchestrator)

    # --- Decomposition use cases (each shares one UoW across its collaborators) ---
    def _start_decomposition(c: Container) -> StartDecompositionRun:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        members = DecompositionMemberStream(
            molecule_fetcher=SQLAlchemyMoleculeRepository(uow),
            collection_reader=SQLAlchemyCollectionRepository(uow),
        )
        return StartDecompositionRun(
            members=members,
            decomposer=c[StreamingRGroupDecomposer],
            repository=SQLAlchemyRGroupDecompositionRunRepository(uow),
            orchestrator=c[RGroupDecompositionOrchestrator],
            uow=uow,
        )

    def _get_decomposition(c: Container) -> GetDecompositionRun:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetDecompositionRun(
            repository=SQLAlchemyRGroupDecompositionRunRepository(uow),
            uow=uow,
        )

    def _cancel_decomposition(c: Container) -> CancelDecompositionRun:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CancelDecompositionRun(
            repository=SQLAlchemyRGroupDecompositionRunRepository(uow),
            orchestrator=c[RGroupDecompositionOrchestrator],
            uow=uow,
        )

    def _fetch_decomposition_rows(c: Container) -> FetchDecompositionRows:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return FetchDecompositionRows(
            repository=SQLAlchemyRGroupDecompositionRunRepository(uow),
            reader=SQLAlchemyDecompositionRowReader(uow),
            uow=uow,
        )

    container.define(StartDecompositionRun, _start_decomposition)
    container.define(GetDecompositionRun, _get_decomposition)
    container.define(CancelDecompositionRun, _cancel_decomposition)
    container.define(FetchDecompositionRows, _fetch_decomposition_rows)

    # =====================================================================
    # Activity projection slice (mirrors the decomposition slice above)
    # =====================================================================

    def _activity_projection_repo(c: Container) -> SarActivityProjectionRepository:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SQLAlchemySarActivityProjectionRepository(uow)  # type: ignore[return-value]

    container.define(SarActivityProjectionRepository, _activity_projection_repo)

    def _activity_enricher(uow: AsyncUnitOfWork) -> MoleculeActivityService:
        # Shares the caller's UoW so enrich reads + value writes run on one session.
        return MoleculeActivityService(
            uow=uow,
            readout_repo=SQLAlchemyReadoutDataRepository(uow),
            curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            run_repo=SQLAlchemyRunRepository(uow),
        )

    def _run_activity_projection(c: Container) -> RunActivityProjection:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        members = DecompositionMemberStream(
            molecule_fetcher=SQLAlchemyMoleculeRepository(uow),
            collection_reader=SQLAlchemyCollectionRepository(uow),
        )
        return RunActivityProjection(
            members=members,
            enricher=_activity_enricher(uow),
            repository=SQLAlchemySarActivityProjectionRepository(uow),
            uow=uow,
        )

    container.define(RunActivityProjection, _run_activity_projection)

    if os.environ.get("TEMPORAL_DISABLED") == "1":
        from cellar.infrastructure.temporal.orchestrators.sar_activity_projection import (
            NullSarActivityProjectionOrchestrator,
        )

        def _null_activity_orchestrator(c: Container) -> NullSarActivityProjectionOrchestrator:
            return NullSarActivityProjectionOrchestrator(c[RunActivityProjection])

        container.define(SarActivityProjectionOrchestrator, _null_activity_orchestrator)

    def _start_activity_projection(c: Container) -> StartActivityProjection:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        members = DecompositionMemberStream(
            molecule_fetcher=SQLAlchemyMoleculeRepository(uow),
            collection_reader=SQLAlchemyCollectionRepository(uow),
        )
        return StartActivityProjection(
            members=members,
            enricher=_activity_enricher(uow),
            repository=SQLAlchemySarActivityProjectionRepository(uow),
            orchestrator=c[SarActivityProjectionOrchestrator],
            uow=uow,
        )

    def _get_activity_projection(c: Container) -> GetActivityProjection:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetActivityProjection(
            repository=SQLAlchemySarActivityProjectionRepository(uow), uow=uow
        )

    def _cancel_activity_projection(c: Container) -> CancelActivityProjection:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CancelActivityProjection(
            repository=SQLAlchemySarActivityProjectionRepository(uow),
            orchestrator=c[SarActivityProjectionOrchestrator],
            uow=uow,
        )

    container.define(StartActivityProjection, _start_activity_projection)
    container.define(GetActivityProjection, _get_activity_projection)
    container.define(CancelActivityProjection, _cancel_activity_projection)
    # NOTE: FetchActivityHeatmap is registered in Task 14 (its module lands there).

    # --- RunScaffoldTree ---
    # In-process runner the Temporal activity wraps. Worker pulls this once
    # at boot (`container[RunScaffoldTree]`), so it must resolve cleanly.
    def _run_scaffold_tree(c: Container) -> RunScaffoldTree:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return RunScaffoldTree(
            builder=c[BuildScaffoldNetwork],
            repository=SQLAlchemyScaffoldTreeJobRepository(uow),
            uow=uow,
        )

    container.define(RunScaffoldTree, _run_scaffold_tree)

    # --- ScaffoldTreeOrchestrator ---
    # When TEMPORAL_DISABLED=1, bind NullScaffoldTreeOrchestrator here so the
    # whole container is self-contained (tests + local dev without Temporal).
    # In production, app.py's lifespan awaits the Temporal client and overrides
    # this binding with TemporalScaffoldTreeOrchestrator — same pattern as
    # NullExportOrchestrator etc.
    if os.environ.get("TEMPORAL_DISABLED") == "1":
        from cellar.infrastructure.temporal.orchestrators.scaffold_tree import (
            NullScaffoldTreeOrchestrator,
        )

        def _null_orchestrator(c: Container) -> NullScaffoldTreeOrchestrator:
            return NullScaffoldTreeOrchestrator(c[RunScaffoldTree])

        container.define(ScaffoldTreeOrchestrator, _null_orchestrator)

    # --- Use cases ---
    def _start(c: Container) -> StartScaffoldTreeJob:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return StartScaffoldTreeJob(
            builder=c[BuildScaffoldNetwork],
            repository=SQLAlchemyScaffoldTreeJobRepository(uow),
            orchestrator=c[ScaffoldTreeOrchestrator],
            uow=uow,
        )

    def _get(c: Container) -> GetScaffoldTreeJob:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetScaffoldTreeJob(
            repository=SQLAlchemyScaffoldTreeJobRepository(uow),
            uow=uow,
        )

    def _cancel(c: Container) -> CancelScaffoldTreeJob:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CancelScaffoldTreeJob(
            repository=SQLAlchemyScaffoldTreeJobRepository(uow),
            orchestrator=c[ScaffoldTreeOrchestrator],
            uow=uow,
        )

    container.define(StartScaffoldTreeJob, _start)
    container.define(GetScaffoldTreeJob, _get)
    container.define(CancelScaffoldTreeJob, _cancel)

    # -------------------------------------------------------------------------
    # UMAP cluster pipeline
    # -------------------------------------------------------------------------

    # Singletons — pure computation wrappers, no session state.
    container.define(UmapEmbedder, Singleton(UmapEmbedder))
    container.define(ButinaClusterer, Singleton(lambda: ButinaClusterer(threshold=0.4)))
    container.define(MaxMinPickerAdapter, Singleton(lambda: MaxMinPickerAdapter(seed=42)))

    # MorganFingerprintLoader — per-resolve, creates a fresh session per load_morgan call.
    def _fp_loader(c: Container) -> MorganFingerprintLoader:
        return MorganFingerprintLoader(session_factory=c[async_sessionmaker])

    container.define(MorganFingerprintLoader, _fp_loader)

    # UmapJobRepository — per-resolve fresh UoW so request-scoped sessions
    # don't bleed across callers — same pattern as ScaffoldTreeJobRepository.
    def _umap_job_repo(c: Container) -> UmapJobRepository:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SQLAlchemyUmapJobRepository(uow)  # type: ignore[return-value]

    container.define(UmapJobRepository, _umap_job_repo)

    # ComputeUmapCluster — per-resolve (depends on loader which is per-resolve).
    def _compute_umap(c: Container) -> ComputeUmapCluster:
        return ComputeUmapCluster(
            fingerprint_loader=c[MorganFingerprintLoader],
            embedder=c[UmapEmbedder],
            clusterer=c[ButinaClusterer],
            maxmin_picker=c[MaxMinPickerAdapter],
        )

    container.define(ComputeUmapCluster, _compute_umap)

    # RunUmapCluster — in-process runner the Temporal activity wraps.
    # A single UoW is shared by the runner and its repo so both operate within
    # the same transaction boundary — mirrors RunScaffoldTree exactly.
    def _run_umap_cluster(c: Container) -> RunUmapCluster:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return RunUmapCluster(
            compute=c[ComputeUmapCluster],
            repository=SQLAlchemyUmapJobRepository(uow),
            uow=uow,
        )

    container.define(RunUmapCluster, _run_umap_cluster)

    # UmapClusterOrchestrator — Null when TEMPORAL_DISABLED=1; live orchestrator
    # bound by app.py's lifespan once the Temporal client is available.
    if os.environ.get("TEMPORAL_DISABLED") == "1":
        from cellar.infrastructure.temporal.orchestrators.umap_cluster import (
            NullUmapClusterOrchestrator,
        )

        def _null_umap_orchestrator(c: Container) -> NullUmapClusterOrchestrator:
            return NullUmapClusterOrchestrator(runner=c[RunUmapCluster].execute)

        container.define(UmapClusterOrchestrator, _null_umap_orchestrator)

    # Use cases — each builds its own UoW and shares it with its repo so the
    # use case and repo always operate within the same transaction boundary.
    def _start_umap(c: Container) -> StartUmapClusterJob:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return StartUmapClusterJob(
            compute=c[ComputeUmapCluster],
            repository=SQLAlchemyUmapJobRepository(uow),
            orchestrator=c[UmapClusterOrchestrator],
            uow=uow,
        )

    def _get_umap(c: Container) -> GetUmapClusterJob:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetUmapClusterJob(
            repository=SQLAlchemyUmapJobRepository(uow),
            uow=uow,
        )

    def _cancel_umap(c: Container) -> CancelUmapClusterJob:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CancelUmapClusterJob(
            repository=SQLAlchemyUmapJobRepository(uow),
            uow=uow,
            orchestrator=c[UmapClusterOrchestrator],
        )

    container.define(StartUmapClusterJob, _start_umap)
    container.define(GetUmapClusterJob, _get_umap)
    container.define(CancelUmapClusterJob, _cancel_umap)
