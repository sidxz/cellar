"""SarActivityProjection — persisted async materialization of one activity scalar
per molecule for a color channel, over a member set.

State machine (mirrors RGroupDecompositionRun):
  pending -> running -> {ready | failed | cancelled}
  pending             ->  cancelled

ready / failed / cancelled are terminal.

The aggregate holds only the *header* (channel spec + value count). The
per-molecule scalars are persisted as separate SPARSE rows (see the repository) —
only molecules that have a value, so a LEFT JOIN nulls render as heatmap gaps.
Keyed by (membership_hash, channel_hash); core-independent, reused across cores.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any
from uuid import UUID


class SarActivityProjectionStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InvalidSarProjectionTransition(Exception):
    pass


_TERMINAL = {
    SarActivityProjectionStatus.READY,
    SarActivityProjectionStatus.FAILED,
    SarActivityProjectionStatus.CANCELLED,
}


@dataclass(frozen=True)
class SarActivityProjection:
    id: UUID
    workspace_id: UUID
    requested_by: UUID
    membership_hash: str
    channel_hash: str
    channel_spec: dict[str, Any]
    requested_at: datetime
    status: SarActivityProjectionStatus = SarActivityProjectionStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    value_count: int = 0
    version: int = 1

    @classmethod
    def create(
        cls,
        *,
        workspace_id: UUID,
        requested_by: UUID,
        membership_hash: str,
        channel_hash: str,
        channel_spec: dict[str, Any],
        now: datetime,
    ) -> SarActivityProjection:
        return cls(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            requested_by=requested_by,
            membership_hash=membership_hash,
            channel_hash=channel_hash,
            channel_spec=dict(channel_spec),
            requested_at=now,
        )

    def mark_running(self, now: datetime) -> SarActivityProjection:
        if self.status != SarActivityProjectionStatus.PENDING:
            raise InvalidSarProjectionTransition(f"Cannot mark RUNNING from {self.status}")
        return replace(self, status=SarActivityProjectionStatus.RUNNING, started_at=now)

    def mark_ready(self, *, value_count: int, now: datetime) -> SarActivityProjection:
        if self.status != SarActivityProjectionStatus.RUNNING:
            raise InvalidSarProjectionTransition(f"Cannot mark READY from {self.status}")
        return replace(
            self,
            status=SarActivityProjectionStatus.READY,
            completed_at=now,
            value_count=value_count,
        )

    def mark_failed(self, error: str, now: datetime) -> SarActivityProjection:
        if self.status not in {
            SarActivityProjectionStatus.PENDING,
            SarActivityProjectionStatus.RUNNING,
        }:
            raise InvalidSarProjectionTransition(f"Cannot mark FAILED from {self.status}")
        return replace(
            self,
            status=SarActivityProjectionStatus.FAILED,
            completed_at=now,
            error_message=error,
        )

    def mark_cancelled(self, now: datetime) -> SarActivityProjection:
        if self.status in _TERMINAL:
            raise InvalidSarProjectionTransition(f"Cannot CANCEL terminal {self.status}")
        return replace(self, status=SarActivityProjectionStatus.CANCELLED, completed_at=now)
