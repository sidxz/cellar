"""RunUmapCluster — in-process runner: claim -> compute UMAP -> finalize.

The Temporal activity wraps this; the Null orchestrator invokes it inline. The
lifecycle scaffolding (claim, re-read-before-finalize) is the shared
``claim_job`` / ``finalize_if_still_running``; the compute stays explicit. The
result is header-only (no child rows), so there is no reset step. The runner
never marks FAILED — it re-raises so a retry can re-enter; FAILED is recorded at
the orchestration boundary (``MarkJobFailed``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

from cellar.application.sar_analysis.compute_umap_cluster import (
    ComputeUmapCluster,
    ComputeUmapClusterInput,
)
from cellar.application.sar_analysis.repositories import UmapJobRepository
from cellar.application.shared.async_job_runner import claim_job, finalize_if_still_running
from cellar.application.shared.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

_JOB_TYPE = "umap_cluster"


@dataclass
class RunUmapCluster:
    """Callable runner that drives the full UMAP pipeline for one job."""

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
        log = logger.bind(job_id=str(job_id), workspace_id=str(workspace_id))
        try:
            if not await claim_job(
                self.repository,
                self.uow,
                job_id=job_id,
                workspace_id=workspace_id,
                now=datetime.now(UTC),
                job_type=_JOB_TYPE,
            ):
                return

            result = await self.compute.execute(
                ComputeUmapClusterInput(
                    molecule_ids=molecule_ids,
                    picker=picker,
                    picker_params=picker_params,
                )
            )

            async with self.uow:
                await finalize_if_still_running(
                    self.repository,
                    self.uow,
                    job_id=job_id,
                    workspace_id=workspace_id,
                    apply_ready=lambda job: job.mark_ready(result=result, now=datetime.now(UTC)),
                    job_type=_JOB_TYPE,
                )
            log.info(
                "umap_cluster_job_ready",
                point_count=len(result.points),
                cluster_count=result.cluster_count,
            )

        except Exception:
            # FAILED is marked at the orchestration boundary (Temporal workflow on
            # retry exhaustion, or the Null orchestrator), not here — so a retry
            # can re-enter and recover. Re-raise for the boundary.
            log.exception("umap_cluster_job_failed")
            raise
