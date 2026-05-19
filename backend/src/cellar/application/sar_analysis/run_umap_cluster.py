"""RunUmapCluster — in-process runner: mark running → compute UMAP → mark READY.

The Temporal activity wraps this runner. The NullUmapClusterOrchestrator also
invokes it inline for environments without a Temporal cluster
(``TEMPORAL_DISABLED=1`` or unit tests).

Mirroring RunScaffoldTree, all state-machine transitions are handled here so
that the activity is a thin adapter and the Null path has identical business
semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog

from cellar.application.sar_analysis.compute_umap_cluster import (
    ComputeUmapCluster,
    ComputeUmapClusterInput,
)
from cellar.application.sar_analysis.repositories import UmapJobRepository
from cellar.application.shared.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


@dataclass
class RunUmapCluster:
    """Callable runner that drives the full UMAP pipeline for one job.

    Dependencies are injected as dataclass fields so both the Temporal
    activity and the NullUmapClusterOrchestrator can wire them independently.

    Usage::

        runner = RunUmapCluster(compute=..., repository=..., uow=...)
        await runner.execute(
            job_id=job.id,
            workspace_id=job.workspace_id,
            molecule_ids=[...],
            picker="maxmin",
            picker_params={"n": 50},
        )
    """

    compute: ComputeUmapCluster
    repository: UmapJobRepository
    uow: UnitOfWork

    async def execute(
        self,
        *,
        job_id: UUID,
        workspace_id: UUID,
        molecule_ids: list[UUID],
        picker: str,
        picker_params: dict[str, Any],
    ) -> None:
        """Execute the UMAP pipeline for *job_id*.

        1. Load the job from the repository.
        2. Advance the state machine: PENDING → RUNNING.
        3. Run ComputeUmapCluster.
        4. Advance the state machine: RUNNING → READY (result attached).
        5. On any exception: advance to FAILED and re-raise so Temporal retries.
        """
        log = logger.bind(job_id=str(job_id), workspace_id=str(workspace_id))
        running = None
        try:
            async with self.uow:
                job = await self.repository.find_by_id(
                    job_id, workspace_id=workspace_id
                )
                if job is None:
                    log.error("umap_cluster_job_not_found")
                    return
                running = job.mark_running(datetime.now(timezone.utc))
                await self.repository.save(running)
                await self.uow.commit()

            result = await self.compute.execute(
                ComputeUmapClusterInput(
                    molecule_ids=molecule_ids,
                    picker=picker,
                    picker_params=picker_params,
                )
            )

            async with self.uow:
                ready = running.mark_ready(result, datetime.now(timezone.utc))
                await self.repository.save(ready)
                await self.uow.commit()
            log.info(
                "umap_cluster_job_ready",
                point_count=len(result.points),
                cluster_count=result.cluster_count,
            )

        except Exception as exc:
            log.exception("umap_cluster_job_failed")
            try:
                async with self.uow:
                    current = await self.repository.find_by_id(
                        job_id, workspace_id=workspace_id
                    )
                    if current is not None:
                        failed = current.mark_failed(str(exc), datetime.now(timezone.utc))
                        await self.repository.save(failed)
                        await self.uow.commit()
            except Exception:
                log.exception("umap_cluster_fail_mark_failed")
            raise
