"""Export bounded context bindings: export jobs, use cases, render runner."""

from __future__ import annotations

import os
import uuid

from lagom import Container
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.application.export.cancel_export import CancelExport
from cellar.application.export.get_export_status import GetExportStatus
from cellar.application.export.list_exports import ListExports
from cellar.application.export.orchestration import ExportOrchestrator
from cellar.application.export.prepare_export_download import PrepareExportDownload
from cellar.application.export.purge_expired_exports import PurgeExpiredExports
from cellar.application.export.render_export import RenderExport
from cellar.application.export.row_streams.search_results import (
    ExportAuth,
    SearchResultsRowStream,
)
from cellar.application.export.run_report import BuildRunReport, RunReport
from cellar.application.export.start_export import StartExport
from cellar.application.research_organization.execute_search import ExecuteSearch
from cellar.application.screening.get_melting_analysis import GetMeltingAnalysis
from cellar.application.screening.get_protocol import ListProtocols, ListProtocolsQuery
from cellar.application.screening.get_run_curves import GetRunCurves
from cellar.domain.export.repository import ExportJobRepository
from cellar.infrastructure.messaging.event_dispatcher import EventDispatcher
from cellar.infrastructure.persistence.sqlalchemy.export.export_job_repository import (
    SqlAlchemyExportJobRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.run_repository import (
    SQLAlchemyRunRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from cellar.infrastructure.storage.fsspec_client import FsspecStorageClient


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
        storage = c[FsspecStorageClient]
        uow = AsyncUnitOfWork(session_factory)
        repo = SqlAlchemyExportJobRepository(uow)

        def _build_search_stream(job):  # type: ignore[no-untyped-def]
            # The container's ExecuteSearch factory builds a fresh UoW per
            # resolve, so sessions don't bleed across jobs — and the export runs
            # exactly the search the /search endpoint runs (a hand-built copy
            # here had drifted from it).
            execute_search = c[ExecuteSearch]

            async def _protocols_reader(workspace_id):  # type: ignore[no-untyped-def]
                from returns.result import Success

                p_uow = AsyncUnitOfWork(session_factory)
                lp = ListProtocols(p_uow, SQLAlchemyProtocolRepository(p_uow))
                result = await lp(ListProtocolsQuery(workspace_id=workspace_id), auth=None)
                if not isinstance(result, Success):
                    return []
                # ListProtocols yields ProtocolWithTargets; the column builder
                # needs the Protocol itself (id, name, readout_definitions).
                return [item.protocol for item in result.unwrap().items]

            return SearchResultsRowStream(
                workspace_id=job.workspace_id,
                payload=job.query_snapshot,
                execute_search=execute_search,
                protocols_reader=_protocols_reader,
                requested_by=job.requested_by,
                format=job.format.value,
            )

        async def _build_run_report(job) -> RunReport:  # type: ignore[no-untyped-def]
            # Built from the queries the Traces tab reads; the page sends the
            # names it shows (operator, step reviewers), which the worker can't
            # look up without the person's sign-in.
            payload = job.query_snapshot or {}
            r_uow = AsyncUnitOfWork(session_factory)
            build = BuildRunReport(
                uow=r_uow,
                run_repo=SQLAlchemyRunRepository(r_uow),
                protocol_repo=SQLAlchemyProtocolRepository(r_uow),
                get_analysis=c[GetMeltingAnalysis],
                get_curves=c[GetRunCurves],
            )
            people = payload.get("people")
            return await build(
                workspace_id=job.workspace_id,
                run_id=uuid.UUID(str(payload["run_id"])),
                people=people if isinstance(people, dict) else {},
                auth=ExportAuth(job.workspace_id, job.requested_by),
            )

        return RenderExport(
            uow=uow,
            repo=repo,
            storage=storage,
            build_search_stream=_build_search_stream,
            dispatcher=c[EventDispatcher],
            build_run_report=_build_run_report,
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
        return StartExport(uow, repo, c[ExportOrchestrator], c[EventDispatcher])

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
