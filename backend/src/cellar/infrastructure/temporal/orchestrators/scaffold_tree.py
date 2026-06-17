"""Orchestrator implementations for the scaffold-tree workflow.

``TemporalScaffoldTreeOrchestrator`` submits ``ScaffoldTreeWorkflow`` and cancels
via workflow handle. ``NullScaffoldTreeOrchestrator`` runs ``RunScaffoldTree``
inline as a fire-and-forget asyncio task (dev / tests) via the shared
``NullJobOrchestrator``, which records FAILED at the boundary when the runner
raises (the runner leaves FAILED-marking to the boundary).
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from temporalio.client import Client

from cellar.application.sar_analysis.run_scaffold_tree import RunScaffoldTree
from cellar.application.shared.mark_job_failed import MarkJobFailed
from cellar.infrastructure.temporal.orchestrator_base import NullJobOrchestrator
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
        await self._client.start_workflow(
            ScaffoldTreeWorkflow.run,
            ScaffoldTreeWorkflowInput(
                job_id=str(job_id),
                workspace_id=str(workspace_id),
                molecule_ids=[str(mid) for mid in molecule_ids],
            ),
            id=f"scaffold-tree-{job_id}",
            task_queue=MAIN_TASK_QUEUE,
        )

    async def cancel(self, *, job_id: UUID) -> None:
        handle = self._client.get_workflow_handle(f"scaffold-tree-{job_id}")
        await handle.cancel()


class NullScaffoldTreeOrchestrator(NullJobOrchestrator):
    """In-process fallback when Temporal is unavailable."""

    def __init__(
        self,
        runner: ScaffoldTreeRunner | RunScaffoldTree,
        *,
        mark_failed: MarkJobFailed | None = None,
    ) -> None:
        super().__init__(mark_failed=mark_failed, job_type="scaffold_tree")
        self._runner = runner

    async def schedule(
        self, *, job_id: UUID, workspace_id: UUID, molecule_ids: list[UUID]
    ) -> None:
        self._spawn(
            lambda: self._runner.run(
                job_id=job_id, workspace_id=workspace_id, molecule_ids=molecule_ids
            ),
            job_id=job_id,
            workspace_id=workspace_id,
        )

    async def cancel(self, *, job_id: UUID) -> None:
        return None  # inline tasks cannot be cancelled by job id
