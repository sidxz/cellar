"""ScaffoldTreeActivities — Temporal activity that delegates to RunScaffoldTree.

``run_scaffold_tree`` drives the build; ``mark_scaffold_tree_job_failed`` records
FAILED at the boundary once run retries are exhausted (the runner leaves
FAILED-marking to this boundary so a retry can re-enter and recover).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from temporalio import activity

from cellar.application.sar_analysis.run_scaffold_tree import RunScaffoldTree
from cellar.application.shared.mark_job_failed import MarkJobFailed, MarkJobFailedInput


@dataclass
class RunScaffoldTreeInput:
    job_id: str
    workspace_id: str
    molecule_ids: list[str]


@dataclass
class MarkScaffoldFailedInput:
    job_id: str
    workspace_id: str
    error: str


class ScaffoldTreeActivities:
    def __init__(self, run_scaffold_tree: RunScaffoldTree, mark_failed: MarkJobFailed) -> None:
        self._run = run_scaffold_tree
        self._mark_failed = mark_failed

    @activity.defn
    async def run_scaffold_tree(self, input: RunScaffoldTreeInput) -> None:
        await self._run.run(
            job_id=uuid.UUID(input.job_id),
            workspace_id=uuid.UUID(input.workspace_id),
            molecule_ids=[uuid.UUID(mid) for mid in input.molecule_ids],
        )

    @activity.defn
    async def mark_scaffold_tree_job_failed(self, input: MarkScaffoldFailedInput) -> None:
        # Invoked by the workflow once run retries are exhausted, so the row is
        # never left orphaned in RUNNING. Guarded + idempotent in the use case.
        await self._mark_failed.execute(
            MarkJobFailedInput(
                job_id=uuid.UUID(input.job_id),
                workspace_id=uuid.UUID(input.workspace_id),
                error=input.error,
                now=datetime.now(UTC),
            )
        )
