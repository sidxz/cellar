"""UmapClusterWorkflow — durable single-activity wrapper for RunUmapCluster.

One workflow per UMAP cluster job. The 30-minute timeout accommodates large
molecule sets with expensive fingerprint computation; most sub-500-mol builds
complete in seconds. On retry exhaustion the run is marked FAILED at the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from uuid import UUID

from temporalio import workflow

from cellar.infrastructure.temporal.workflow_support import run_job_with_failure_marking

with workflow.unsafe.imports_passed_through():
    from cellar.infrastructure.temporal.activities.umap_cluster import (
        MarkUmapFailedInput,
        RunUmapClusterActivityInput,
        UmapClusterActivities,
    )


@dataclass
class UmapClusterWorkflowInput:
    job_id: UUID
    workspace_id: UUID
    molecule_ids: list[UUID] = field(default_factory=list)
    picker: str = "maxmin"
    picker_params: dict[str, Any] = field(default_factory=dict)


@workflow.defn(name="UmapClusterWorkflow")
class UmapClusterWorkflow:
    """Durable workflow that computes one UMAP cluster job to completion."""

    @workflow.run
    async def run(self, payload: UmapClusterWorkflowInput) -> None:
        await run_job_with_failure_marking(
            run_activity=UmapClusterActivities.run_umap_cluster,
            run_input=RunUmapClusterActivityInput(
                job_id=payload.job_id,
                workspace_id=payload.workspace_id,
                molecule_ids=payload.molecule_ids,
                picker=payload.picker,
                picker_params=payload.picker_params,
            ),
            mark_failed_activity=UmapClusterActivities.mark_umap_cluster_job_failed,
            mark_failed_input=MarkUmapFailedInput(
                job_id=payload.job_id,
                workspace_id=payload.workspace_id,
                error="umap cluster build failed after retries",
            ),
            run_timeout=timedelta(minutes=30),
        )
