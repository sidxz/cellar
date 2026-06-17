"""Workflow-safe helpers shared across single-activity job workflows.

Imported at the top of ``@workflow.defn`` modules, so this module must stay
inside the Temporal determinism sandbox: temporalio + stdlib only, no asyncio
primitives, no application/infrastructure imports.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError


async def run_job_with_failure_marking(
    *,
    run_activity: Any,
    run_input: Any,
    mark_failed_activity: Any,
    mark_failed_input: Any,
    run_timeout: timedelta,
    run_retries: int = 3,
    mark_failed_timeout: timedelta = timedelta(minutes=5),
    mark_failed_retries: int = 5,
) -> None:
    """Run the job activity under a retry policy; on retry exhaustion, mark the
    job FAILED via the mark-failed activity, then re-raise to fail the workflow.

    This is the boundary that records FAILED — the runner deliberately re-raises
    so a retry can re-enter and recover; only when retries are exhausted is the
    row marked FAILED so it is never orphaned in RUNNING.
    """
    try:
        await workflow.execute_activity(
            run_activity,
            run_input,
            start_to_close_timeout=run_timeout,
            retry_policy=RetryPolicy(maximum_attempts=run_retries),
        )
    except ActivityError:
        await workflow.execute_activity(
            mark_failed_activity,
            mark_failed_input,
            start_to_close_timeout=mark_failed_timeout,
            retry_policy=RetryPolicy(maximum_attempts=mark_failed_retries),
        )
        raise
