"""ScaffoldTreeWorkflow — durable single-activity wrapper for RunScaffoldTree.

One workflow per scaffold-tree job. The single ``run_scaffold_tree`` activity
does all the heavy lifting (build network → persist result → mark READY). The
5-minute timeout covers large molecule sets; most sub-500-mol builds complete
in milliseconds synchronously, so only large async jobs reach this workflow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from cellar.infrastructure.temporal.activities.scaffold_tree import (
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
        await workflow.execute_activity(
            ScaffoldTreeActivities.run_scaffold_tree,
            RunScaffoldTreeInput(
                job_id=input.job_id,
                workspace_id=input.workspace_id,
                molecule_ids=input.molecule_ids,
            ),
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
