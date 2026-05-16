"""prepare_export_download — resolves a READY export job to the bits the route
needs to serve the file (file_key, content_type, filename).

Separating this from GetExportStatus keeps the status view security-conscious
(no file_key on the wire) while giving the download route a proper UoW boundary.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.export.enums import ExportStatus
from cellar.domain.export.repository import ExportJobRepository
from cellar.domain.shared.errors import ConflictError, DomainError, GoneError, NotFoundError, ValidationError


@dataclass(frozen=True, kw_only=True)
class PrepareExportDownloadQuery:
    workspace_id: uuid.UUID
    job_id: uuid.UUID


@dataclass(frozen=True)
class ExportDownloadView:
    file_key: str
    content_type: str
    filename: str


class PrepareExportDownload:
    """Validate that a job is READY and return the storage address for the file.

    Status → Result mapping:
        READY          → Success(ExportDownloadView(...))
        EXPIRED        → Failure(GoneError)          → 410
        any other      → Failure(ConflictError)       → 409
        job missing    → Failure(NotFoundError)       → 404
        file_key None  → Failure(ValidationError)     → 422
    """

    def __init__(self, uow: UnitOfWork, repo: ExportJobRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        q: PrepareExportDownloadQuery,
        *,
        auth: AuthContext,
    ) -> Result[ExportDownloadView, DomainError]:
        require_same_workspace(auth, q.workspace_id)

        async with self._uow:
            job = await self._repo.find_by_id_in_workspace(q.workspace_id, q.job_id)

        if job is None:
            return Failure(NotFoundError("ExportJob", str(q.job_id)))

        if job.status == ExportStatus.EXPIRED:
            return Failure(
                GoneError("Export expired — re-export the same query.")
            )

        if job.status != ExportStatus.READY:
            return Failure(
                ConflictError(f"Export not ready (status={job.status}).")
            )

        if not job.file_key:
            return Failure(ValidationError("Export file missing."))

        from cellar.domain.export.enums import ExportFormat

        content_type = job.content_type or ExportFormat(job.format).media_type
        filename = job.filename or f"export{ExportFormat(job.format).extension}"

        return Success(
            ExportDownloadView(
                file_key=job.file_key,
                content_type=content_type,
                filename=filename,
            )
        )
