"""GetCddMoleculeImportStatus — DB fallback + sync failed import status."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_workspace_role
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.repository import CddMoleculeImportRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetCddMoleculeImportStatusQuery(Query):
    workspace_id: uuid.UUID
    workflow_id: str


@dataclass(frozen=True)
class CddMoleculeImportStatusResult:
    import_id: str
    status: str
    total_count: int
    registered_count: int
    duplicate_count: int
    error_count: int
    skipped_count: int
    current_offset: int
    pages_processed: int


class GetCddMoleculeImportStatusFromDb:
    """Fallback: read CDD molecule import status from DB.

    Used when Temporal query fails or returns stale data.
    """

    def __init__(self, uow: UnitOfWork, repo: CddMoleculeImportRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        input: GetCddMoleculeImportStatusQuery,
        auth: AuthContext | None = None,
    ) -> Result[CddMoleculeImportStatusResult, DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            imp = await self._repo.find_by_workflow_id_in_workspace(
                input.workspace_id, input.workflow_id
            )
        if imp is None:
            return Failure(NotFoundError("CddMoleculeImport", input.workflow_id))
        return Success(CddMoleculeImportStatusResult(
            import_id=str(imp.id),
            status=imp.status.value,
            total_count=imp.total_count,
            registered_count=imp.registered_count,
            duplicate_count=imp.duplicate_count,
            error_count=imp.error_count,
            skipped_count=imp.skipped_count,
            current_offset=imp.last_processed_offset,
            pages_processed=0,
        ))


class SyncFailedCddMoleculeImport:
    """Update a crashed import's DB record to FAILED.

    Called when the status endpoint detects the Temporal workflow is
    terminated but the DB aggregate is still in a non-terminal state.
    Best-effort -- swallows errors so it never breaks the status response.
    """

    def __init__(self, uow: UnitOfWork, repo: CddMoleculeImportRepository) -> None:
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
