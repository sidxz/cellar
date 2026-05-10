"""GetCddPlateImportStatus — DB fallback + sync failed import status."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_workspace_role
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.inventory.repository import CddPlateImportRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError


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
        async with self._uow:
            imp = await self._repo.find_by_workflow_id_in_workspace(
                input.workspace_id, input.workflow_id
            )
        if imp is None:
            return Failure(NotFoundError("CddPlateImport", input.workflow_id))
        return Success(CddPlateImportStatusResult(
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
        ))


class SyncFailedCddPlateImport:
    """Update a crashed plate import's DB record to FAILED.

    Called when the status endpoint detects the Temporal workflow is
    terminated but the DB aggregate is still in a non-terminal state.
    Best-effort -- swallows errors so it never breaks the status response.
    """

    def __init__(self, uow: UnitOfWork, repo: CddPlateImportRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        workspace_id: uuid.UUID,
        import_id: str,
    ) -> None:
        if not import_id:
            return
        try:
            async with self._uow:
                imp = await self._repo.find_by_id_in_workspace(
                    workspace_id, uuid.UUID(import_id)
                )
                if imp is None:
                    return
                if imp.status.value in ("completed", "completed_with_errors", "failed"):
                    return  # Already terminal
                imp.fail("Workflow crashed (detected by status poll)")
                await self._repo.save(imp)
                await self._uow.commit()
        except Exception:
            pass  # Best-effort
