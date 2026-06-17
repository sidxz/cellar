"""Orchestrator implementations for the R-group decomposition workflow.

``TemporalRGroupDecompositionOrchestrator`` submits the workflow and cancels via
handle. ``NullRGroupDecompositionOrchestrator`` runs RunDecomposition inline as a
fire-and-forget asyncio task (dev / tests) via the shared ``NullJobOrchestrator``.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from temporalio.client import Client

from cellar.application.sar_analysis.run_decomposition import RunDecomposition
from cellar.application.shared.mark_job_failed import MarkJobFailed
from cellar.infrastructure.temporal.orchestrator_base import NullJobOrchestrator
from cellar.infrastructure.temporal.task_queues import MAIN_TASK_QUEUE
from cellar.infrastructure.temporal.workflows.rgroup_decomposition import (
    RGroupDecompositionWorkflow,
    RGroupDecompositionWorkflowInput,
)


class RGroupDecompositionRunner(Protocol):
    async def run(
        self,
        *,
        run_id: UUID,
        workspace_id: UUID,
        core_smiles: str,
        collection_id: UUID | None = None,
        molecule_ids: list[UUID] | None = None,
    ) -> None: ...


class TemporalRGroupDecompositionOrchestrator:
    def __init__(self, client: Client) -> None:
        self._client = client

    async def schedule(
        self,
        *,
        run_id: UUID,
        workspace_id: UUID,
        core_smiles: str,
        collection_id: UUID | None = None,
        molecule_ids: list[UUID] | None = None,
    ) -> None:
        await self._client.start_workflow(
            RGroupDecompositionWorkflow.run,
            RGroupDecompositionWorkflowInput(
                run_id=str(run_id),
                workspace_id=str(workspace_id),
                core_smiles=core_smiles,
                collection_id=str(collection_id) if collection_id is not None else None,
                molecule_ids=[str(m) for m in (molecule_ids or [])],
            ),
            id=f"rgroup-decomposition-{run_id}",
            task_queue=MAIN_TASK_QUEUE,
        )

    async def cancel(self, *, run_id: UUID) -> None:
        handle = self._client.get_workflow_handle(f"rgroup-decomposition-{run_id}")
        await handle.cancel()


class NullRGroupDecompositionOrchestrator(NullJobOrchestrator):
    """In-process fallback when Temporal is unavailable."""

    def __init__(
        self,
        runner: RGroupDecompositionRunner | RunDecomposition,
        *,
        mark_failed: MarkJobFailed | None = None,
    ) -> None:
        super().__init__(mark_failed=mark_failed, job_type="rgroup_decomposition")
        self._runner = runner

    async def schedule(
        self,
        *,
        run_id: UUID,
        workspace_id: UUID,
        core_smiles: str,
        collection_id: UUID | None = None,
        molecule_ids: list[UUID] | None = None,
    ) -> None:
        self._spawn(
            lambda: self._runner.run(
                run_id=run_id,
                workspace_id=workspace_id,
                core_smiles=core_smiles,
                collection_id=collection_id,
                molecule_ids=molecule_ids,
            ),
            job_id=run_id,
            workspace_id=workspace_id,
        )

    async def cancel(self, *, run_id: UUID) -> None:
        return None  # inline tasks cannot be cancelled by run id
