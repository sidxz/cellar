"""ExportJob aggregate root — tracks an async export request lifecycle."""

from __future__ import annotations

import uuid
from datetime import datetime, UTC
from typing import Any

from cellar.domain.export.enums import ExportFormat, ExportSource, ExportStatus
from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.shared.errors import ConflictError

_TERMINAL = {
    ExportStatus.READY,
    ExportStatus.FAILED,
    ExportStatus.CANCELLED,
    ExportStatus.EXPIRED,
}


class ExportJob(AggregateRoot):
    """An async export job — tracks lifecycle from PENDING through READY/FAILED/EXPIRED.

    State machine:
        pending -[mark_running]-> running
            -[mark_ready]-> ready -[mark_expired]-> expired
            -[mark_failed]-> failed
            -[request_cancel]-> cancel_requested -[mark_cancelled]-> cancelled
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        requested_by: uuid.UUID,
        source: ExportSource,
        format: ExportFormat,
        query_snapshot: dict[str, Any],
        filename: str,
        status: ExportStatus = ExportStatus.PENDING,
        row_count: int | None = None,
        progress: float | None = None,
        file_key: str | None = None,
        byte_size: int | None = None,
        content_type: str | None = None,
        error_message: str | None = None,
        requested_at: datetime | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        expires_at: datetime | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        self.workspace_id = workspace_id
        self.requested_by = requested_by
        self.source = source
        self.format = format
        self.query_snapshot = query_snapshot
        self.filename = filename
        self.status = status
        self.row_count = row_count
        self.progress = progress
        self.file_key = file_key
        self.byte_size = byte_size
        self.content_type = content_type
        self.error_message = error_message
        self.requested_at = requested_at or datetime.now(UTC)
        self.started_at = started_at
        self.completed_at = completed_at
        self.expires_at = expires_at

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        id: uuid.UUID,
        workspace_id: uuid.UUID,
        requested_by: uuid.UUID,
        source: ExportSource,
        format: ExportFormat,
        query_snapshot: dict[str, Any],
        filename: str,
    ) -> "ExportJob":
        return cls(
            id=id,
            workspace_id=workspace_id,
            requested_by=requested_by,
            source=source,
            format=format,
            query_snapshot=query_snapshot,
            filename=filename,
        )

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def mark_running(self) -> None:
        if self.status != ExportStatus.PENDING:
            raise ConflictError(f"Cannot start job in status {self.status}")
        self.status = ExportStatus.RUNNING
        self.started_at = datetime.now(UTC)
        self.version += 1

    def set_row_count(self, n: int) -> None:
        if self.status in _TERMINAL:
            raise ConflictError(f"Cannot set row count on job in status {self.status}")
        self.row_count = max(int(n), 0)
        self.version += 1

    def report_progress(self, p: float) -> None:
        if self.status in _TERMINAL:
            raise ConflictError(f"Cannot report progress on job in status {self.status}")
        self.progress = max(0.0, min(1.0, float(p)))
        self.version += 1

    def mark_ready(
        self,
        file_key: str,
        byte_size: int,
        content_type: str,
        expires_at: datetime,
    ) -> None:
        if self.status != ExportStatus.RUNNING:
            raise ConflictError(f"Cannot mark job ready in status {self.status}")
        self.status = ExportStatus.READY
        self.file_key = file_key
        self.byte_size = byte_size
        self.content_type = content_type
        self.expires_at = expires_at
        self.completed_at = datetime.now(UTC)
        self.progress = 1.0
        self.version += 1

    def mark_failed(self, error: str) -> None:
        if self.status in _TERMINAL:
            raise ConflictError(f"Cannot mark job failed in status {self.status}")
        self.status = ExportStatus.FAILED
        self.error_message = error
        self.completed_at = datetime.now(UTC)
        self.version += 1

    def request_cancel(self) -> None:
        if self.status in _TERMINAL:
            raise ConflictError(f"Cannot cancel job in status {self.status}")
        self.status = ExportStatus.CANCEL_REQUESTED
        self.version += 1

    def mark_cancelled(self) -> None:
        if self.status != ExportStatus.CANCEL_REQUESTED:
            raise ConflictError(f"Cannot mark job cancelled in status {self.status}")
        self.status = ExportStatus.CANCELLED
        self.completed_at = datetime.now(UTC)
        self.version += 1

    def mark_expired(self) -> None:
        if self.status != ExportStatus.READY:
            raise ConflictError(f"Cannot expire job in status {self.status}")
        self.status = ExportStatus.EXPIRED
        self.file_key = None
        self.version += 1
