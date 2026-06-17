"""StartUmapClusterJob — 3-path dispatch (cache / sync / async)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from cellar.application.sar_analysis.compute_umap_cluster import (
    ComputeUmapCluster,
    ComputeUmapClusterInput,
    compute_ids_hash,
    compute_picker_param_hash,
)
from cellar.application.sar_analysis.repositories import UmapJobRepository
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.umap_job import UmapJob
from cellar.domain.sar_analysis.umap_types import UmapResult


@dataclass(frozen=True)
class StartUmapClusterJobInput:
    molecule_ids: list[UUID]
    picker: str
    picker_params: dict[str, Any]
    workspace_id: UUID
    requested_by: UUID
    now: datetime


@dataclass(frozen=True)
class StartUmapClusterJobOutput:
    result: UmapResult | None
    job: UmapJob | None


class UmapClusterOrchestrator(Protocol):
    async def schedule(
        self,
        *,
        job_id: UUID,
        workspace_id: UUID,
        molecule_ids: list[UUID],
        picker: str,
        picker_params: dict[str, Any],
    ) -> None: ...

    async def cancel(self, *, job_id: UUID) -> None: ...


class StartUmapClusterJob:
    def __init__(
        self,
        *,
        compute: ComputeUmapCluster,
        repository: UmapJobRepository,
        orchestrator: UmapClusterOrchestrator,
        uow: UnitOfWork,
        sync_limit: int = 500,
    ) -> None:
        self._compute = compute
        self._repo = repository
        self._orchestrator = orchestrator
        self._uow = uow
        self._sync_limit = sync_limit

    async def execute(self, payload: StartUmapClusterJobInput) -> StartUmapClusterJobOutput:
        ids_hash = compute_ids_hash(payload.molecule_ids)
        pp_hash = compute_picker_param_hash(payload.picker, payload.picker_params)

        async with self._uow:
            cached = await self._repo.find_cached(
                workspace_id=payload.workspace_id,
                ids_hash=ids_hash,
                picker=payload.picker,
                picker_param_hash=pp_hash,
                ttl_seconds=3600,
            )
        if cached is not None and cached.result is not None:
            return StartUmapClusterJobOutput(result=cached.result, job=None)

        # Partial-cache path: if a prior READY job exists for the same compound
        # set + same Butina threshold, reuse its UMAP coords + cluster
        # assignments and only re-run the picker. Skips the expensive UMAP step
        # when chemists scrub N or switch picker mode at the same threshold.
        threshold = float(payload.picker_params.get("threshold", 0.4))
        async with self._uow:
            partial = await self._repo.find_compatible_for_pick(
                workspace_id=payload.workspace_id,
                ids_hash=ids_hash,
                threshold=threshold,
                ttl_seconds=3600,
            )

        if (
            partial is not None
            and partial.result is not None
            and len(payload.molecule_ids) <= self._sync_limit
        ):
            try:
                result = await self._compute.pick_only(
                    existing=partial.result,
                    picker=payload.picker,
                    picker_params=payload.picker_params,
                )
            except RuntimeError:
                # FP availability shifted since the cache was built — fall
                # through to full compute.
                result = None
            if result is not None:
                job = UmapJob.create(
                    workspace_id=payload.workspace_id,
                    requested_by=payload.requested_by,
                    ids_hash=ids_hash,
                    picker=payload.picker,
                    picker_params=payload.picker_params,
                    picker_param_hash=pp_hash,
                    now=payload.now,
                )
                job.mark_running(payload.now)
                job.mark_ready(result=result, now=payload.now)
                async with self._uow:
                    await self._repo.save(job)
                    await self._uow.commit()
                return StartUmapClusterJobOutput(result=result, job=None)

        if len(payload.molecule_ids) <= self._sync_limit:
            result = await self._compute.execute(
                ComputeUmapClusterInput(
                    molecule_ids=payload.molecule_ids,
                    picker=payload.picker,
                    picker_params=payload.picker_params,
                )
            )
            job = UmapJob.create(
                workspace_id=payload.workspace_id,
                requested_by=payload.requested_by,
                ids_hash=ids_hash,
                picker=payload.picker,
                picker_params=payload.picker_params,
                picker_param_hash=pp_hash,
                now=payload.now,
            )
            job.mark_running(payload.now)
            job.mark_ready(result=result, now=payload.now)
            async with self._uow:
                await self._repo.save(job)
                await self._uow.commit()
            return StartUmapClusterJobOutput(result=result, job=None)

        # Async path.
        job = UmapJob.create(
            workspace_id=payload.workspace_id,
            requested_by=payload.requested_by,
            ids_hash=ids_hash,
            picker=payload.picker,
            picker_params=payload.picker_params,
            picker_param_hash=pp_hash,
            now=payload.now,
        )
        async with self._uow:
            await self._repo.save(job)
            await self._uow.commit()
        await self._orchestrator.schedule(
            job_id=job.id,
            workspace_id=payload.workspace_id,
            molecule_ids=list(payload.molecule_ids),
            picker=payload.picker,
            picker_params=payload.picker_params,
        )
        return StartUmapClusterJobOutput(result=None, job=job)
