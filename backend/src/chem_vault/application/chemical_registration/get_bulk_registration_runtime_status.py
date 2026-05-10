"""GetBulkRegistrationRuntimeStatus — query the orchestrator for live progress.

Bulk registration has no DB-side aggregate to fall back to, so this is a
thin wrapper around the orchestrator. Errors propagate as ``Failure``
results so callers stay on the railway.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_workspace_role
from chem_vault.application.chemical_registration.bulk_registration_orchestrator import (
    BulkRegistrationOrchestrator,
)
from chem_vault.application.shared.query import Query
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetBulkRegistrationRuntimeStatusQuery(Query):
    workspace_id: uuid.UUID
    workflow_id: str


@dataclass(frozen=True)
class BulkRegistrationStatusView:
    bulk_reg_id: str
    status: str
    total_count: int
    registered_count: int
    duplicate_count: int
    error_count: int
    disclosed_count: int
    merge_candidate_count: int
    conflict_count: int
    merge_candidates: list[dict]
    chunks_processed: int
    chunks_total: int


class GetBulkRegistrationRuntimeStatus:
    def __init__(self, orchestrator: BulkRegistrationOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def __call__(
        self,
        input: GetBulkRegistrationRuntimeStatusQuery,
        auth: AuthContext | None = None,
    ) -> Result[BulkRegistrationStatusView, DomainError]:
        require_workspace_role(auth, "viewer")

        try:
            progress = await self._orchestrator.get_progress(input.workflow_id)
        except NotFoundError as exc:
            return Failure(exc)

        return Success(
            BulkRegistrationStatusView(
                bulk_reg_id=progress.bulk_reg_id,
                status=progress.status,
                total_count=progress.total_count,
                registered_count=progress.registered_count,
                duplicate_count=progress.duplicate_count,
                error_count=progress.error_count,
                disclosed_count=progress.disclosed_count,
                merge_candidate_count=progress.merge_candidate_count,
                conflict_count=progress.conflict_count,
                merge_candidates=list(progress.merge_candidates),
                chunks_processed=progress.chunks_processed,
                chunks_total=progress.chunks_total,
            )
        )
