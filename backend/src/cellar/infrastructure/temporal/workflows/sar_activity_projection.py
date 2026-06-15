"""SarActivityProjectionWorkflow — durable single-activity wrapper for
RunActivityProjection. The 1-hour timeout is generous because the activity
re-expands the membership and enriches it. Timeout + retry are baked into history
at schedule time (changing them later does not affect in-flight workflows)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from cellar.infrastructure.temporal.activities.sar_activity_projection import (
        RunActivityProjectionInput,
        SarActivityProjectionActivities,
    )


@dataclass
class SarActivityProjectionWorkflowInput:
    projection_id: str
    workspace_id: str
    channel_spec: dict[str, Any]
    collection_id: str | None = None
    molecule_ids: list[str] = field(default_factory=list)


@workflow.defn
class SarActivityProjectionWorkflow:
    @workflow.run
    async def run(self, input: SarActivityProjectionWorkflowInput) -> None:
        await workflow.execute_activity(
            SarActivityProjectionActivities.run_sar_activity_projection,
            RunActivityProjectionInput(
                projection_id=input.projection_id,
                workspace_id=input.workspace_id,
                channel_spec=input.channel_spec,
                collection_id=input.collection_id,
                molecule_ids=input.molecule_ids,
            ),
            start_to_close_timeout=timedelta(hours=1),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
