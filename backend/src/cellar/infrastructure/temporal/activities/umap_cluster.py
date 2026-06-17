"""UmapClusterActivities — Temporal activity that delegates to RunUmapCluster.

``run_umap_cluster`` drives the build; ``mark_umap_cluster_job_failed`` records
FAILED at the boundary once run retries are exhausted (the runner leaves
FAILED-marking to this boundary so a retry can re-enter and recover).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from temporalio import activity

from cellar.application.sar_analysis.run_umap_cluster import RunUmapCluster
from cellar.application.shared.mark_job_failed import MarkJobFailed, MarkJobFailedInput


@dataclass
class RunUmapClusterActivityInput:
    job_id: UUID
    workspace_id: UUID
    molecule_ids: list[UUID]
    picker: str = "maxmin"
    picker_params: dict[str, Any] = field(default_factory=dict)


@dataclass
class MarkUmapFailedInput:
    job_id: UUID
    workspace_id: UUID
    error: str


class UmapClusterActivities:
    def __init__(self, run_umap_cluster: RunUmapCluster, mark_failed: MarkJobFailed) -> None:
        self._run = run_umap_cluster
        self._mark_failed = mark_failed

    @activity.defn
    async def run_umap_cluster(self, input: RunUmapClusterActivityInput) -> None:
        await self._run.execute(
            job_id=input.job_id,
            workspace_id=input.workspace_id,
            molecule_ids=input.molecule_ids,
            picker=input.picker,
            picker_params=input.picker_params,
        )

    @activity.defn
    async def mark_umap_cluster_job_failed(self, input: MarkUmapFailedInput) -> None:
        # Invoked by the workflow once run retries are exhausted, so the row is
        # never left orphaned in RUNNING. Guarded + idempotent in the use case.
        await self._mark_failed.execute(
            MarkJobFailedInput(
                job_id=input.job_id,
                workspace_id=input.workspace_id,
                error=input.error,
                now=datetime.now(UTC),
            )
        )
