"""GetCddPlateImportStatus — DB fallback + sync failed import status."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog
from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.repository import CddPlateImportRepository
from cellar.domain.shared.errors import DomainError, NotFoundError

_log = structlog.get_logger(__name__)


@dataclass(frozen=True, kw_only=True)
class GetCddPlateImportStatusQuery(Query):
    workspace_id: uuid.UUID
    workflow_id: str


@dataclass(frozen=True)
class CddPlateImportStatusResult:
    import_id: str
    status: str
    total_count: int
    plates_registered: int
    plates_duplicate: int
    plates_error: int
    wells_mapped: int
    wells_unresolved: int
    current_offset: int
    pages_processed: int


class GetCddPlateImportStatusFromDb:
    """Fallback: read CDD plate import status from DB.

    Used when Temporal query fails or returns stale data.
    """

    def __init__(self, uow: UnitOfWork, repo: CddPlateImportRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        input: GetCddPlateImportStatusQuery,
        auth: AuthContext | None = None,
    ) -> Result[CddPlateImportStatusResult, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            imp = await self._repo.find_by_workflow_id_in_workspace(
                input.workspace_id, input.workflow_id
            )
        if imp is None:
            return Failure(NotFoundError("CddPlateImport", input.workflow_id))
        return Success(
            CddPlateImportStatusResult(
                import_id=str(imp.id),
                status=imp.status.value,
                total_count=imp.total_count,
                plates_registered=imp.plates_registered,
                plates_duplicate=imp.plates_duplicate,
                plates_error=imp.plates_error,
                wells_mapped=imp.wells_mapped,
                wells_unresolved=imp.wells_unresolved,
                current_offset=imp.last_processed_offset,
                pages_processed=0,
            )
        )


class SyncFailedCddPlateImport:
    """Internal helper: update a crashed plate import's DB record to FAILED.

    Not a public use case — wired through DI only so the runtime-status
    use case can call it. No auth guard, no Result. Best-effort: swallows
    errors so it never breaks the status response. Use ``run()`` rather
    than ``__call__`` so it doesn't appear in route registrations.
    """

    def __init__(self, uow: UnitOfWork, repo: CddPlateImportRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def run(
        self,
        workspace_id: uuid.UUID,
        import_id: str,
    ) -> None:
        if not import_id:
            return
        try:
            async with self._uow:
                imp = await self._repo.find_by_id_in_workspace(workspace_id, uuid.UUID(import_id))
                if imp is None:
                    return
                if imp.status.value in ("completed", "completed_with_errors", "failed"):
                    return  # Already terminal
                imp.fail("Workflow crashed (detected by status poll)")
                await self._repo.save(imp)
                await self._uow.commit()
        except Exception as exc:
            _log.warning(
                "cdd_plate_import.sync_failed_status_write_failed",
                import_id=import_id,
                workspace_id=str(workspace_id),
                error=str(exc),
                exc_info=True,
            )
