"""SAR analysis bounded context bindings: scaffold-tree + UMAP cluster jobs + use cases.

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
from cellar.application.sar_analysis.cancel_scaffold_tree_job import CancelScaffoldTreeJob
from cellar.application.sar_analysis.cancel_umap_cluster_job import CancelUmapClusterJob
from cellar.application.sar_analysis.compute_umap_cluster import ComputeUmapCluster
from cellar.application.sar_analysis.get_scaffold_tree_job import GetScaffoldTreeJob
from cellar.application.sar_analysis.get_umap_cluster_job import GetUmapClusterJob
from cellar.application.sar_analysis.repositories import (
    ScaffoldTreeJobRepository,
    UmapJobRepository,
)
from cellar.application.sar_analysis.run_scaffold_tree import RunScaffoldTree
from cellar.application.sar_analysis.run_umap_cluster import RunUmapCluster
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
