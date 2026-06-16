"""Orchestrator implementations for the SAR activity-projection workflow.

``TemporalSarActivityProjectionOrchestrator`` submits the workflow and cancels via
handle. ``NullSarActivityProjectionOrchestrator`` runs RunActivityProjection inline
as a fire-and-forget asyncio task (dev / tests). Mirrors rgroup_decomposition exactly.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

import structlog
from temporalio.client import Client

from cellar.application.sar_analysis.mark_activity_projection_failed import (
    MarkActivityProjectionFailed,
    MarkActivityProjectionFailedInput,
)
from cellar.application.sar_analysis.run_activity_projection import RunActivityProjection
from cellar.infrastructure.temporal.task_queues import MAIN_TASK_QUEUE
from cellar.infrastructure.temporal.workflows.sar_activity_projection import (
    SarActivityProjectionWorkflow,
    SarActivityProjectionWorkflowInput,
)

logger = structlog.get_logger(__name__)


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


class NullSarActivityProjectionOrchestrator:
    """In-process fallback when Temporal is unavailable.

    Runs the projection as a fire-and-forget asyncio task. Because there is no
    Temporal workflow to mark FAILED on retry exhaustion, this orchestrator marks
    FAILED itself when the runner raises (the runner deliberately leaves that to
    the boundary). ``mark_failed`` is optional so tests can construct the
    orchestrator without it.
    """

    def __init__(
        self,
        runner: SarActivityProjectionRunner | RunActivityProjection,
        *,
        mark_failed: MarkActivityProjectionFailed | None = None,
    ) -> None:
        self._runner = runner
        self._mark_failed = mark_failed
        self._tasks: set[asyncio.Task] = set()

    async def schedule(
        self,
        *,
        projection_id: UUID,
        workspace_id: UUID,
        channel_spec: dict[str, Any],
        collection_id: UUID | None = None,
        molecule_ids: list[UUID] | None = None,
    ) -> None:
        task = asyncio.create_task(
            self._run_and_record(
                projection_id=projection_id,
                workspace_id=workspace_id,
                channel_spec=channel_spec,
                collection_id=collection_id,
                molecule_ids=molecule_ids,
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run_and_record(
        self,
        *,
        projection_id: UUID,
        workspace_id: UUID,
        channel_spec: dict[str, Any],
        collection_id: UUID | None,
        molecule_ids: list[UUID] | None,
    ) -> None:
        try:
            await self._runner.run(
                run_id=projection_id,
                workspace_id=workspace_id,
                channel_spec=channel_spec,
                collection_id=collection_id,
                molecule_ids=molecule_ids,
            )
        except Exception:
            # The runner already logged + re-raised; record FAILED here (no
            # Temporal workflow exists on the inline path to do it). Swallow
            # after — this is a fire-and-forget background task.
            if self._mark_failed is not None:
                await self._mark_failed.execute(
                    MarkActivityProjectionFailedInput(
                        projection_id=projection_id,
                        workspace_id=workspace_id,
                        error="activity projection failed",
                        now=datetime.now(UTC),
                    )
                )
            else:
                logger.warning(
                    "sar_activity_projection_inline_failed_unrecorded",
                    projection_id=str(projection_id),
                )

    async def cancel(self, *, projection_id: UUID) -> None:
        return None  # inline tasks cannot be cancelled by id
