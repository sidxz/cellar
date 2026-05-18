"""UmapClusterOrchestrator implementations.

``NullUmapClusterOrchestrator`` — in-process fallback for dev/test environments
where a Temporal worker is not running. Runs the runner inline (awaits directly)
so the caller gets synchronous completion feedback. Suitable for unit tests and
``TEMPORAL_DISABLED=1`` single-process environments.

``TemporalUmapClusterOrchestrator`` — submits ``UmapClusterWorkflow`` to the
Temporal cluster and implements ``cancel`` via workflow handle.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable
from uuid import UUID

from temporalio.client import Client

from cellar.infrastructure.temporal.task_queues import MAIN_TASK_QUEUE
from cellar.infrastructure.temporal.workflows.umap_cluster import (
    UmapClusterWorkflow,
    UmapClusterWorkflowInput,
)

RunnerFn = Callable[..., Awaitable[None]]


class NullUmapClusterOrchestrator:
    """Runs the runner inline (no Temporal). For tests + TEMPORAL_DISABLED=1."""

    def __init__(self, *, runner: RunnerFn) -> None:
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
        await self._runner(
            job_id=job_id,
            workspace_id=workspace_id,
            molecule_ids=molecule_ids,
            picker=picker,
            picker_params=picker_params,
        )

    async def cancel(self, *, job_id: UUID) -> None:  # pragma: no cover
        # Cancellation is best-effort; the runner has no signal channel in the inline path.
        return


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
