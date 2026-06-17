"""Orchestrator implementations for the SAR activity-projection workflow.

``TemporalSarActivityProjectionOrchestrator`` submits the workflow and cancels via
handle. ``NullSarActivityProjectionOrchestrator`` runs RunActivityProjection inline
as a fire-and-forget asyncio task (dev / tests) via the shared ``NullJobOrchestrator``.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from temporalio.client import Client

from cellar.application.sar_analysis.run_activity_projection import RunActivityProjection
from cellar.application.shared.mark_job_failed import MarkJobFailed
from cellar.infrastructure.temporal.orchestrator_base import NullJobOrchestrator
from cellar.infrastructure.temporal.task_queues import MAIN_TASK_QUEUE
from cellar.infrastructure.temporal.workflows.sar_activity_projection import (
    SarActivityProjectionWorkflow,
    SarActivityProjectionWorkflowInput,
)


class SarActivityProjectionRunner(Protocol):
    async def run(
        self,
        *,
        run_id: UUID,
        workspace_id: UUID,
        channel_spec: dict[str, Any],
        collection_id: UUID | None = None,
        molecule_ids: list[UUID] | None = None,
    ) -> None: ...


class TemporalSarActivityProjectionOrchestrator:
    def __init__(self, client: Client) -> None:
        self._client = client

    async def schedule(
        self,
        *,
        projection_id: UUID,
        workspace_id: UUID,
        channel_spec: dict[str, Any],
        collection_id: UUID | None = None,
        molecule_ids: list[UUID] | None = None,
    ) -> None:
        await self._client.start_workflow(
            SarActivityProjectionWorkflow.run,
            SarActivityProjectionWorkflowInput(
                projection_id=str(projection_id),
                workspace_id=str(workspace_id),
                channel_spec=channel_spec,
                collection_id=str(collection_id) if collection_id is not None else None,
                molecule_ids=[str(m) for m in (molecule_ids or [])],
            ),
            id=f"sar-activity-projection-{projection_id}",
            task_queue=MAIN_TASK_QUEUE,
        )

    async def cancel(self, *, projection_id: UUID) -> None:
        handle = self._client.get_workflow_handle(f"sar-activity-projection-{projection_id}")
        await handle.cancel()


class NullSarActivityProjectionOrchestrator(NullJobOrchestrator):
    """In-process fallback when Temporal is unavailable."""

    def __init__(
        self,
        runner: SarActivityProjectionRunner | RunActivityProjection,
        *,
        mark_failed: MarkJobFailed | None = None,
    ) -> None:
        super().__init__(mark_failed=mark_failed, job_type="sar_activity_projection")
        self._runner = runner

    async def schedule(
        self,
        *,
        projection_id: UUID,
        workspace_id: UUID,
        channel_spec: dict[str, Any],
        collection_id: UUID | None = None,
        molecule_ids: list[UUID] | None = None,
    ) -> None:
        self._spawn(
            lambda: self._runner.run(
                run_id=projection_id,
                workspace_id=workspace_id,
                channel_spec=channel_spec,
                collection_id=collection_id,
                molecule_ids=molecule_ids,
            ),
            job_id=projection_id,
            workspace_id=workspace_id,
        )

    async def cancel(self, *, projection_id: UUID) -> None:
        return None  # inline tasks cannot be cancelled by id
