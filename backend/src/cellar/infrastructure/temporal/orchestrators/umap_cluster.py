"""UmapClusterOrchestrator implementations.

``NullUmapClusterOrchestrator`` — in-process fallback for dev/test environments
where a Temporal worker is not running. Runs the runner as a fire-and-forget
asyncio task via the shared ``NullJobOrchestrator``, which records FAILED at the
boundary when the runner raises (the runner leaves FAILED-marking to the boundary).

``TemporalUmapClusterOrchestrator`` — submits ``UmapClusterWorkflow`` to the
Temporal cluster and implements ``cancel`` via workflow handle.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from temporalio.client import Client

from cellar.application.shared.mark_job_failed import MarkJobFailed
from cellar.infrastructure.temporal.orchestrator_base import NullJobOrchestrator
from cellar.infrastructure.temporal.task_queues import MAIN_TASK_QUEUE
from cellar.infrastructure.temporal.workflows.umap_cluster import (
    UmapClusterWorkflow,
    UmapClusterWorkflowInput,
)

RunnerFn = Callable[..., Awaitable[None]]


class NullUmapClusterOrchestrator(NullJobOrchestrator):
    """Runs the runner inline as a fire-and-forget task. For tests + TEMPORAL_DISABLED=1."""

    def __init__(self, *, runner: RunnerFn, mark_failed: MarkJobFailed | None = None) -> None:
        super().__init__(mark_failed=mark_failed, job_type="umap_cluster")
        self._runner = runner

    async def schedule(
        self,
        *,
        job_id: UUID,
        workspace_id: UUID,
        molecule_ids: list[UUID],
        picker: str,
        picker_params: dict[str, Any],
    ) -> None:
        self._spawn(
            lambda: self._runner(
                job_id=job_id,
                workspace_id=workspace_id,
                molecule_ids=molecule_ids,
                picker=picker,
                picker_params=picker_params,
            ),
            job_id=job_id,
            workspace_id=workspace_id,
        )

    async def cancel(self, *, job_id: UUID) -> None:
        return None  # inline tasks cannot be cancelled by job id


class TemporalUmapClusterOrchestrator:
    """Implements the UmapCluster orchestrator against a live Temporal cluster."""

    def __init__(self, *, client: Client, task_queue: str = MAIN_TASK_QUEUE) -> None:
        self._client = client
        self._task_queue = task_queue

    async def schedule(
        self,
        *,
        job_id: UUID,
        workspace_id: UUID,
        molecule_ids: list[UUID],
        picker: str,
        picker_params: dict[str, Any],
    ) -> None:
        await self._client.start_workflow(
            UmapClusterWorkflow.run,
            UmapClusterWorkflowInput(
                job_id=job_id,
                workspace_id=workspace_id,
                molecule_ids=molecule_ids,
                picker=picker,
                picker_params=picker_params,
            ),
            id=f"umap-cluster-{job_id}",
            task_queue=self._task_queue,
        )

    async def cancel(self, *, job_id: UUID) -> None:
        handle = self._client.get_workflow_handle(f"umap-cluster-{job_id}")
        await handle.cancel()
