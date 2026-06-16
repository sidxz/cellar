# AsyncJob Primitives (Plan 1 of N) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the three layer-pure shared primitives for the generic async-job mechanism — the domain `AsyncJob` base, the runner lifecycle helpers, and the generic `MarkJobFailed` boundary use case — each fully unit-tested, with no job wired to them yet (so all existing tests stay green).

**Architecture:** Mutable `AsyncJob(AggregateRoot)` aggregate (codebase norm) so job repos can later reuse the existing `SQLAlchemyRepository` optimistic-concurrency `save()`. Runner lifecycle = module-level composition helpers (`claim_job`, `finalize_if_still_running`) that plain `@dataclass` runners call. FAILED is owned by one guarded, idempotent `MarkJobFailed` use case at the orchestration boundary; runners never mark FAILED. This plan delivers only the parts that are unit-testable in isolation; the two Temporal primitives (`run_job_with_failure_marking`, `NullJobOrchestrator`) land in Plan 2 alongside the real decomposition workflow that exercises them.

**Tech Stack:** Python 3.13, `structlog`, `returns` (railway), SQLAlchemy 2.0 async, pytest (`asyncio_mode = "auto"`), ruff, Import Linter (`uv run lint-imports`).

**Reference spec:** `docs/superpowers/specs/2026-06-16-generic-asyncjob-design.md`

**Run all commands from `backend/`.** This plan adds only new files (no existing file is modified), so the full suite must stay green throughout.

---

### Task 1: `AsyncJob` domain base

**Files:**
- Create: `backend/src/cellar/domain/shared/async_job.py`
- Test: `backend/tests/unit/domain/shared/test_async_job.py`

The base aggregate. Mutable `AggregateRoot` subclass holding the 9 common fields and the three shared transitions (`mark_running`/`mark_failed`/`mark_cancelled`) plus a protected `_enter_ready` that subclass `mark_ready` overrides call. Transitions mutate `self` and return `None`; they never touch `version` (the repo's `save()` owns it). String enum values match the 4 existing per-job enums, so no DB data migration.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/domain/shared/test_async_job.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.domain.shared.async_job import (
    JOB_TERMINAL_STATES,
    AsyncJob,
    AsyncJobStatus,
    InvalidJobTransition,
)

_NOW = datetime(2026, 6, 16, tzinfo=UTC)


