"""Orchestrator implementations for the scaffold-tree workflow.

``TemporalScaffoldTreeOrchestrator`` — submits ``ScaffoldTreeWorkflow`` to
the Temporal cluster and implements ``cancel`` via workflow handle.

``NullScaffoldTreeOrchestrator`` — in-process fallback for dev/test
environments where a Temporal worker is not running. Runs ``RunScaffoldTree``
as a fire-and-forget ``asyncio.Task`` so the route handler returns immediately
(job_id) while the build proceeds in the background. The FE polls
``GET /scaffold-tree/{id}`` for status.
"""

from __future__ import annotations

import asyncio
from typing import Protocol
from uuid import UUID

from temporalio.client import Client

from cellar.application.sar_analysis.run_scaffold_tree import RunScaffoldTree
from cellar.infrastructure.temporal.task_queues import MAIN_TASK_QUEUE
from cellar.infrastructure.temporal.workflows.scaffold_tree import (
    ScaffoldTreeWorkflow,
    ScaffoldTreeWorkflowInput,
)


class ScaffoldTreeRunner(Protocol):
    """Minimal interface consumed by NullScaffoldTreeOrchestrator."""

    async def run(self, *, job_id: UUID, workspace_id: UUID, molecule_ids: list[UUID]) -> None: ...


class TemporalScaffoldTreeOrchestrator:
    """Implements ``ScaffoldTreeOrchestrator`` against a live Temporal cluster."""

    def __init__(self, client: Client) -> None:
        self._client = client

    async def schedule(
        self, *, job_id: UUID, workspace_id: UUID, molecule_ids: list[UUID]
    ) -> None:
        wf_id = f"scaffold-tree-{job_id}"
        await self._client.start_workflow(
            ScaffoldTreeWorkflow.run,
            ScaffoldTreeWorkflowInput(
                job_id=str(job_id),
                workspace_id=str(workspace_id),
                molecule_ids=[str(mid) for mid in molecule_ids],
            ),
            id=wf_id,
            task_queue=MAIN_TASK_QUEUE,
        )

    async def cancel(self, *, job_id: UUID) -> None:
        handle = self._client.get_workflow_handle(f"scaffold-tree-{job_id}")
        await handle.cancel()


class NullScaffoldTreeOrchestrator:
    """In-process fallback when Temporal is unavailable.

    Runs the runner as a fire-and-forget ``asyncio.Task``. The route returns
    the job_id immediately; the FE polls ``GET /scaffold-tree/{id}`` for
    progress. Errors are written to the job record by ``RunScaffoldTree``
    itself, so they surface on the next status poll.

    Suitable for local dev and unit tests where the Temporal worker is not
    running.
    """

    def __init__(self, runner: ScaffoldTreeRunner | RunScaffoldTree) -> None:
        self._runner = runner
        # Keep strong references to in-flight tasks — asyncio only holds weak
        # refs, so a fire-and-forget task can be garbage-collected mid-build.
        self._tasks: set[asyncio.Task] = set()

    async def schedule(
        self, *, job_id: UUID, workspace_id: UUID, molecule_ids: list[UUID]
    ) -> None:
        task = asyncio.create_task(
            self._runner.run(job_id=job_id, workspace_id=workspace_id, molecule_ids=molecule_ids)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def cancel(self, *, job_id: UUID) -> None:
        # No-op — inline tasks cannot be cancelled by job id.
        return None
