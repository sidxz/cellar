"""Repository protocols for the sar_analysis context."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from cellar.domain.sar_analysis.scaffold_tree_job import ScaffoldTreeJob
from cellar.domain.sar_analysis.scaffold_tree_types import ScaffoldTreeResult


class ScaffoldTreeJobRepository(Protocol):
    async def save(self, job: ScaffoldTreeJob) -> None: ...

    async def find_by_id(
        self, job_id: UUID, *, workspace_id: UUID
    ) -> ScaffoldTreeJob | None: ...

    async def find_cached(
        self, *, ids_hash: str, ttl_seconds: int
    ) -> ScaffoldTreeResult | None: ...
