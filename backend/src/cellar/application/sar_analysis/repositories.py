"""Repository protocols for the sar_analysis context."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from cellar.domain.sar_analysis.scaffold_tree_job import ScaffoldTreeJob
from cellar.domain.sar_analysis.scaffold_tree_types import ScaffoldTreeResult
from cellar.domain.sar_analysis.umap_job import UmapJob


class ScaffoldTreeJobRepository(Protocol):
    async def save(self, job: ScaffoldTreeJob) -> None: ...

    async def find_by_id(
        self, job_id: UUID, *, workspace_id: UUID
    ) -> ScaffoldTreeJob | None: ...

    async def find_cached(
        self, *, ids_hash: str, ttl_seconds: int
    ) -> ScaffoldTreeResult | None: ...


class UmapJobRepository(Protocol):
    async def save(self, job: UmapJob) -> None: ...

    async def find_by_id(
        self, job_id: UUID, *, workspace_id: UUID
    ) -> UmapJob | None: ...

    async def find_cached(
        self,
        *,
        workspace_id: UUID,
        ids_hash: str,
        picker: str,
        picker_param_hash: str,
        ttl_seconds: int,
    ) -> UmapJob | None: ...

    async def find_compatible_for_pick(
        self,
        *,
        workspace_id: UUID,
        ids_hash: str,
        threshold: float,
        ttl_seconds: int,
    ) -> UmapJob | None: ...
