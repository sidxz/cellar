"""start_export — initiates an async export job for a search result set."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.export.orchestration import (
    ExportOrchestrator,
    StartExportWorkflowRequest,
    WorkflowOrchestratorUnavailable,
)
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.export.enums import ExportFormat, ExportSource
from cellar.domain.export.export_job import ExportJob
from cellar.domain.export.repository import ExportJobRepository
from cellar.domain.shared.errors import DomainError, ValidationError


@dataclass(frozen=True, kw_only=True)
class StartExportCommand:
    workspace_id: uuid.UUID
    requested_by: uuid.UUID
    source: ExportSource
    format: ExportFormat
    payload: dict[str, Any]
    filename_hint: str | None = None


@dataclass(frozen=True)
class StartExportResult:
    job_id: uuid.UUID


class StartExport:
    """Create an ExportJob, persist it, then hand off to the workflow orchestrator."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: ExportJobRepository,
        orchestrator: ExportOrchestrator,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._orchestrator = orchestrator

    async def __call__(
        self,
        cmd: StartExportCommand,
        *,
        auth: AuthContext,
    ) -> Result[StartExportResult, DomainError]:
        require_workspace_role(auth, "viewer")

        if cmd.source != ExportSource.SEARCH:
            return Failure(ValidationError(f"Unsupported export source: {cmd.source}"))

        job = ExportJob.create(
            id=uuid.uuid4(),
            workspace_id=cmd.workspace_id,
            requested_by=cmd.requested_by,
            source=cmd.source,
            format=cmd.format,
            query_snapshot=cmd.payload,
            filename=(cmd.filename_hint or "cellar-export") + cmd.format.extension,
        )

        async with self._uow:
            await self._repo.save(job)
            await self._uow.commit()

        try:
            await self._orchestrator.start(
                StartExportWorkflowRequest(
                    job_id=job.id,
                    workspace_id=job.workspace_id,
                )
            )
        except WorkflowOrchestratorUnavailable as exc:
            return Failure(ValidationError(f"Export workflow unavailable: {exc}"))

        return Success(StartExportResult(job_id=job.id))
