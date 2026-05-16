"""cancel_export — marks a job as cancel-requested and signals the workflow."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace
from cellar.application.export.orchestration import ExportOrchestrator
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.export.repository import ExportJobRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class CancelExportCommand:
    workspace_id: uuid.UUID
    job_id: uuid.UUID


class CancelExport:
    """Transition an in-flight export job to CANCEL_REQUESTED and signal the runner.

    The workflow signal is best-effort — a failure here does not roll back the
    domain state change so the worker will pick up the transition on its next
    status check.
    """

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
        cmd: CancelExportCommand,
        *,
        auth: AuthContext,
    ) -> Result[None, DomainError]:
        require_same_workspace(auth, cmd.workspace_id)

        async with self._uow:
            job = await self._repo.find_by_id_in_workspace(
                cmd.workspace_id, cmd.job_id
            )
            if job is None:
                return Failure(NotFoundError("ExportJob", str(cmd.job_id)))
            job.request_cancel()
            await self._repo.save(job)
            await self._uow.commit()

        try:
            await self._orchestrator.request_cancel(f"export-{job.id}")
        except Exception:
            pass  # best-effort — worker polls the status column

        return Success(None)
