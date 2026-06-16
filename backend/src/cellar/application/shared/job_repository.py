"""JobRepository — the minimal repository surface the shared async-job helpers
(``claim_job`` / ``finalize_if_still_running`` / ``MarkJobFailed``) depend on.

Satisfied structurally by any repository extending ``SQLAlchemyRepository``
whose aggregate is an ``AsyncJob`` — it already exposes
``find_by_id_in_workspace`` and ``save``.
"""

from __future__ import annotations

from typing import Protocol, TypeVar
from uuid import UUID

from cellar.domain.shared.async_job import AsyncJob

JobT = TypeVar("JobT", bound=AsyncJob)


class JobRepository(Protocol[JobT]):
    async def find_by_id_in_workspace(self, workspace_id: UUID, id: UUID) -> JobT | None: ...

    async def save(self, aggregate: JobT) -> None: ...
