"""UmapJob — persisted unit of async UMAP compute.

Lifecycle (see ``AsyncJob``): pending -> running -> {ready | failed | cancelled};
pending -> cancelled. The result is stored on the header (no child rows).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from cellar.domain.sar_analysis.umap_types import UmapResult
from cellar.domain.shared.async_job import AsyncJob, AsyncJobStatus


class UmapJob(AsyncJob):
    def __init__(
        self,
        *,
        workspace_id: UUID,
        requested_by: UUID,
        ids_hash: str,
        picker: str,
        picker_params: dict[str, Any],
        picker_param_hash: str,
        requested_at: datetime,
        id: UUID | None = None,
        status: AsyncJobStatus = AsyncJobStatus.PENDING,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
        result: UmapResult | None = None,
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
        self.picker = picker
        self.picker_params = dict(picker_params)
        self.picker_param_hash = picker_param_hash
        self.result = result

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
            workspace_id=workspace_id,
            requested_by=requested_by,
            ids_hash=ids_hash,
            picker=picker,
            picker_params=picker_params,
            picker_param_hash=picker_param_hash,
            requested_at=now,
        )

    def mark_ready(self, *, result: UmapResult, now: datetime) -> None:
        self._enter_ready(now)
        self.result = result
