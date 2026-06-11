"""RGroupDecompositionRun — persisted async R-group decomposition over a member
set against one core.

State machine (mirrors ScaffoldTreeJob):
  pending -> running -> {ready | failed | cancelled}
  pending             ->  cancelled

ready / failed / cancelled are terminal.

The aggregate holds only the *header* (discovered labels + counts). The
per-molecule assignments are persisted as separate rows (see the repository),
so the result scales past what a single JSONB blob could hold.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import UUID


class RGroupDecompositionRunStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InvalidRGroupRunTransition(Exception):
    pass


_TERMINAL = {
    RGroupDecompositionRunStatus.READY,
    RGroupDecompositionRunStatus.FAILED,
    RGroupDecompositionRunStatus.CANCELLED,
}


@dataclass(frozen=True)
class RGroupDecompositionRun:
    id: UUID
    workspace_id: UUID
    requested_by: UUID
    membership_hash: str
    core_smiles: str
    core_hash: str
    requested_at: datetime
    status: RGroupDecompositionRunStatus = RGroupDecompositionRunStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    rgroup_labels: list[str] = field(default_factory=list)
    matched_count: int = 0
    unmatched_count: int = 0
    total_count: int = 0
    version: int = 1

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
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            requested_by=requested_by,
            membership_hash=membership_hash,
            core_smiles=core_smiles,
            core_hash=core_hash,
            requested_at=now,
        )

    def mark_running(self, now: datetime) -> RGroupDecompositionRun:
        if self.status != RGroupDecompositionRunStatus.PENDING:
            raise InvalidRGroupRunTransition(f"Cannot mark RUNNING from {self.status}")
        return replace(self, status=RGroupDecompositionRunStatus.RUNNING, started_at=now)

    def mark_ready(
        self,
        *,
        rgroup_labels: list[str],
        matched_count: int,
        unmatched_count: int,
        total_count: int,
        now: datetime,
    ) -> RGroupDecompositionRun:
        if self.status != RGroupDecompositionRunStatus.RUNNING:
            raise InvalidRGroupRunTransition(f"Cannot mark READY from {self.status}")
        return replace(
            self,
            status=RGroupDecompositionRunStatus.READY,
            completed_at=now,
            rgroup_labels=list(rgroup_labels),
            matched_count=matched_count,
            unmatched_count=unmatched_count,
            total_count=total_count,
        )

    def mark_failed(self, error: str, now: datetime) -> RGroupDecompositionRun:
        if self.status not in {
            RGroupDecompositionRunStatus.PENDING,
            RGroupDecompositionRunStatus.RUNNING,
        }:
            raise InvalidRGroupRunTransition(f"Cannot mark FAILED from {self.status}")
        return replace(
            self,
            status=RGroupDecompositionRunStatus.FAILED,
            completed_at=now,
            error_message=error,
        )

    def mark_cancelled(self, now: datetime) -> RGroupDecompositionRun:
        if self.status in _TERMINAL:
            raise InvalidRGroupRunTransition(f"Cannot CANCEL terminal {self.status}")
        return replace(
            self,
            status=RGroupDecompositionRunStatus.CANCELLED,
            completed_at=now,
        )