class _FakeJob(AsyncJob):
    """Minimal concrete AsyncJob for exercising the shared base."""

    def __init__(self, *, result: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.result = result

    def mark_ready(self, *, result: str, now: datetime) -> None:
        self._enter_ready(now)
        self.result = result


def _pending() -> _FakeJob:
    return _FakeJob(
        workspace_id=uuid.uuid4(),
        requested_by=uuid.uuid4(),
        requested_at=_NOW,
    )


def test_new_job_is_pending_with_version_1():
    job = _pending()
    assert job.status == AsyncJobStatus.PENDING
    assert job.version == 1
    assert job.started_at is None and job.completed_at is None


def test_mark_running_from_pending():
    job = _pending()
    job.mark_running(_NOW)
    assert job.status == AsyncJobStatus.RUNNING
    assert job.started_at == _NOW


def test_mark_running_twice_raises():
    job = _pending()
    job.mark_running(_NOW)
    with pytest.raises(InvalidJobTransition):
        job.mark_running(_NOW)


def test_mark_ready_from_running_sets_result():
    job = _pending()
    job.mark_running(_NOW)
    job.mark_ready(result="done", now=_NOW)
    assert job.status == AsyncJobStatus.READY
    assert job.completed_at == _NOW
    assert job.result == "done"


def test_mark_ready_from_pending_raises():
    job = _pending()
    with pytest.raises(InvalidJobTransition):
        job.mark_ready(result="x", now=_NOW)


def test_mark_failed_from_running():
    job = _pending()
    job.mark_running(_NOW)
    job.mark_failed("boom", _NOW)
    assert job.status == AsyncJobStatus.FAILED
    assert job.error_message == "boom"
    assert job.completed_at == _NOW


def test_mark_failed_from_pending():
    job = _pending()
    job.mark_failed("boom", _NOW)
    assert job.status == AsyncJobStatus.FAILED


def test_mark_failed_from_terminal_raises():
    job = _pending()
    job.mark_cancelled(_NOW)
    with pytest.raises(InvalidJobTransition):
        job.mark_failed("boom", _NOW)


def test_mark_cancelled_from_pending():
    job = _pending()
    job.mark_cancelled(_NOW)
    assert job.status == AsyncJobStatus.CANCELLED
    assert job.completed_at == _NOW


def test_mark_cancelled_from_running():
    job = _pending()
    job.mark_running(_NOW)
    job.mark_cancelled(_NOW)
    assert job.status == AsyncJobStatus.CANCELLED


def test_mark_cancelled_from_terminal_raises():
    job = _pending()
    job.mark_cancelled(_NOW)
    with pytest.raises(InvalidJobTransition):
        job.mark_cancelled(_NOW)


def test_transitions_do_not_bump_version():
    # version is owned by the repository's optimistic-concurrency save(), never
    # by a domain transition.
    job = _pending()
    job.mark_running(_NOW)
    job.mark_ready(result="done", now=_NOW)
    assert job.version == 1


def test_terminal_states_constant():
    assert JOB_TERMINAL_STATES == frozenset(
        {AsyncJobStatus.READY, AsyncJobStatus.FAILED, AsyncJobStatus.CANCELLED}
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/domain/shared/test_async_job.py -q`
Expected: collection/import error — `ModuleNotFoundError: No module named 'cellar.domain.shared.async_job'`.

- [ ] **Step 3: Write minimal implementation**

Create `backend/src/cellar/domain/shared/async_job.py`:

```python
"""AsyncJob — shared base aggregate for async compute jobs.

State machine: pending -> running -> {ready | failed | cancelled};
pending -> cancelled. ready/failed/cancelled are terminal.

Subclasses add their result / cache-key fields and a ``mark_ready`` that calls
``_enter_ready(now)`` then sets those result fields. Transitions mutate in place
and return ``None`` (codebase norm); ``version`` is owned by the repository's
optimistic-concurrency ``save()`` — a transition never touches it.

The aggregate is a mutable ``AggregateRoot`` subclass so job repositories can
reuse the existing ``SQLAlchemyRepository`` base (whose ``save()`` mutates
``aggregate.version``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.shared.errors import DomainError


class AsyncJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


JOB_TERMINAL_STATES = frozenset(
    {AsyncJobStatus.READY, AsyncJobStatus.FAILED, AsyncJobStatus.CANCELLED}
)


class InvalidJobTransition(DomainError):
    """Raised when an async-job state transition violates the lifecycle."""


class AsyncJob(AggregateRoot):
    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        requested_by: uuid.UUID,
        requested_at: datetime,
        status: AsyncJobStatus = AsyncJobStatus.PENDING,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        self.workspace_id = workspace_id
        self.requested_by = requested_by
        self.requested_at = requested_at
        self.status = status
        self.started_at = started_at
        self.completed_at = completed_at
        self.error_message = error_message

    def mark_running(self, now: datetime) -> None:
        if self.status != AsyncJobStatus.PENDING:
            raise InvalidJobTransition(f"Cannot mark RUNNING from {self.status}")
        self.status = AsyncJobStatus.RUNNING
        self.started_at = now

    def mark_failed(self, error: str, now: datetime) -> None:
        if self.status not in {AsyncJobStatus.PENDING, AsyncJobStatus.RUNNING}:
            raise InvalidJobTransition(f"Cannot mark FAILED from {self.status}")
        self.status = AsyncJobStatus.FAILED
        self.completed_at = now
        self.error_message = error

    def mark_cancelled(self, now: datetime) -> None:
        if self.status in JOB_TERMINAL_STATES:
            raise InvalidJobTransition(f"Cannot CANCEL terminal {self.status}")
        self.status = AsyncJobStatus.CANCELLED
        self.completed_at = now

    def _enter_ready(self, now: datetime) -> None:
        """Shared guard + common mutations for the READY transition.

        A subclass ``mark_ready`` calls this first, then sets its result fields.
        """
        if self.status != AsyncJobStatus.RUNNING:
            raise InvalidJobTransition(f"Cannot mark READY from {self.status}")
        self.status = AsyncJobStatus.READY
        self.completed_at = now
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/domain/shared/test_async_job.py -q`
Expected: PASS (13 passed).

- [ ] **Step 5: Verify lint + architecture**

Run: `uv run ruff check src/cellar/domain/shared/async_job.py tests/unit/domain/shared/test_async_job.py`
Expected: no errors.

Run: `uv run lint-imports`
Expected: contracts kept (domain layer imports only domain).

- [ ] **Step 6: Commit**

```bash
git add src/cellar/domain/shared/async_job.py tests/unit/domain/shared/test_async_job.py
git commit -m "feat(shared): add AsyncJob domain base (status, transitions, terminal set)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `JobRepository` protocol + runner lifecycle helpers

**Files:**
- Create: `backend/src/cellar/application/shared/job_repository.py`
- Create: `backend/src/cellar/application/shared/async_job_runner.py`
- Test: `backend/tests/unit/application/shared/test_async_job_runner.py`

The two functions are the lifecycle scaffolding every runner needs — the bits that diverged into bugs when hand-copied. `claim_job` opens its own transaction (PENDING→RUNNING is committed before compute). `finalize_if_still_running` runs **inside the caller's** compute transaction (so the READY mark commits atomically with the result rows) and re-reads to honor a concurrent cancel.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/application/shared/test_async_job_runner.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.application.shared.async_job_runner import (
    claim_job,
    finalize_if_still_running,
)
from cellar.domain.shared.async_job import AsyncJob, AsyncJobStatus

_NOW = datetime(2026, 6, 16, tzinfo=UTC)


class _FakeJob(AsyncJob):
    def __init__(self, *, result: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.result = result

    def mark_ready(self, *, result: str, now: datetime) -> None:
        self._enter_ready(now)
        self.result = result


class FakeUoW:
    def __init__(self) -> None:
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        self.commits += 1
        return []


class FakeJobRepo:
    def __init__(self, job: _FakeJob | None = None) -> None:
        self._by_id: dict[uuid.UUID, _FakeJob] = {}
        if job is not None:
            self._by_id[job.id] = job

    async def find_by_id_in_workspace(self, workspace_id, id):
        job = self._by_id.get(id)
        return job if job is not None and job.workspace_id == workspace_id else None

    async def save(self, job):
        self._by_id[job.id] = job


def _pending(ws: uuid.UUID) -> _FakeJob:
    return _FakeJob(workspace_id=ws, requested_by=uuid.uuid4(), requested_at=_NOW)


# --- claim_job ---


@pytest.mark.asyncio
async def test_claim_pending_marks_running_and_returns_true():
    ws = uuid.uuid4()
    job = _pending(ws)
    repo, uow = FakeJobRepo(job), FakeUoW()
    proceed = await claim_job(
        repo, uow, job_id=job.id, workspace_id=ws, now=_NOW, log_prefix="test_job"
    )
    assert proceed is True
    assert repo._by_id[job.id].status == AsyncJobStatus.RUNNING
    assert uow.commits == 1


@pytest.mark.asyncio
async def test_claim_running_reclaims_without_write():
    ws = uuid.uuid4()
    job = _pending(ws)
    job.mark_running(_NOW)
    repo, uow = FakeJobRepo(job), FakeUoW()
    proceed = await claim_job(
        repo, uow, job_id=job.id, workspace_id=ws, now=_NOW, log_prefix="test_job"
    )
    assert proceed is True
    assert uow.commits == 0  # re-claim does not re-commit


@pytest.mark.asyncio
async def test_claim_terminal_returns_false():
    ws = uuid.uuid4()
    job = _pending(ws)
    job.mark_cancelled(_NOW)
    repo, uow = FakeJobRepo(job), FakeUoW()
    proceed = await claim_job(
        repo, uow, job_id=job.id, workspace_id=ws, now=_NOW, log_prefix="test_job"
    )
    assert proceed is False


@pytest.mark.asyncio
async def test_claim_missing_returns_false():
    ws = uuid.uuid4()
    repo, uow = FakeJobRepo(), FakeUoW()
    proceed = await claim_job(
        repo, uow, job_id=uuid.uuid4(), workspace_id=ws, now=_NOW, log_prefix="test_job"
    )
    assert proceed is False


@pytest.mark.asyncio
async def test_claim_wrong_workspace_returns_false():
    ws = uuid.uuid4()
    job = _pending(ws)
    repo, uow = FakeJobRepo(job), FakeUoW()
    proceed = await claim_job(
        repo, uow, job_id=job.id, workspace_id=uuid.uuid4(), now=_NOW, log_prefix="test_job"
    )
    assert proceed is False


# --- finalize_if_still_running ---


@pytest.mark.asyncio
async def test_finalize_applies_ready_when_running():
    ws = uuid.uuid4()
    job = _pending(ws)
    job.mark_running(_NOW)
    repo, uow = FakeJobRepo(job), FakeUoW()
    await finalize_if_still_running(
        repo,
        uow,
        job_id=job.id,
        workspace_id=ws,
        apply_ready=lambda j: j.mark_ready(result="done", now=_NOW),
        log_prefix="test_job",
    )
    saved = repo._by_id[job.id]
    assert saved.status == AsyncJobStatus.READY
    assert saved.result == "done"
    assert uow.commits == 1


@pytest.mark.asyncio
async def test_finalize_skips_when_cancelled():
    ws = uuid.uuid4()
    job = _pending(ws)
    job.mark_running(_NOW)
    job.mark_cancelled(_NOW)  # a concurrent cancel won
    repo, uow = FakeJobRepo(job), FakeUoW()
    await finalize_if_still_running(
        repo,
        uow,
        job_id=job.id,
        workspace_id=ws,
        apply_ready=lambda j: j.mark_ready(result="done", now=_NOW),
        log_prefix="test_job",
    )
    assert repo._by_id[job.id].status == AsyncJobStatus.CANCELLED
    assert uow.commits == 0


@pytest.mark.asyncio
async def test_finalize_skips_when_missing():
    ws = uuid.uuid4()
    repo, uow = FakeJobRepo(), FakeUoW()
    await finalize_if_still_running(
        repo,
        uow,
        job_id=uuid.uuid4(),
        workspace_id=ws,
        apply_ready=lambda j: j.mark_ready(result="done", now=_NOW),
        log_prefix="test_job",
    )
    assert uow.commits == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/application/shared/test_async_job_runner.py -q`
Expected: import error — `ModuleNotFoundError: No module named 'cellar.application.shared.async_job_runner'`.

- [ ] **Step 3: Write the `JobRepository` protocol**

Create `backend/src/cellar/application/shared/job_repository.py`:

```python
"""JobRepository — the minimal repository surface the shared async-job helpers
(``claim_job`` / ``finalize_if_still_running`` / ``MarkJobFailed``) depend on.

Satisfied structurally by any repository extending ``SQLAlchemyRepository``
whose aggregate is an ``AsyncJob`` — it already exposes
``find_by_id_in_workspace`` and ``save``.
"""

from __future__ import annotations

from typing import Protocol, TypeVar
from uuid import UUID

from cellar.domain.shared.async_job import AsyncJob

JobT = TypeVar("JobT", bound=AsyncJob)


class JobRepository(Protocol[JobT]):
    async def find_by_id_in_workspace(self, workspace_id: UUID, id: UUID) -> JobT | None: ...

    async def save(self, aggregate: JobT) -> None: ...
```

- [ ] **Step 4: Write the runner helpers**

Create `backend/src/cellar/application/shared/async_job_runner.py`:

```python
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
    log_prefix: str,
) -> bool:
    """Claim a job for execution. Returns True if the caller should proceed.

    PENDING -> RUNNING (persisted + committed) -> True.
    RUNNING -> True (re-claim a crashed/retried attempt; no write).
    missing or terminal -> False.
    """
    async with uow:
        job = await repository.find_by_id_in_workspace(workspace_id, job_id)
        if job is None:
            logger.error(f"{log_prefix}_not_found", job_id=str(job_id))
            return False
        if job.status == AsyncJobStatus.PENDING:
            job.mark_running(now)
            await repository.save(job)
            await uow.commit()
            return True
        if job.status == AsyncJobStatus.RUNNING:
            return True
        logger.info(f"{log_prefix}_not_runnable", job_id=str(job_id), status=str(job.status))
        return False


async def finalize_if_still_running(
    repository: JobRepository[JobT],
    uow: UnitOfWork,
    *,
    job_id: UUID,
    workspace_id: UUID,
    apply_ready: Callable[[JobT], None],
    log_prefix: str,
) -> None:
    """Re-read inside the active UoW and finalize only if still RUNNING.

    MUST be called inside the caller's ``async with uow:`` block so the READY
    mark commits atomically with the result rows written in that block. Honors
    a concurrent cancel (re-read sees a non-RUNNING status) and relies on the
    version-checked ``save`` as the TOCTOU backstop.
    """
    current = await repository.find_by_id_in_workspace(workspace_id, job_id)
    if current is None or current.status != AsyncJobStatus.RUNNING:
        logger.info(
            f"{log_prefix}_no_longer_running",
            job_id=str(job_id),
            status=str(current.status) if current is not None else "missing",
        )
        return
    apply_ready(current)
    await repository.save(current)
    await uow.commit()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/application/shared/test_async_job_runner.py -q`
Expected: PASS (8 passed).

- [ ] **Step 6: Verify lint + architecture**

Run: `uv run ruff check src/cellar/application/shared/job_repository.py src/cellar/application/shared/async_job_runner.py tests/unit/application/shared/test_async_job_runner.py`
Expected: no errors.

Run: `uv run lint-imports`
Expected: contracts kept (application imports only domain + application).

- [ ] **Step 7: Commit**

```bash
git add src/cellar/application/shared/job_repository.py src/cellar/application/shared/async_job_runner.py tests/unit/application/shared/test_async_job_runner.py
git commit -m "feat(shared): add JobRepository protocol + claim/finalize runner helpers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: generic `MarkJobFailed` boundary use case

**Files:**
- Create: `backend/src/cellar/application/shared/mark_job_failed.py`
- Test: `backend/tests/unit/application/shared/test_mark_job_failed.py`

One class for all jobs. Guarded + idempotent: a missing job is a no-op, an already-terminal job is left untouched (`InvalidJobTransition` swallowed), and a `ConcurrencyConflictError` on save (a cancel advanced the row between read and save) is swallowed so the winning terminal state stands.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/application/shared/test_mark_job_failed.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.application.shared.mark_job_failed import MarkJobFailed, MarkJobFailedInput
from cellar.domain.shared.async_job import AsyncJob, AsyncJobStatus
from cellar.domain.shared.errors import ConcurrencyConflictError

_NOW = datetime(2026, 6, 16, tzinfo=UTC)


class _FakeJob(AsyncJob):
    pass


class FakeUoW:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        return []


class FakeJobRepo:
    def __init__(self, job: _FakeJob | None = None, *, raise_on_save: bool = False) -> None:
        self._by_id: dict[uuid.UUID, _FakeJob] = {}
        if job is not None:
            self._by_id[job.id] = job
        self._raise_on_save = raise_on_save

    async def find_by_id_in_workspace(self, workspace_id, id):
        job = self._by_id.get(id)
        return job if job is not None and job.workspace_id == workspace_id else None

    async def save(self, job):
        if self._raise_on_save:
            raise ConcurrencyConflictError(entity_type="Job", entity_id=str(job.id))
        self._by_id[job.id] = job


def _running(ws: uuid.UUID) -> _FakeJob:
    job = _FakeJob(workspace_id=ws, requested_by=uuid.uuid4(), requested_at=_NOW)
    job.mark_running(_NOW)
    return job


def _make(repo) -> MarkJobFailed:
    return MarkJobFailed(repository=repo, uow=FakeUoW(), log_event="test_job_mark_failed_conflict")


@pytest.mark.asyncio
async def test_mark_failed_from_running():
    ws = uuid.uuid4()
    job = _running(ws)
    repo = FakeJobRepo(job)
    await _make(repo).execute(
        MarkJobFailedInput(job_id=job.id, workspace_id=ws, error="boom", now=_NOW)
    )
    assert repo._by_id[job.id].status == AsyncJobStatus.FAILED
    assert repo._by_id[job.id].error_message == "boom"


@pytest.mark.asyncio
async def test_mark_failed_idempotent_on_terminal():
    # A cancel that won the race must NOT be flipped to FAILED.
    ws = uuid.uuid4()
    job = _running(ws)
    job.mark_cancelled(_NOW)
    repo = FakeJobRepo(job)
    await _make(repo).execute(
        MarkJobFailedInput(job_id=job.id, workspace_id=ws, error="boom", now=_NOW)
    )
    assert repo._by_id[job.id].status == AsyncJobStatus.CANCELLED


@pytest.mark.asyncio
async def test_mark_failed_missing_is_noop():
    ws = uuid.uuid4()
    repo = FakeJobRepo()
    await _make(repo).execute(
        MarkJobFailedInput(job_id=uuid.uuid4(), workspace_id=ws, error="boom", now=_NOW)
    )
    assert repo._by_id == {}


@pytest.mark.asyncio
async def test_mark_failed_swallows_concurrency_conflict():
    # A concurrent cancel advanced the row between our read and save; the
    # ConcurrencyConflictError is swallowed (does not propagate).
    ws = uuid.uuid4()
    job = _running(ws)
    repo = FakeJobRepo(job, raise_on_save=True)
    await _make(repo).execute(
        MarkJobFailedInput(job_id=job.id, workspace_id=ws, error="boom", now=_NOW)
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/application/shared/test_mark_job_failed.py -q`
Expected: import error — `ModuleNotFoundError: No module named 'cellar.application.shared.mark_job_failed'`.

- [ ] **Step 3: Write minimal implementation**

Create `backend/src/cellar/application/shared/mark_job_failed.py`:

```python
"""MarkJobFailed — the single, guarded, idempotent FAILED-marker for every
async compute job.

Runners deliberately re-raise instead of marking FAILED (so a Temporal retry
can re-enter and recover), so FAILED is set here — invoked by the Temporal
workflow after retries, the Null orchestrator's inline task, and the inline
Start path. Idempotent: a job already terminal (a cancel won the race, or it
succeeded) is left untouched, and a concurrent transition that advances the row
between our read and save is swallowed.
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
    def __init__(self, *, repository: JobRepository, uow: UnitOfWork, log_event: str) -> None:
        self._repo = repository
        self._uow = uow
        self._log_event = log_event

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
                logger.info(self._log_event, job_id=str(payload.job_id))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/application/shared/test_mark_job_failed.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Verify lint + architecture**

Run: `uv run ruff check src/cellar/application/shared/mark_job_failed.py tests/unit/application/shared/test_mark_job_failed.py`
Expected: no errors.

Run: `uv run lint-imports`
Expected: contracts kept.

- [ ] **Step 6: Commit**

```bash
git add src/cellar/application/shared/mark_job_failed.py tests/unit/application/shared/test_mark_job_failed.py
git commit -m "feat(shared): add generic MarkJobFailed boundary use case

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Full-suite regression gate

No new code — confirm the primitives changed nothing for existing jobs.

- [ ] **Step 1: Run the SAR + shared suites**

Run: `uv run pytest tests/unit/domain/shared tests/unit/application/shared tests/unit/application/sar_analysis tests/unit/domain/sar_analysis -q`
Expected: all green (existing SAR tests unaffected; 25 new shared tests pass).

- [ ] **Step 2: Architecture + lint sweep**

Run: `uv run lint-imports && uv run ruff check src/cellar/domain/shared src/cellar/application/shared`
Expected: contracts kept, no lint errors.

---

## Self-Review

**Spec coverage (this plan is Plan 1 of N — deliberately partial):**
- Domain primitive (`AsyncJobStatus`, `JOB_TERMINAL_STATES`, `InvalidJobTransition`, `AsyncJob`) → Task 1. ✓
- Runner helpers (spec §Design "AsyncJobRunner base" → refined to module-level `claim_job` / `finalize_if_still_running` functions; composition decision unchanged) → Task 2. ✓
- Generic `MarkJobFailed` + `JobRepository` protocol → Tasks 2–3. ✓
- **Deferred to Plan 2 (decomposition migration), by design:** persistence reuse of `SQLAlchemyRepository` (no new code — it's a per-job migration), and the two Temporal primitives (`run_job_with_failure_marking`, `NullJobOrchestrator`) which need the real workflow + Temporal test harness to be exercised. Noted in the spec's migration order (step 1 builds primitives; the Temporal ones are only meaningfully testable with a job).

**Placeholder scan:** none — every step has complete code/commands.

**Type consistency:** `claim_job(repository, uow, *, job_id, workspace_id, now, log_prefix)` and `finalize_if_still_running(repository, uow, *, job_id, workspace_id, apply_ready, log_prefix)` match impl ↔ tests. `MarkJobFailed(repository=, uow=, log_event=)` + `MarkJobFailedInput(job_id, workspace_id, error, now)` match impl ↔ tests. `JobRepository.find_by_id_in_workspace(workspace_id, id)` matches the existing `SQLAlchemyRepository` base signature. `AsyncJob.__init__(*, workspace_id, requested_by, requested_at, …)` and `_enter_ready(now)` consistent across all three test files' `_FakeJob` subclasses.

**Note:** `asyncio_mode = "auto"` makes the `@pytest.mark.asyncio` markers optional; kept for parity with neighboring SAR test files.
