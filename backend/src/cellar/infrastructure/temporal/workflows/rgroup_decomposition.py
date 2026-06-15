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
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from cellar.infrastructure.temporal.activities.rgroup_decomposition import (
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
        await workflow.execute_activity(
            RGroupDecompositionActivities.run_rgroup_decomposition,
            RunDecompositionInput(
                run_id=input.run_id,
                workspace_id=input.workspace_id,
                core_smiles=input.core_smiles,
                collection_id=input.collection_id,
                molecule_ids=input.molecule_ids,
            ),
            start_to_close_timeout=timedelta(hours=1),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
