"""NullJobOrchestrator — in-process fallback base for async compute jobs.

Runs the job's runner as a fire-and-forget asyncio task (dev / tests, when
Temporal is unavailable). Because there is no Temporal workflow to mark FAILED
on retry exhaustion, this base records FAILED itself when the runner raises (the
runner leaves FAILED-marking to the boundary). ``mark_failed`` is optional so
tests can construct a subclass without it.

Subclasses implement the job-specific ``schedule(...)``/``cancel(...)`` and call
``_spawn`` with a zero-arg coroutine factory that invokes their runner.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

import structlog

from cellar.application.shared.mark_job_failed import MarkJobFailed, MarkJobFailedInput

logger = structlog.get_logger(__name__)


class NullJobOrchestrator:
    def __init__(self, *, mark_failed: MarkJobFailed | None, job_type: str) -> None:
        self._mark_failed = mark_failed
        self._job_type = job_type
        self._tasks: set[asyncio.Task] = set()

    def _spawn(
        self,
        run: Callable[[], Awaitable[None]],
        *,
        job_id: UUID,
        workspace_id: UUID,
    ) -> None:
        task = asyncio.create_task(
            self._run_and_record(run, job_id=job_id, workspace_id=workspace_id)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run_and_record(
        self,
        run: Callable[[], Awaitable[None]],
        *,
        job_id: UUID,
        workspace_id: UUID,
    ) -> None:
        try:
            await run()
        except Exception:
            # The runner already logged + re-raised; record FAILED here (no
            # Temporal workflow exists on the inline path to do it). Swallow
            # after — this is a fire-and-forget background task.
            if self._mark_failed is not None:
                await self._mark_failed.execute(
                    MarkJobFailedInput(
                        job_id=job_id,
                        workspace_id=workspace_id,
                        error=f"{self._job_type} failed",
                        now=datetime.now(UTC),
                    )
                )
            else:
                logger.warning(
                    "async_job_inline_failed_unrecorded",
                    job_type=self._job_type,
                    job_id=str(job_id),
                )
