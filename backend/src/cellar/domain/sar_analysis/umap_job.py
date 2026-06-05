"""UmapJob — persisted unit of async UMAP compute.

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
from typing import Any
from uuid import UUID

from cellar.domain.sar_analysis.umap_types import UmapResult


class UmapJobStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InvalidUmapJobTransition(Exception):
    pass


_TERMINAL = {
    UmapJobStatus.READY,
    UmapJobStatus.FAILED,
    UmapJobStatus.CANCELLED,
}


@dataclass(frozen=True)
class UmapJob:
    id: UUID
    workspace_id: UUID
    requested_by: UUID
    ids_hash: str
    picker: str
    picker_params: dict[str, Any]
    picker_param_hash: str
    requested_at: datetime
    status: UmapJobStatus = UmapJobStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    result: UmapResult | None = None
    version: int = 1

    @classmethod
    def create(
        cls,
        *,
        workspace_id: UUID,
        requested_by: UUID,
        ids_hash: str,
        picker: str,
        picker_params: dict[str, Any],
        picker_param_hash: str,
        now: datetime,
    ) -> UmapJob:
        return cls(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            requested_by=requested_by,
            ids_hash=ids_hash,
            picker=picker,
            picker_params=dict(picker_params),
            picker_param_hash=picker_param_hash,
            requested_at=now,
        )

    def mark_running(self, now: datetime) -> UmapJob:
        if self.status != UmapJobStatus.PENDING:
            raise InvalidUmapJobTransition(f"Cannot mark RUNNING from {self.status}")
        return replace(self, status=UmapJobStatus.RUNNING, started_at=now)

    def mark_ready(self, result: UmapResult, now: datetime) -> UmapJob:
        if self.status != UmapJobStatus.RUNNING:
            raise InvalidUmapJobTransition(f"Cannot mark READY from {self.status}")
        return replace(
            self,
            status=UmapJobStatus.READY,
            completed_at=now,
            result=result,
        )

    def mark_failed(self, error: str, now: datetime) -> UmapJob:
        if self.status not in {UmapJobStatus.PENDING, UmapJobStatus.RUNNING}:
            raise InvalidUmapJobTransition(f"Cannot mark FAILED from {self.status}")
        return replace(
            self,
            status=UmapJobStatus.FAILED,
            completed_at=now,
            error_message=error,
        )

    def mark_cancelled(self, now: datetime) -> UmapJob:
        if self.status in _TERMINAL:
            raise InvalidUmapJobTransition(f"Cannot CANCEL terminal {self.status}")
        return replace(
            self,
            status=UmapJobStatus.CANCELLED,
            completed_at=now,
        )
