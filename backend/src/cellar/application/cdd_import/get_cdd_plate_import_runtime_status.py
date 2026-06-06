"""GetCddPlateImportRuntimeStatus — runtime + DB fallback + crash sync."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.cdd_import.cdd_plate_import_orchestrator import (
    CddPlateImportOrchestrator,
)
from cellar.application.cdd_import.get_cdd_plate_import_status import (
    GetCddPlateImportStatusFromDb,
    GetCddPlateImportStatusQuery,
    SyncFailedCddPlateImport,
)
from cellar.application.orchestration.workflow_status import (
    WorkflowOrchestratorUnavailable,
)
from cellar.application.shared.query import Query
from cellar.domain.shared.errors import DomainError, NotFoundError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class GetCddPlateImportRuntimeStatusQuery(Query):
    workspace_id: uuid.UUID
    workflow_id: str


@dataclass(frozen=True)
class CddPlateImportStatusView:
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


class GetCddPlateImportRuntimeStatus:
    def __init__(
        self,
        orchestrator: CddPlateImportOrchestrator,
        db_status: GetCddPlateImportStatusFromDb,
        sync_failed: SyncFailedCddPlateImport,
    ) -> None:
        self._orchestrator = orchestrator
        self._db_status = db_status
        self._sync_failed = sync_failed

    async def __call__(
        self,
        input: GetCddPlateImportRuntimeStatusQuery,
        auth: AuthContext | None = None,
    ) -> Result[CddPlateImportStatusView, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)

        try:
            progress = await self._orchestrator.get_progress(input.workflow_id)
        except NotFoundError:
            return await self._fallback_to_db(input, auth)
        except WorkflowOrchestratorUnavailable:
            return await self._fallback_to_db(input, auth)
        except Exception:
            logger.warning(
                "orchestrator_get_progress_failed: workflow_id=%s — falling back to DB",
                input.workflow_id,
            )
            return await self._fallback_to_db(input, auth)

        if progress.status == "failed":
            await self._sync_failed.run(input.workspace_id, progress.import_id)

        return Success(
            CddPlateImportStatusView(
                import_id=progress.import_id,
                status=progress.status,
                total_count=progress.total_count,
                plates_registered=progress.plates_registered,
                plates_duplicate=progress.plates_duplicate,
                plates_error=progress.plates_error,
                wells_mapped=progress.wells_mapped,
                wells_unresolved=progress.wells_unresolved,
                current_offset=progress.current_offset,
                pages_processed=progress.pages_processed,
            )
        )

    async def _fallback_to_db(
        self,
        input: GetCddPlateImportRuntimeStatusQuery,
        auth: AuthContext | None,
    ) -> Result[CddPlateImportStatusView, DomainError]:
        result = await self._db_status(
            GetCddPlateImportStatusQuery(
                workspace_id=input.workspace_id,
                workflow_id=input.workflow_id,
            ),
            auth=auth,
        )
        if isinstance(result, Failure):
            return result
        data = result.unwrap()
        return Success(
            CddPlateImportStatusView(
                import_id=data.import_id,
                status=data.status,
                total_count=data.total_count,
                plates_registered=data.plates_registered,
                plates_duplicate=data.plates_duplicate,
                plates_error=data.plates_error,
                wells_mapped=data.wells_mapped,
                wells_unresolved=data.wells_unresolved,
                current_offset=data.current_offset,
                pages_processed=data.pages_processed,
            )
        )
