"""ScaffoldTreeWorkflow — durable single-activity wrapper for RunScaffoldTree.

One workflow per scaffold-tree job. The 5-minute timeout covers large molecule
sets; most sub-500-mol builds complete synchronously, so only large async jobs
reach this workflow. On retry exhaustion the run is marked FAILED at the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from temporalio import workflow

from cellar.infrastructure.temporal.workflow_support import run_job_with_failure_marking

with workflow.unsafe.imports_passed_through():
    from cellar.infrastructure.temporal.activities.scaffold_tree import (
        MarkScaffoldFailedInput,
        RunScaffoldTreeInput,
        ScaffoldTreeActivities,
    )


@dataclass
class ScaffoldTreeWorkflowInput:
    job_id: str
    workspace_id: str
    molecule_ids: list[str] = field(default_factory=list)


@workflow.defn
class ScaffoldTreeWorkflow:
    """Durable workflow that computes one scaffold-tree job to completion."""

    @workflow.run
    async def run(self, input: ScaffoldTreeWorkflowInput) -> None:
        await run_job_with_failure_marking(
            run_activity=ScaffoldTreeActivities.run_scaffold_tree,
            run_input=RunScaffoldTreeInput(
                job_id=input.job_id,
                workspace_id=input.workspace_id,
                molecule_ids=input.molecule_ids,
            ),
            mark_failed_activity=ScaffoldTreeActivities.mark_scaffold_tree_job_failed,
            mark_failed_input=MarkScaffoldFailedInput(
                job_id=input.job_id,
                workspace_id=input.workspace_id,
                error="scaffold tree build failed after retries",
            ),
            run_timeout=timedelta(minutes=5),
        )
