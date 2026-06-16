"""MarkJobFailed — the single, guarded, idempotent FAILED-marker for every
async compute job.

Runners deliberately re-raise instead of marking FAILED (so a Temporal retry
can re-enter and recover), so FAILED is set here — invoked by the Temporal
workflow after retries, the Null orchestrator's inline task, and the inline
Start path. Idempotent: a job already terminal (a cancel won the race, or it
succeeded) is left untouched, and a concurrent transition that advances the row
between our read and save is swallowed.

``job_type`` is a stable string identifying the kind of job; the conflict log
uses a fixed event name (``async_job_mark_failed_conflict``) with ``job_type`` as
a structured field, matching the codebase's string-literal event-name convention.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog

from cellar.application.shared.job_repository import JobRepository
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.async_job import InvalidJobTransition
from cellar.domain.shared.errors import ConcurrencyConflictError

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class MarkJobFailedInput:
    job_id: UUID
    workspace_id: UUID
    error: str
    now: datetime


class MarkJobFailed:
    def __init__(self, *, repository: JobRepository, uow: UnitOfWork, job_type: str) -> None:
        self._repo = repository
        self._uow = uow
        self._job_type = job_type

    async def execute(self, payload: MarkJobFailedInput) -> None:
        async with self._uow:
            job = await self._repo.find_by_id_in_workspace(payload.workspace_id, payload.job_id)
            if job is None:
                return
            try:
                job.mark_failed(payload.error, payload.now)
            except InvalidJobTransition:
                return  # already terminal — idempotent no-op
            try:
                await self._repo.save(job)
                await self._uow.commit()
            except ConcurrencyConflictError:
                # A concurrent transition (e.g. a cancel) won the race; leave
                # whatever terminal state was committed.
                logger.info(
                    "async_job_mark_failed_conflict",
                    job_type=self._job_type,
                    job_id=str(payload.job_id),
                )
