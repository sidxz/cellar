"""UmapClusterWorkflow — durable single-activity wrapper for RunUmapCluster.

One workflow per UMAP cluster job. The single ``run_umap_cluster_activity``
activity does all the heavy lifting (compute UMAP → persist result → mark READY).
The 30-minute timeout accommodates large molecule sets with expensive fingerprint
computation; most sub-500-mol builds complete in seconds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from uuid import UUID

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from cellar.infrastructure.temporal.activities.umap_cluster import (
        UmapClusterActivities,
        RunUmapClusterActivityInput,
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
        await workflow.execute_activity(
            UmapClusterActivities.run_umap_cluster,
            RunUmapClusterActivityInput(
                job_id=payload.job_id,
                workspace_id=payload.workspace_id,
                molecule_ids=payload.molecule_ids,
                picker=payload.picker,
                picker_params=payload.picker_params,
            ),
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
