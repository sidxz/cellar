"""SAR analysis bounded context bindings: scaffold-tree jobs + use cases.

Wires:
- ``ScaffoldNetworkBuilder``         — Singleton (pure RDKit wrapper)
- ``ScaffoldTreeJobRepository``      — SQLAlchemy impl, per-resolve UoW
- ``BuildScaffoldNetwork``           — Singleton-less factory (fresh UoW each call)
- ``RunScaffoldTree``                — Activity runner used by the Temporal worker
- ``ScaffoldTreeOrchestrator``       — Null when ``TEMPORAL_DISABLED=1``; the live
  ``TemporalScaffoldTreeOrchestrator`` is bound later by ``app.py``'s lifespan
  once the Temporal client is available — same pattern as ``register_export``.
- ``StartScaffoldTreeJob`` / ``GetScaffoldTreeJob`` / ``CancelScaffoldTreeJob``

Note: ``MurckoScaffoldCalculator`` is already registered by ``register_core``.
"""

from __future__ import annotations

import os

from lagom import Container, Singleton
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.application.sar_analysis.build_scaffold_network import BuildScaffoldNetwork
from cellar.application.sar_analysis.cancel_scaffold_tree_job import CancelScaffoldTreeJob
from cellar.application.sar_analysis.get_scaffold_tree_job import GetScaffoldTreeJob
from cellar.application.sar_analysis.repositories import ScaffoldTreeJobRepository
from cellar.application.sar_analysis.run_scaffold_tree import RunScaffoldTree
from cellar.application.sar_analysis.start_scaffold_tree_job import (
    ScaffoldTreeOrchestrator,
    StartScaffoldTreeJob,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.scaffold_tree_job_repository import (
    SQLAlchemyScaffoldTreeJobRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from cellar.infrastructure.rdkit.scaffold_network_builder import ScaffoldNetworkBuilder


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
        )

    def _get(c: Container) -> GetScaffoldTreeJob:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetScaffoldTreeJob(
            repository=SQLAlchemyScaffoldTreeJobRepository(uow),
        )

    def _cancel(c: Container) -> CancelScaffoldTreeJob:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CancelScaffoldTreeJob(
            repository=SQLAlchemyScaffoldTreeJobRepository(uow),
            orchestrator=c[ScaffoldTreeOrchestrator],
        )

    container.define(StartScaffoldTreeJob, _start)
    container.define(GetScaffoldTreeJob, _get)
    container.define(CancelScaffoldTreeJob, _cancel)
