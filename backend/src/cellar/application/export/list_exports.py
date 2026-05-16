"""list_exports — keyset-paginated listing of export jobs for a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace
from cellar.application.export.get_export_status import ExportStatusView
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.export.enums import ExportStatus
from cellar.domain.export.export_job import ExportJob
from cellar.domain.export.repository import ExportJobRepository
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListExportsQuery:
    workspace_id: uuid.UUID
    limit: int = 50
    cursor_requested_at: datetime | None = None


class ListExports:
    """Return a paginated list of export jobs newest-first."""

    def __init__(self, uow: UnitOfWork, repo: ExportJobRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        q: ListExportsQuery,
        *,
        auth: AuthContext,
    ) -> Result[list[ExportStatusView], DomainError]:
        require_same_workspace(auth, q.workspace_id)

        async with self._uow:
            jobs = await self._repo.list_in_workspace(
                q.workspace_id,
                limit=q.limit,
                cursor_requested_at=q.cursor_requested_at,
            )

        return Success([_to_view(j) for j in jobs])


def _to_view(job: ExportJob) -> ExportStatusView:
    return ExportStatusView(
        id=job.id,
        status=job.status,
        format=job.format,
        row_count=job.row_count,
        progress=job.progress,
        error_message=job.error_message,
        download_url=(
            f"/api/v1/exports/{job.id}/download"
            if job.status == ExportStatus.READY
            else None
        ),
        byte_size=job.byte_size,
        filename=job.filename,
        requested_at=job.requested_at,
        completed_at=job.completed_at,
        expires_at=job.expires_at,
    )
