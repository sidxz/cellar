"""GetCddMoleculeImportRuntimeStatus — runtime + DB fallback + crash sync.

Composes three application services to produce the user-facing status:

1. Ask the orchestrator for live progress.
2. If the runtime says the workflow is gone, fall back to the DB record.
3. If the runtime detects a crash (status was rewritten to ``"failed"``),
   sync the DB aggregate so the next read is consistent and the UI doesn't
   loop on a stale ``"processing"``.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.cdd_import.cdd_molecule_import_orchestrator import (
    CddMoleculeImportOrchestrator,
)
from cellar.application.cdd_import.get_cdd_molecule_import_status import (
    GetCddMoleculeImportStatusFromDb,
    GetCddMoleculeImportStatusQuery,
    SyncFailedCddMoleculeImport,
)
from cellar.application.orchestration.workflow_status import (
    WorkflowOrchestratorUnavailable,
)
from cellar.application.shared.query import Query
from cellar.domain.shared.errors import DomainError, NotFoundError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class GetCddMoleculeImportRuntimeStatusQuery(Query):
    workspace_id: uuid.UUID
    workflow_id: str


@dataclass(frozen=True)
class CddMoleculeImportStatusView:
    """Combined view returned to API callers."""

    import_id: str
    status: str
    total_count: int
    registered_count: int
    duplicate_count: int
    error_count: int
    skipped_count: int
    current_offset: int
    pages_processed: int


class GetCddMoleculeImportRuntimeStatus:
    def __init__(
        self,
        orchestrator: CddMoleculeImportOrchestrator,
        db_status: GetCddMoleculeImportStatusFromDb,
        sync_failed: SyncFailedCddMoleculeImport,
    ) -> None:
        self._orchestrator = orchestrator
        self._db_status = db_status
        self._sync_failed = sync_failed

    async def __call__(
        self,
        input: GetCddMoleculeImportRuntimeStatusQuery,
        auth: AuthContext | None = None,
    ) -> Result[CddMoleculeImportStatusView, DomainError]:
        require_workspace_role(auth, "viewer")

        try:
            progress = await self._orchestrator.get_progress(input.workflow_id)
        except NotFoundError:
            return await self._fallback_to_db(input, auth)
        except WorkflowOrchestratorUnavailable:
            # If the engine itself is unreachable, fall back to whatever the
            # DB has — the UI can still show the last known state.
            return await self._fallback_to_db(input, auth)
        except Exception:
            logger.warning(
                "orchestrator_get_progress_failed: workflow_id=%s — falling back to DB",
                input.workflow_id,
            )
            return await self._fallback_to_db(input, auth)

        # Crash detected: the adapter rewrote status to "failed" because the
        # runtime says the execution is terminal. Bring the DB into line so
        # subsequent polls don't loop.
        if progress.status == "failed":
            await self._sync_failed(input.workspace_id, progress.import_id)

        return Success(
            CddMoleculeImportStatusView(
                import_id=progress.import_id,
                status=progress.status,
                total_count=progress.total_count,
                registered_count=progress.registered_count,
                duplicate_count=progress.duplicate_count,
                error_count=progress.error_count,
                skipped_count=progress.skipped_count,
                current_offset=progress.current_offset,
                pages_processed=progress.pages_processed,
            )
        )

    async def _fallback_to_db(
        self,
        input: GetCddMoleculeImportRuntimeStatusQuery,
        auth: AuthContext | None,
    ) -> Result[CddMoleculeImportStatusView, DomainError]:
        result = await self._db_status(
            GetCddMoleculeImportStatusQuery(
                workspace_id=input.workspace_id,
                workflow_id=input.workflow_id,
            ),
            auth=auth,
        )
        if isinstance(result, Failure):
            return result
        data = result.unwrap()
        return Success(
            CddMoleculeImportStatusView(
                import_id=data.import_id,
                status=data.status,
                total_count=data.total_count,
                registered_count=data.registered_count,
                duplicate_count=data.duplicate_count,
                error_count=data.error_count,
                skipped_count=data.skipped_count,
                current_offset=data.current_offset,
                pages_processed=data.pages_processed,
            )
        )
