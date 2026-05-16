"""Orchestrator implementations for the export workflow.

``TemporalExportOrchestrator`` — submits ``ExportWorkflow`` to the Temporal
cluster and implements ``request_cancel`` via workflow handle.

``NullExportOrchestrator`` — in-process fallback for dev/test environments
where a Temporal worker is not running. Runs ``RenderExport`` as an
``asyncio.Task`` so the route handler returns immediately (job_id) while
the export proceeds in the background. The FE polls ``GET /exports/{id}``
for status.
"""

from __future__ import annotations

import asyncio

from temporalio.client import Client

from cellar.application.export.orchestration import (
    ExportOrchestrator,  # noqa: F401 — imported for isinstance checks in tests
    StartExportWorkflowRequest,
    WorkflowOrchestratorUnavailable,  # noqa: F401 — re-exported for callers
)
from cellar.application.export.render_export import RenderExport
from cellar.infrastructure.temporal.task_queues import MAIN_TASK_QUEUE
from cellar.infrastructure.temporal.workflows.export import (
    ExportWorkflow,
    ExportWorkflowInput,
)


class TemporalExportOrchestrator:
    """Implements ``ExportOrchestrator`` against a live Temporal cluster."""

    def __init__(self, client: Client) -> None:
        self._client = client

    async def start(self, request: StartExportWorkflowRequest) -> str:
        wf_id = f"export-{request.job_id}"
        await self._client.start_workflow(
            ExportWorkflow.run,
            ExportWorkflowInput(
                job_id=str(request.job_id),
                workspace_id=str(request.workspace_id),
            ),
            id=wf_id,
            task_queue=MAIN_TASK_QUEUE,
        )
        return wf_id

    async def request_cancel(self, workflow_id: str) -> None:
        handle = self._client.get_workflow_handle(workflow_id)
        await handle.cancel()


class NullExportOrchestrator:
    """In-process fallback when Temporal is unavailable.

    Runs ``RenderExport`` as a fire-and-forget ``asyncio.Task``.  The route
    returns the job_id immediately; the FE polls ``GET /exports/{id}`` for
    progress.  Errors are written to the job record by ``RenderExport``
    itself, so they surface on the next status poll.

    Suitable for local dev and unit tests where the Temporal worker is not
    running.
    """

    def __init__(self, render_export: RenderExport) -> None:
        self._run = render_export

    async def start(self, request: StartExportWorkflowRequest) -> str:
        asyncio.create_task(self._run(request.job_id, request.workspace_id))
        return f"inline-{request.job_id}"

    async def request_cancel(self, workflow_id: str) -> None:
        # No-op — inline tasks cannot be cancelled by workflow id.
        return None
