"""ScaffoldTreeJob — persisted unit of async scaffold-network compute.

Lifecycle (see ``AsyncJob``): pending -> running -> {ready | failed | cancelled};
pending -> cancelled. The result tree is stored on the header (no child rows).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from cellar.domain.sar_analysis.scaffold_tree_types import ScaffoldTreeResult
from cellar.domain.shared.async_job import AsyncJob, AsyncJobStatus


class ScaffoldTreeJob(AsyncJob):
    def __init__(
        self,
        *,
        workspace_id: UUID,
        requested_by: UUID,
        ids_hash: str,
        requested_at: datetime,
        id: UUID | None = None,
        status: AsyncJobStatus = AsyncJobStatus.PENDING,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
        result: ScaffoldTreeResult | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(
            id=id,
            workspace_id=workspace_id,
            requested_by=requested_by,
            requested_at=requested_at,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            error_message=error_message,
            version=version,
        )
        self.ids_hash = ids_hash
        self.result = result

    @classmethod
    def create(
        cls, *, workspace_id: UUID, requested_by: UUID, ids_hash: str, now: datetime
    ) -> ScaffoldTreeJob:
        return cls(
            workspace_id=workspace_id,
            requested_by=requested_by,
            ids_hash=ids_hash,
            requested_at=now,
        )

    def mark_ready(self, *, result: ScaffoldTreeResult, now: datetime) -> None:
        self._enter_ready(now)
        self.result = result
