"""StartScaffoldTreeJob — single entry-point for the scaffold-tree endpoint.

Dispatches one of three paths:
1. Cache hit (any size)      -> return tree inline.
2. Cache miss, <= sync_limit -> compute synchronously, persist as a READY job
                                for cache reuse, return tree inline.
3. Cache miss, > sync_limit  -> create a PENDING job, schedule the workflow,
                                return job inline.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol
from uuid import UUID

from cellar.application.sar_analysis.build_scaffold_network import (
    BuildScaffoldNetwork,
    BuildScaffoldNetworkInput,
    compute_ids_hash,
)
from cellar.application.sar_analysis.repositories import ScaffoldTreeJobRepository
from cellar.domain.sar_analysis.scaffold_tree_job import ScaffoldTreeJob
from cellar.domain.sar_analysis.scaffold_tree_types import ScaffoldTreeResult


@dataclass(frozen=True)
class StartScaffoldTreeJobInput:
    molecule_ids: list[UUID]
    workspace_id: UUID
    requested_by: UUID
    now: datetime


@dataclass(frozen=True)
class StartScaffoldTreeJobOutput:
    tree: ScaffoldTreeResult | None
    job: ScaffoldTreeJob | None


class ScaffoldTreeOrchestrator(Protocol):
    async def schedule(
        self, *, job_id: UUID, workspace_id: UUID, molecule_ids: list[UUID]
    ) -> None: ...

    async def cancel(self, *, job_id: UUID) -> None: ...


class StartScaffoldTreeJob:
    def __init__(
        self,
        *,
        builder: BuildScaffoldNetwork,
        repository: ScaffoldTreeJobRepository,
        orchestrator: ScaffoldTreeOrchestrator,
        sync_limit: int = 500,
    ) -> None:
        self._builder = builder
        self._repo = repository
        self._orchestrator = orchestrator
        self._sync_limit = sync_limit

    async def execute(self, payload: StartScaffoldTreeJobInput) -> StartScaffoldTreeJobOutput:
        ids_hash = compute_ids_hash(payload.molecule_ids)

        # Always check cache first regardless of size.
        cached = await self._repo.find_cached(ids_hash=ids_hash, ttl_seconds=3600)
        if cached is not None:
            return StartScaffoldTreeJobOutput(
                tree=replace(
                    cached,
                    stats=replace(cached.stats, cache_hit=True),
                ),
                job=None,
            )

        if len(payload.molecule_ids) <= self._sync_limit:
            # Sync path — compute now + persist as READY for next-time cache hit.
            tree = await self._builder.execute(
                BuildScaffoldNetworkInput(
                    molecule_ids=payload.molecule_ids,
                    workspace_id=payload.workspace_id,
                )
            )
            job = (
                ScaffoldTreeJob.create(
                    workspace_id=payload.workspace_id,
                    requested_by=payload.requested_by,
                    ids_hash=ids_hash,
                    now=payload.now,
                )
                .mark_running(payload.now)
                .mark_ready(tree, payload.now)
            )
            await self._repo.save(job)
            return StartScaffoldTreeJobOutput(tree=tree, job=None)

        # Async path — create pending job + schedule workflow.
        job = ScaffoldTreeJob.create(
            workspace_id=payload.workspace_id,
            requested_by=payload.requested_by,
            ids_hash=ids_hash,
            now=payload.now,
        )
        await self._repo.save(job)
        await self._orchestrator.schedule(
            job_id=job.id,
            workspace_id=payload.workspace_id,
            molecule_ids=list(payload.molecule_ids),
        )
        return StartScaffoldTreeJobOutput(tree=None, job=job)
