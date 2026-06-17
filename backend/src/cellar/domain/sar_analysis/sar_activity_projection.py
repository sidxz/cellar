"""SarActivityProjection — persisted async materialization of one activity scalar
per molecule for a color channel, over a member set.

Lifecycle (see ``AsyncJob``): pending -> running -> {ready | failed | cancelled};
pending -> cancelled. The aggregate holds only the *header* (channel spec + value
count). Per-molecule scalars are persisted as separate SPARSE rows (see the
repository) — only molecules that have a value, so a LEFT JOIN's nulls render as
heatmap gaps. Keyed by (membership_hash, channel_hash); core-independent.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from cellar.domain.shared.async_job import AsyncJob, AsyncJobStatus


class SarActivityProjection(AsyncJob):
    def __init__(
        self,
        *,
        workspace_id: UUID,
        requested_by: UUID,
        membership_hash: str,
        channel_hash: str,
        channel_spec: dict[str, Any],
        requested_at: datetime,
        id: UUID | None = None,
        status: AsyncJobStatus = AsyncJobStatus.PENDING,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
        value_count: int = 0,
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
        self.channel_hash = channel_hash
        self.channel_spec = dict(channel_spec)
        self.value_count = value_count

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
            workspace_id=workspace_id,
            requested_by=requested_by,
            membership_hash=membership_hash,
            channel_hash=channel_hash,
            channel_spec=channel_spec,
            requested_at=now,
        )

    def mark_ready(self, *, value_count: int, now: datetime) -> None:
        self._enter_ready(now)
        self.value_count = value_count
