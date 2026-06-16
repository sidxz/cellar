"""Orchestrator implementations for the R-group decomposition workflow.

``TemporalRGroupDecompositionOrchestrator`` submits the workflow and cancels via
handle. ``NullRGroupDecompositionOrchestrator`` runs RunDecomposition inline as a
fire-and-forget asyncio task (dev / tests). Mirrors scaffold_tree exactly.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

import structlog
from temporalio.client import Client

from cellar.application.sar_analysis.mark_decomposition_run_failed import (
    MarkDecompositionRunFailed,
    MarkDecompositionRunFailedInput,
)
from cellar.application.sar_analysis.run_decomposition import RunDecomposition
from cellar.infrastructure.temporal.task_queues import MAIN_TASK_QUEUE
from cellar.infrastructure.temporal.workflows.rgroup_decomposition import (
    RGroupDecompositionWorkflow,
    RGroupDecompositionWorkflowInput,
)

logger = structlog.get_logger(__name__)


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


class NullRGroupDecompositionOrchestrator:
    """In-process fallback when Temporal is unavailable.

    Runs the decomposition as a fire-and-forget asyncio task. Because there is no
    Temporal workflow to mark FAILED on retry exhaustion, this orchestrator marks
    FAILED itself when the runner raises (the runner deliberately leaves that to
    the boundary). ``mark_failed`` is optional so tests can construct the
    orchestrator without it.
    """

    def __init__(
        self,
        runner: RGroupDecompositionRunner | RunDecomposition,
        *,
        mark_failed: MarkDecompositionRunFailed | None = None,
    ) -> None:
        self._runner = runner
        self._mark_failed = mark_failed
        self._tasks: set[asyncio.Task] = set()

    async def schedule(
        self,
        *,
        run_id: UUID,
        workspace_id: UUID,
        core_smiles: str,
        collection_id: UUID | None = None,
        molecule_ids: list[UUID] | None = None,
    ) -> None:
        task = asyncio.create_task(
            self._run_and_record(
                run_id=run_id,
                workspace_id=workspace_id,
                core_smiles=core_smiles,
                collection_id=collection_id,
                molecule_ids=molecule_ids,
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run_and_record(
        self,
        *,
        run_id: UUID,
        workspace_id: UUID,
        core_smiles: str,
        collection_id: UUID | None,
        molecule_ids: list[UUID] | None,
    ) -> None:
        try:
            await self._runner.run(
                run_id=run_id,
                workspace_id=workspace_id,
                core_smiles=core_smiles,
                collection_id=collection_id,
                molecule_ids=molecule_ids,
            )
        except Exception:
            # The runner already logged + re-raised; record FAILED here (no
            # Temporal workflow exists on the inline path to do it). Swallow
            # after — this is a fire-and-forget background task.
            if self._mark_failed is not None:
                await self._mark_failed.execute(
                    MarkDecompositionRunFailedInput(
                        run_id=run_id,
                        workspace_id=workspace_id,
                        error="decomposition failed",
                        now=datetime.now(UTC),
                    )
                )
            else:
                logger.warning(
                    "rgroup_decomposition_inline_failed_unrecorded", run_id=str(run_id)
                )

    async def cancel(self, *, run_id: UUID) -> None:
        return None  # inline tasks cannot be cancelled by run id
