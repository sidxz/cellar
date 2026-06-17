"""RGroupDecompositionRun — persisted async R-group decomposition over a member
set against one core.

Lifecycle (see ``AsyncJob``): pending -> running -> {ready | failed | cancelled};
pending -> cancelled. The aggregate holds only the *header* (discovered labels +
counts); per-molecule assignments are separate rows (see the repository).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from cellar.domain.shared.async_job import AsyncJob, AsyncJobStatus


class RGroupDecompositionRun(AsyncJob):
    def __init__(
        self,
        *,
        workspace_id: UUID,
        requested_by: UUID,
        membership_hash: str,
        core_smiles: str,
        core_hash: str,
        requested_at: datetime,
        id: UUID | None = None,
        status: AsyncJobStatus = AsyncJobStatus.PENDING,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
        rgroup_labels: list[str] | None = None,
        matched_count: int = 0,
        unmatched_count: int = 0,
        total_count: int = 0,
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
        self.membership_hash = membership_hash
        self.core_smiles = core_smiles
        self.core_hash = core_hash
        self.rgroup_labels = list(rgroup_labels) if rgroup_labels is not None else []
        self.matched_count = matched_count
        self.unmatched_count = unmatched_count
        self.total_count = total_count

    @classmethod
    def create(
        cls,
        *,
        workspace_id: UUID,
        requested_by: UUID,
        membership_hash: str,
        core_smiles: str,
        core_hash: str,
        now: datetime,
    ) -> RGroupDecompositionRun:
        return cls(
            workspace_id=workspace_id,
            requested_by=requested_by,
            membership_hash=membership_hash,
            core_smiles=core_smiles,
            core_hash=core_hash,
            requested_at=now,
        )

    def mark_ready(
        self,
        *,
        rgroup_labels: list[str],
        matched_count: int,
        unmatched_count: int,
        total_count: int,
        now: datetime,
    ) -> None:
        self._enter_ready(now)
        self.rgroup_labels = list(rgroup_labels)
        self.matched_count = matched_count
        self.unmatched_count = unmatched_count
        self.total_count = total_count
