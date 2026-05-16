"""ExportWorkflow — durable single-activity wrapper for RenderExport.

One workflow per export job. The single ``run_export`` activity does all the
heavy lifting (stream → render → upload → mark READY). The 30-minute timeout
covers large PDF/XLSX exports with sparkline generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from cellar.infrastructure.temporal.activities.export import (
        ExportActivities,
        RunExportInput,
    )


@dataclass
class ExportWorkflowInput:
    job_id: str
    workspace_id: str


@workflow.defn
class ExportWorkflow:
    """Durable workflow that renders one export job to completion."""

    @workflow.run
    async def run(self, input: ExportWorkflowInput) -> None:
        await workflow.execute_activity(
            ExportActivities.run_export,
            RunExportInput(job_id=input.job_id, workspace_id=input.workspace_id),
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
