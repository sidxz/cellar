"""UmapClusterActivities — Temporal activity that delegates to RunUmapCluster.

A single ``run_umap_cluster`` activity drives the full pipeline:
  fetch job → mark running → compute UMAP embeddings → persist READY result.

``RunUmapCluster`` is injected at worker boot time so the activity class
is just a thin adapter — all business logic lives in the application layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from temporalio import activity

from cellar.application.sar_analysis.run_umap_cluster import RunUmapCluster


@dataclass
class RunUmapClusterActivityInput:
    job_id: UUID
    workspace_id: UUID
    molecule_ids: list[UUID]
    picker: str = "maxmin"
    picker_params: dict[str, Any] = field(default_factory=dict)


class UmapClusterActivities:
    def __init__(self, run_umap_cluster: RunUmapCluster) -> None:
        self._run = run_umap_cluster

    @activity.defn
    async def run_umap_cluster(self, input: RunUmapClusterActivityInput) -> None:
        await self._run.execute(
            job_id=input.job_id,
            workspace_id=input.workspace_id,
            molecule_ids=input.molecule_ids,
            picker=input.picker,
            picker_params=input.picker_params,
        )
