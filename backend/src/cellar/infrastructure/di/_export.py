"""Export bounded context bindings: export jobs, use cases, render runner."""

from __future__ import annotations

import os

from lagom import Container, Singleton
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.application.export.cancel_export import CancelExport
from cellar.application.export.get_export_status import GetExportStatus
from cellar.application.export.list_exports import ListExports
from cellar.application.export.orchestration import ExportOrchestrator
from cellar.application.export.prepare_export_download import PrepareExportDownload
from cellar.application.export.purge_expired_exports import PurgeExpiredExports
from cellar.application.export.render_export import RenderExport
from cellar.application.export.row_streams.search_results import SearchResultsRowStream
from cellar.application.export.start_export import StartExport
from cellar.application.research_organization.execute_search import ExecuteSearch
from cellar.application.screening.get_protocol import ListProtocols, ListProtocolsQuery
from cellar.application.screening.molecule_activity_service import MoleculeActivityService
from cellar.domain.export.repository import ExportJobRepository
from cellar.infrastructure.persistence.sqlalchemy.export.export_job_repository import (
    SqlAlchemyExportJobRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (
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
from cellar.infrastructure.persistence.sqlalchemy.research_organization.saved_search_repository import (
    SQLAlchemySavedSearchRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from cellar.infrastructure.storage.fsspec_client import FsspecStorageClient
from cellar.application.chemical_registration.molecule_reader import MoleculeReader


def register_export(container: Container) -> None:
    # ── ExportJobRepository ────────────────────────────────────────────────────
    def _export_job_repo(c: Container) -> ExportJobRepository:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SqlAlchemyExportJobRepository(uow)  # type: ignore[return-value]

    container.define(ExportJobRepository, _export_job_repo)

    # FsspecStorageClient is bound as a Singleton in _core.py — resolve via c[FsspecStorageClient].

    # ── RenderExport ───────────────────────────────────────────────────────────
    def _render_export(c: Container) -> RenderExport:
        session_factory = c[async_sessionmaker]
        molecule_reader = c[MoleculeReader]
        storage = c[FsspecStorageClient]
        uow = AsyncUnitOfWork(session_factory)
        repo = SqlAlchemyExportJobRepository(uow)

        def _build_search_stream(job):  # type: ignore[no-untyped-def]
            # Per-job fresh UoW + ExecuteSearch so sessions don't bleed across jobs.
            j_uow = AsyncUnitOfWork(session_factory)
            execute_search = ExecuteSearch(
                j_uow,
                molecule_reader,
                SQLAlchemySavedSearchRepository(j_uow),
                activity_service=MoleculeActivityService(
                    uow=j_uow,
                    readout_repo=SQLAlchemyReadoutDataRepository(j_uow),
                    curve_repo=SQLAlchemyDoseResponseCurveRepository(j_uow),
                    protocol_repo=SQLAlchemyProtocolRepository(j_uow),
                    run_repo=SQLAlchemyRunRepository(j_uow),
                ),
            )

            async def _protocols_reader(workspace_id):  # type: ignore[no-untyped-def]
                from returns.result import Success

                p_uow = AsyncUnitOfWork(session_factory)
                lp = ListProtocols(p_uow, SQLAlchemyProtocolRepository(p_uow))
                result = await lp(ListProtocolsQuery(workspace_id=workspace_id), auth=None)
                return result.unwrap().items if isinstance(result, Success) else []

            return SearchResultsRowStream(
                workspace_id=job.workspace_id,
                payload=job.query_snapshot,
                execute_search=execute_search,
                protocols_reader=_protocols_reader,
                requested_by=job.requested_by,
                format=job.format.value,
            )

        return RenderExport(
            uow=uow,
            repo=repo,
            storage=storage,
            build_search_stream=_build_search_stream,
        )

    container.define(RenderExport, _render_export)

    # ── ExportOrchestrator ─────────────────────────────────────────────────────
    # When TEMPORAL_DISABLED=1, bind NullExportOrchestrator here so the whole
    # container is self-contained (used in tests and local dev without Temporal).
    # In production, app.py's lifespan awaits the Temporal client and overrides
    # this binding with TemporalExportOrchestrator — same pattern as
    # BulkRegistrationOrchestrator, CddMoleculeImportOrchestrator, etc.
    if os.environ.get("TEMPORAL_DISABLED") == "1":
        from cellar.infrastructure.temporal.orchestrators.export import NullExportOrchestrator

        def _null_orchestrator(c: Container) -> NullExportOrchestrator:
            return NullExportOrchestrator(c[RenderExport])

        container.define(ExportOrchestrator, _null_orchestrator)

    # ── Use cases ──────────────────────────────────────────────────────────────

    def _start_export(c: Container) -> StartExport:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        repo = SqlAlchemyExportJobRepository(uow)
        return StartExport(uow, repo, c[ExportOrchestrator])

    def _get_export_status(c: Container) -> GetExportStatus:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        repo = SqlAlchemyExportJobRepository(uow)
        return GetExportStatus(uow, repo)

    def _cancel_export(c: Container) -> CancelExport:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        repo = SqlAlchemyExportJobRepository(uow)
        return CancelExport(uow, repo, c[ExportOrchestrator])

    def _list_exports(c: Container) -> ListExports:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        repo = SqlAlchemyExportJobRepository(uow)
        return ListExports(uow, repo)

    def _purge_expired_exports(c: Container) -> PurgeExpiredExports:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        repo = SqlAlchemyExportJobRepository(uow)
        return PurgeExpiredExports(uow, repo, c[FsspecStorageClient])

    def _prepare_export_download(c: Container) -> PrepareExportDownload:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        repo = SqlAlchemyExportJobRepository(uow)
        return PrepareExportDownload(uow, repo)

    container.define(StartExport, _start_export)
    container.define(GetExportStatus, _get_export_status)
    container.define(CancelExport, _cancel_export)
    container.define(ListExports, _list_exports)
    container.define(PurgeExpiredExports, _purge_expired_exports)
    container.define(PrepareExportDownload, _prepare_export_download)
