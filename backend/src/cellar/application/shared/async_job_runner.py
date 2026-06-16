"""Shared async-job runner helpers.

The two functions here are the lifecycle scaffolding every compute-job runner
needs — the bits that previously diverged into bugs when hand-copied:

- ``claim_job`` — idempotent claim (PENDING -> RUNNING, re-claim a crashed
  RUNNING attempt, no-op on terminal/missing). Owns its own transaction.
- ``finalize_if_still_running`` — re-read inside the *active* transaction and
  finalize only if the job is still RUNNING, so a concurrent cancel is honored
  (the version-checked ``save`` is the TOCTOU backstop).

Runners stay plain ``@dataclass`` objects and call these; the compute itself
stays explicit in each runner. A runner must NEVER mark FAILED — it re-raises
so a retry can re-enter; FAILED is owned by ``MarkJobFailed`` at the boundary.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

import structlog

from cellar.application.shared.job_repository import JobRepository, JobT
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.async_job import AsyncJobStatus

logger = structlog.get_logger(__name__)


async def claim_job(
    repository: JobRepository[JobT],
    uow: UnitOfWork,
    *,
    job_id: UUID,
    workspace_id: UUID,
    now: datetime,
    job_type: str,
) -> bool:
    """Claim a job for execution. Returns True if the caller should proceed.

    PENDING -> RUNNING (persisted + committed) -> True.
    RUNNING -> True (re-claim a crashed/retried attempt; no write).
    missing or terminal -> False.
    """
    async with uow:
        job = await repository.find_by_id_in_workspace(workspace_id, job_id)
        if job is None:
            logger.error("async_job_not_found", job_type=job_type, job_id=str(job_id))
            return False
        if job.status == AsyncJobStatus.PENDING:
            job.mark_running(now)
            await repository.save(job)
            await uow.commit()
            return True
        if job.status == AsyncJobStatus.RUNNING:
            return True
        logger.info(
            "async_job_not_runnable",
            job_type=job_type,
            job_id=str(job_id),
            status=str(job.status),
        )
        return False


async def finalize_if_still_running(
    repository: JobRepository[JobT],
    uow: UnitOfWork,
    *,
    job_id: UUID,
    workspace_id: UUID,
    apply_ready: Callable[[JobT], None],
    job_type: str,
) -> None:
    """Re-read inside the active UoW and finalize only if still RUNNING.

    MUST be called inside the caller's ``async with uow:`` block so the READY
    mark commits atomically with the result rows written in that block. Honors
    a concurrent cancel (re-read sees a non-RUNNING status) and relies on the
    version-checked ``save`` as the TOCTOU backstop.

    ``job_type`` is a stable string identifying the kind of job (e.g.
    ``"fingerprint_run"``). A fixed event name (``async_job_no_longer_running``)
    keeps log cardinality low and aggregatable; the job's identity is carried in
    this structured ``job_type`` field — matching the codebase's string-literal
    event-name convention.
    """
    current = await repository.find_by_id_in_workspace(workspace_id, job_id)
    if current is None or current.status != AsyncJobStatus.RUNNING:
        logger.info(
            "async_job_no_longer_running",
            job_type=job_type,
            job_id=str(job_id),
            status=str(current.status) if current is not None else "missing",
        )
        return
    apply_ready(current)
    await repository.save(current)
    await uow.commit()
