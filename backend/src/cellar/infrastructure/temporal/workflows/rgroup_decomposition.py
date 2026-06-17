"""RGroupDecompositionWorkflow — durable single-activity wrapper for RunDecomposition.

One workflow per decomposition run. The 1-hour timeout is generous because the
activity streams the (re-expanded) collection and decomposes it; timeout + retry
are baked into history at schedule time, so changing them later does not affect
in-flight workflows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from temporalio import workflow

from cellar.infrastructure.temporal.workflow_support import run_job_with_failure_marking

with workflow.unsafe.imports_passed_through():
    from cellar.infrastructure.temporal.activities.rgroup_decomposition import (
        MarkRunFailedInput,
        RGroupDecompositionActivities,
        RunDecompositionInput,
    )


@dataclass
class RGroupDecompositionWorkflowInput:
    run_id: str
    workspace_id: str
    core_smiles: str
    collection_id: str | None = None
    molecule_ids: list[str] = field(default_factory=list)


@workflow.defn
class RGroupDecompositionWorkflow:
    @workflow.run
    async def run(self, input: RGroupDecompositionWorkflowInput) -> None:
        await run_job_with_failure_marking(
            run_activity=RGroupDecompositionActivities.run_rgroup_decomposition,
            run_input=RunDecompositionInput(
                run_id=input.run_id,
                workspace_id=input.workspace_id,
                core_smiles=input.core_smiles,
                collection_id=input.collection_id,
                molecule_ids=input.molecule_ids,
            ),
            mark_failed_activity=RGroupDecompositionActivities.mark_rgroup_decomposition_failed,
            mark_failed_input=MarkRunFailedInput(
                run_id=input.run_id,
                workspace_id=input.workspace_id,
                error="decomposition failed after retries",
            ),
            run_timeout=timedelta(hours=1),
        )
