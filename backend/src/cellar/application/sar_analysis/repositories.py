"""Repository protocols for the sar_analysis context."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from cellar.domain.sar_analysis.activity_projection_types import ActivityScalar
from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRun
from cellar.domain.sar_analysis.rgroup_types import RGroupAssignment
from cellar.domain.sar_analysis.sar_activity_projection import SarActivityProjection
from cellar.domain.sar_analysis.scaffold_tree_job import ScaffoldTreeJob
from cellar.domain.sar_analysis.scaffold_tree_types import ScaffoldTreeResult
from cellar.domain.sar_analysis.umap_job import UmapJob


class ScaffoldTreeJobRepository(Protocol):
    async def save(self, job: ScaffoldTreeJob) -> None: ...

    async def find_by_id(self, job_id: UUID, *, workspace_id: UUID) -> ScaffoldTreeJob | None: ...

    async def find_cached(
        self, *, ids_hash: str, ttl_seconds: int | None
    ) -> ScaffoldTreeResult | None:
        """Return the cached tree for ``ids_hash``.

        ``ttl_seconds=None`` means no time-based expiry: a ready result is
        valid until the member set changes (which changes ``ids_hash``). The
        hash is the sole invalidation key.
        """
        ...


class UmapJobRepository(Protocol):
    async def save(self, job: UmapJob) -> None: ...

    async def find_by_id(self, job_id: UUID, *, workspace_id: UUID) -> UmapJob | None: ...

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


class RGroupDecompositionRunRepository(Protocol):
    async def save(self, run: RGroupDecompositionRun) -> None: ...

    async def find_by_id_in_workspace(
        self, workspace_id: UUID, id: UUID
    ) -> RGroupDecompositionRun | None: ...

    async def find_cached(
        self, *, workspace_id: UUID, membership_hash: str, core_hash: str
    ) -> RGroupDecompositionRun | None:
        """Return the latest READY run for this workspace's (membership_hash,
        core_hash), or None. No TTL: a ready run is valid until membership or core
        changes (each of which changes a hash). Scoped to ``workspace_id`` for
        defense-in-depth — like the sibling projection cache — so a hash collision
        can never surface another tenant's run. Assignment rows for the returned
        run are already persisted under its id."""
        ...

    async def write_assignments(
        self, run_id: UUID, assignments: list[RGroupAssignment]
    ) -> None: ...

    async def delete_assignments(self, run_id: UUID) -> None:
        """Remove all assignment rows for a run, so a re-run is idempotent."""
        ...

    async def fetch_assignments(
        self, run_id: UUID, *, workspace_id: UUID, offset: int, limit: int
    ) -> list[RGroupAssignment]: ...

    async def count_assignments(self, run_id: UUID, *, workspace_id: UUID) -> int: ...


class SarActivityProjectionRepository(Protocol):
    async def save(self, projection: SarActivityProjection) -> None: ...

    async def find_by_id(
        self, projection_id: UUID, *, workspace_id: UUID
    ) -> SarActivityProjection | None: ...

    async def find_cached(
        self, *, workspace_id: UUID, membership_hash: str, channel_hash: str
    ) -> SarActivityProjection | None:
        """Latest READY projection for this workspace's (membership_hash,
        channel_hash), or None. No TTL: valid until membership or channel changes
        (each changes a hash). Scoped to ``workspace_id`` for defense-in-depth —
        the hash inputs are already workspace-scoped, but the cache key is
        filtered explicitly like every other lookup. Value rows for the returned
        projection are already persisted."""
        ...

    async def write_values(self, projection_id: UUID, values: list[ActivityScalar]) -> None: ...

    async def delete_values(self, projection_id: UUID) -> None:
        """Remove all value rows for a projection, so a re-run is idempotent."""
        ...

    async def count_values(self, projection_id: UUID, *, workspace_id: UUID) -> int: ...
