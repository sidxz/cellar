"""Repository protocol for ExportJob persistence."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol, runtime_checkable

from cellar.domain.export.export_job import ExportJob


@runtime_checkable
class ExportJobRepository(Protocol):
    async def save(self, job: ExportJob) -> None: ...

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, job_id: uuid.UUID
    ) -> ExportJob | None: ...

    async def list_in_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int = 50,
        cursor_requested_at: datetime | None = None,
    ) -> list[ExportJob]: ...

    async def find_expired_ready(
        self, before: datetime, *, limit: int = 100
    ) -> list[ExportJob]: ...
