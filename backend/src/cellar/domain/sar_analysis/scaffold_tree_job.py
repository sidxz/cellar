"""ScaffoldTreeJob — persisted unit of async scaffold-network compute.

State machine:
  pending -> running -> {ready | failed | cancelled}
  pending             ->  cancelled

ready / failed / cancelled are terminal.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from cellar.domain.sar_analysis.scaffold_tree_types import ScaffoldTreeResult


class ScaffoldTreeJobStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InvalidScaffoldTreeJobTransition(Exception):
    pass


_TERMINAL = {
    ScaffoldTreeJobStatus.READY,
    ScaffoldTreeJobStatus.FAILED,
    ScaffoldTreeJobStatus.CANCELLED,
}


@dataclass(frozen=True)
class ScaffoldTreeJob:
    id: UUID
    workspace_id: UUID
    requested_by: UUID
    ids_hash: str
    requested_at: datetime
    status: ScaffoldTreeJobStatus = ScaffoldTreeJobStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    result: ScaffoldTreeResult | None = None
    version: int = 1

    @classmethod
    def create(
        cls,
        *,
        workspace_id: UUID,
        requested_by: UUID,
        ids_hash: str,
        now: datetime,
    ) -> ScaffoldTreeJob:
        return cls(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            requested_by=requested_by,
            ids_hash=ids_hash,
            requested_at=now,
        )

    def mark_running(self, now: datetime) -> ScaffoldTreeJob:
        if self.status != ScaffoldTreeJobStatus.PENDING:
            raise InvalidScaffoldTreeJobTransition(f"Cannot mark RUNNING from {self.status}")
        return replace(self, status=ScaffoldTreeJobStatus.RUNNING, started_at=now)

    def mark_ready(self, result: ScaffoldTreeResult, now: datetime) -> ScaffoldTreeJob:
        if self.status != ScaffoldTreeJobStatus.RUNNING:
            raise InvalidScaffoldTreeJobTransition(f"Cannot mark READY from {self.status}")
        return replace(
            self,
            status=ScaffoldTreeJobStatus.READY,
            completed_at=now,
            result=result,
        )

    def mark_failed(self, error: str, now: datetime) -> ScaffoldTreeJob:
        if self.status not in {
            ScaffoldTreeJobStatus.PENDING,
            ScaffoldTreeJobStatus.RUNNING,
        }:
            raise InvalidScaffoldTreeJobTransition(f"Cannot mark FAILED from {self.status}")
        return replace(
            self,
            status=ScaffoldTreeJobStatus.FAILED,
            completed_at=now,
            error_message=error,
        )

    def mark_cancelled(self, now: datetime) -> ScaffoldTreeJob:
        if self.status in _TERMINAL:
            raise InvalidScaffoldTreeJobTransition(f"Cannot CANCEL terminal {self.status}")
        return replace(
            self,
            status=ScaffoldTreeJobStatus.CANCELLED,
            completed_at=now,
        )
