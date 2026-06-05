"""get_export_status — fetches a single ExportJob view for the API."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.export.enums import ExportFormat, ExportStatus
from cellar.domain.export.repository import ExportJobRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetExportStatusQuery:
    workspace_id: uuid.UUID
    job_id: uuid.UUID


@dataclass(frozen=True)
class ExportStatusView:
    id: uuid.UUID
    status: ExportStatus
    format: ExportFormat
    row_count: int | None
    progress: float | None
    error_message: str | None
    download_url: str | None
    byte_size: int | None
    filename: str | None
    requested_at: datetime
    completed_at: datetime | None
    expires_at: datetime | None


class GetExportStatus:
    """Return a polling-friendly view of a single export job."""

    def __init__(self, uow: UnitOfWork, repo: ExportJobRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        q: GetExportStatusQuery,
        *,
        auth: AuthContext,
    ) -> Result[ExportStatusView, DomainError]:
        require_same_workspace(auth, q.workspace_id)

        async with self._uow:
            job = await self._repo.find_by_id_in_workspace(q.workspace_id, q.job_id)

        if job is None:
            return Failure(NotFoundError("ExportJob", str(q.job_id)))

        download_url = (
            f"/api/v1/exports/{job.id}/download" if job.status == ExportStatus.READY else None
        )

        return Success(
            ExportStatusView(
                id=job.id,
                status=job.status,
                format=job.format,
                row_count=job.row_count,
                progress=job.progress,
                error_message=job.error_message,
                download_url=download_url,
                byte_size=job.byte_size,
                filename=job.filename,
                requested_at=job.requested_at,
                completed_at=job.completed_at,
                expires_at=job.expires_at,
            )
        )
