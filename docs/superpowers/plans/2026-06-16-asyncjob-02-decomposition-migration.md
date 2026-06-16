# R-group Decomposition Migration (Plan 2 of N) Implementation Plan

> **Execution model:** CONTROLLER-DRIVEN (not subagent-per-task). This is an *atomic* migration — flipping the aggregate's transitions (return-new → mutate) and renaming `find_by_id` → `find_by_id_in_workspace` break every caller simultaneously, so domain + repo + runner + use-cases + Temporal + DI + tests change together and the suite is RED until the whole change lands. The controller makes the edits in order, then runs the full SAR suite as the single gate, then dispatches spec + code-quality review on the diff. Steps use `- [ ]` for tracking.

**Goal:** Migrate the R-group decomposition job onto the shared AsyncJob primitives (Plan 1) with **zero behavior change** — the existing SAR suite is the regression gate — proving the mechanism on an already-correct job, and introducing the two Temporal primitives (`run_job_with_failure_marking`, `NullJobOrchestrator`) where they're first consumed.

**Architecture:** `RGroupDecompositionRun` becomes a mutable `AsyncJob` subclass; its repo extends the existing `SQLAlchemyRepository` (reusing the proven version-checked `save()` + `find_by_id_in_workspace`); its runner uses `claim_job` + `finalize_if_still_running`; its Temporal workflow uses `run_job_with_failure_marking`; its Null orchestrator extends `NullJobOrchestrator`; FAILED is the generic `MarkJobFailed` (the per-job `MarkDecompositionRunFailed` is deleted).

**Tech Stack:** Python 3.13, SQLAlchemy 2.0 async, Temporal (temporalio), structlog, pytest (`asyncio_mode=auto`), ruff, Import Linter.

**Reference:** spec `docs/superpowers/specs/2026-06-16-generic-asyncjob-design.md`; primitives `docs/superpowers/plans/2026-06-16-asyncjob-01-primitives.md` (landed: `AsyncJob`, `AsyncJobStatus`, `JOB_TERMINAL_STATES`, `InvalidJobTransition`, `JobRepository`, `claim_job`, `finalize_if_still_running`, `MarkJobFailed`/`MarkJobFailedInput`).

**Run all commands from `backend/`.**

---

## File inventory

**New (2):**
- `src/cellar/infrastructure/temporal/workflow_support.py` — `run_job_with_failure_marking` (workflow-safe; temporalio-only imports).
- `src/cellar/infrastructure/temporal/orchestrator_base.py` — `NullJobOrchestrator` base.

**Rewritten/edited (12):**
- `domain/sar_analysis/rgroup_decomposition_run.py` — `RGroupDecompositionRun(AsyncJob)`.
- `infrastructure/persistence/sqlalchemy/sar_analysis/rgroup_decomposition_run_repository.py` — extend `SQLAlchemyRepository`.
- `application/sar_analysis/repositories.py` — protocol: `find_by_id` → `find_by_id_in_workspace`.
- `application/sar_analysis/run_decomposition.py` — use the runner helpers.
- `application/sar_analysis/start_decomposition_run.py` — mutable transitions + generic `MarkJobFailed` + rename.
- `application/sar_analysis/get_decomposition_run.py` — rename.
- `application/sar_analysis/cancel_decomposition_run.py` — rename + `InvalidJobTransition` + mutable.
- `infrastructure/temporal/activities/rgroup_decomposition.py` — generic `MarkJobFailed`.
- `infrastructure/temporal/workflows/rgroup_decomposition.py` — use `run_job_with_failure_marking`.
- `infrastructure/temporal/orchestrators/rgroup_decomposition.py` — `NullJobOrchestrator` base.
- `infrastructure/di/_sar_analysis.py` — generic `MarkJobFailed(job_type="rgroup_decomposition")`.
- `infrastructure/temporal/worker.py` — generic `MarkJobFailed` wiring.

**Deleted (1):** `application/sar_analysis/mark_decomposition_run_failed.py` (→ generic `MarkJobFailed`).

**Tests edited (5):**
- `tests/unit/domain/sar_analysis/test_rgroup_decomposition_run.py`
- `tests/unit/application/sar_analysis/test_run_decomposition.py`
- `tests/unit/application/sar_analysis/test_get_cancel_decomposition_run.py`
- `tests/unit/application/sar_analysis/test_mark_job_failed.py` (drop the decomposition half; keep projection)
- `tests/unit/infrastructure/temporal/test_rgroup_decomposition_orchestrators.py`
- (verify `tests/integration/persistence/sar_analysis/test_decomposition_async_e2e.py` — update any `find_by_id` calls)

No DB migration: `status` column already stores the lowercase enum values, identical between `RGroupDecompositionRunStatus` and `AsyncJobStatus`.

---

## Task 1 — Temporal primitives (2 new files)

- [ ] **1a. `src/cellar/infrastructure/temporal/workflow_support.py`** (workflow-safe — temporalio + stdlib only):

```python
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
```

- [ ] **1b. `src/cellar/infrastructure/temporal/orchestrator_base.py`** (`NullJobOrchestrator` base — NOT imported by any workflow module):

```python
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
```

- [ ] **1c.** `uv run ruff check src/cellar/infrastructure/temporal/workflow_support.py src/cellar/infrastructure/temporal/orchestrator_base.py` and `uv run lint-imports` → clean. (These are additive; suite stays green.)

---

## Task 2 — Domain aggregate: `RGroupDecompositionRun(AsyncJob)`

- [ ] **2a. Replace the entire body of `domain/sar_analysis/rgroup_decomposition_run.py` with:**

```python
"""RGroupDecompositionRun — persisted async R-group decomposition over a member
set against one core.

Lifecycle (see ``AsyncJob``): pending -> running -> {ready | failed | cancelled};
pending -> cancelled. The aggregate holds only the *header* (discovered labels +
counts); per-molecule assignments are separate rows (see the repository).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from cellar.domain.shared.async_job import AsyncJob, AsyncJobStatus


class RGroupDecompositionRun(AsyncJob):
    def __init__(
        self,
        *,
        workspace_id: UUID,
        requested_by: UUID,
        membership_hash: str,
        core_smiles: str,
        core_hash: str,
        requested_at: datetime,
        id: UUID | None = None,
        status: AsyncJobStatus = AsyncJobStatus.PENDING,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
        rgroup_labels: list[str] | None = None,
        matched_count: int = 0,
        unmatched_count: int = 0,
        total_count: int = 0,
        version: int = 1,
    ) -> None:
        super().__init__(
            id=id,
            workspace_id=workspace_id,
            requested_by=requested_by,
            requested_at=requested_at,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            error_message=error_message,
            version=version,
        )
        self.membership_hash = membership_hash
        self.core_smiles = core_smiles
        self.core_hash = core_hash
        self.rgroup_labels = list(rgroup_labels) if rgroup_labels is not None else []
        self.matched_count = matched_count
        self.unmatched_count = unmatched_count
        self.total_count = total_count

    @classmethod
    def create(
        cls,
        *,
        workspace_id: UUID,
        requested_by: UUID,
        membership_hash: str,
        core_smiles: str,
        core_hash: str,
        now: datetime,
    ) -> RGroupDecompositionRun:
        return cls(
            workspace_id=workspace_id,
            requested_by=requested_by,
            membership_hash=membership_hash,
            core_smiles=core_smiles,
            core_hash=core_hash,
            requested_at=now,
        )

    def mark_ready(
        self,
        *,
        rgroup_labels: list[str],
        matched_count: int,
        unmatched_count: int,
        total_count: int,
        now: datetime,
    ) -> None:
        self._enter_ready(now)
        self.rgroup_labels = list(rgroup_labels)
        self.matched_count = matched_count
        self.unmatched_count = unmatched_count
        self.total_count = total_count
```

Removed: the local `RGroupDecompositionRunStatus` enum, `InvalidRGroupRunTransition`, `_TERMINAL`, the `@dataclass(frozen=True)`, and the inherited `mark_running`/`mark_failed`/`mark_cancelled` (now from `AsyncJob`, mutating + returning `None`).

---

## Task 3 — Repository: extend `SQLAlchemyRepository`

- [ ] **3a. Rewrite `infrastructure/persistence/sqlalchemy/sar_analysis/rgroup_decomposition_run_repository.py`:**

```python
"""SQLAlchemy implementation of RGroupDecompositionRunRepository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, insert, select

from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRun
from cellar.domain.sar_analysis.rgroup_types import RGroupAssignment
from cellar.domain.shared.async_job import AsyncJobStatus
from cellar.infrastructure.persistence.sqlalchemy.base_repository import SQLAlchemyRepository
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.rgroup_decomposition_models import (
    RGroupAssignmentModel,
    RGroupDecompositionRunModel,
)


class SQLAlchemyRGroupDecompositionRunRepository(
    SQLAlchemyRepository[RGroupDecompositionRun, RGroupDecompositionRunModel]
):
    model_class = RGroupDecompositionRunModel

    def _to_domain(self, model: RGroupDecompositionRunModel) -> RGroupDecompositionRun:
        return RGroupDecompositionRun(
            id=model.id,
            workspace_id=model.workspace_id,
            requested_by=model.requested_by,
            membership_hash=model.membership_hash,
            core_smiles=model.core_smiles,
            core_hash=model.core_hash,
            requested_at=model.requested_at,
            status=AsyncJobStatus(model.status),
            started_at=model.started_at,
            completed_at=model.completed_at,
            error_message=model.error_message,
            rgroup_labels=list(model.rgroup_labels or []),
            matched_count=model.matched_count,
            unmatched_count=model.unmatched_count,
            total_count=model.total_count,
            version=model.version,
        )

    def _to_model(self, aggregate: RGroupDecompositionRun) -> RGroupDecompositionRunModel:
        return RGroupDecompositionRunModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            requested_by=aggregate.requested_by,
            membership_hash=aggregate.membership_hash,
            core_smiles=aggregate.core_smiles,
            core_hash=aggregate.core_hash,
            requested_at=aggregate.requested_at,
            status=aggregate.status.value,
            started_at=aggregate.started_at,
            completed_at=aggregate.completed_at,
            error_message=aggregate.error_message,
            rgroup_labels=list(aggregate.rgroup_labels),
            matched_count=aggregate.matched_count,
            unmatched_count=aggregate.unmatched_count,
            total_count=aggregate.total_count,
            version=aggregate.version,
        )

    def _update_model(
        self, model: RGroupDecompositionRunModel, aggregate: RGroupDecompositionRun
    ) -> None:
        # version is owned by the base save()'s optimistic-concurrency UPDATE.
        model.status = aggregate.status.value
        model.started_at = aggregate.started_at
        model.completed_at = aggregate.completed_at
        model.error_message = aggregate.error_message
        model.rgroup_labels = list(aggregate.rgroup_labels)
        model.matched_count = aggregate.matched_count
        model.unmatched_count = aggregate.unmatched_count
        model.total_count = aggregate.total_count

    async def find_cached(
        self, *, workspace_id: UUID, membership_hash: str, core_hash: str
    ) -> RGroupDecompositionRun | None:
        stmt = (
            select(RGroupDecompositionRunModel)
            .where(
                RGroupDecompositionRunModel.workspace_id == workspace_id,
                RGroupDecompositionRunModel.membership_hash == membership_hash,
                RGroupDecompositionRunModel.core_hash == core_hash,
                RGroupDecompositionRunModel.status == AsyncJobStatus.READY.value,
            )
            .order_by(RGroupDecompositionRunModel.completed_at.desc())
            .limit(1)
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def write_assignments(
        self, run_id: UUID, assignments: list[RGroupAssignment]
    ) -> None:
        batch = 1000
        rows = [
            {"run_id": run_id, "molecule_id": a.molecule_id, "rgroups": a.rgroups}
            for a in assignments
        ]
        for i in range(0, len(rows), batch):
            await self._session.execute(insert(RGroupAssignmentModel), rows[i : i + batch])

    async def delete_assignments(self, run_id: UUID) -> None:
        """Remove all assignment rows for a run, so a re-run (e.g. a Temporal
        retry) is idempotent and never collides on the (run_id, molecule_id) PK."""
        await self._session.execute(
            sa_delete(RGroupAssignmentModel).where(RGroupAssignmentModel.run_id == run_id)
        )

    async def fetch_assignments(
        self, run_id: UUID, *, workspace_id: UUID, offset: int, limit: int
    ) -> list[RGroupAssignment]:
        stmt = (
            select(RGroupAssignmentModel)
            .join(
                RGroupDecompositionRunModel,
                RGroupDecompositionRunModel.id == RGroupAssignmentModel.run_id,
            )
            .where(
                RGroupAssignmentModel.run_id == run_id,
                RGroupDecompositionRunModel.workspace_id == workspace_id,
            )
            .order_by(RGroupAssignmentModel.molecule_id)
            .offset(offset)
            .limit(limit)
        )
        models = (await self._session.execute(stmt)).scalars().all()
        return [
            RGroupAssignment(molecule_id=m.molecule_id, rgroups=dict(m.rgroups))
            for m in models
        ]

    async def count_assignments(self, run_id: UUID, *, workspace_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(RGroupAssignmentModel)
            .join(
                RGroupDecompositionRunModel,
                RGroupDecompositionRunModel.id == RGroupAssignmentModel.run_id,
            )
            .where(
                RGroupAssignmentModel.run_id == run_id,
                RGroupDecompositionRunModel.workspace_id == workspace_id,
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())
```

Notes: `save()` + `find_by_id_in_workspace` come from the base. The base exposes `self._session` (== `self._uow.session`). Module-level `_to_model`/`_apply_to_model`/`_to_domain` are gone (now methods). `find_by_id(run_id, *, workspace_id)` is gone (callers use `find_by_id_in_workspace`).

---

## Task 4 — Repo protocol

- [ ] **4a.** In `application/sar_analysis/repositories.py`, in `RGroupDecompositionRunRepository`, replace:

```python
    async def find_by_id(
        self, run_id: UUID, *, workspace_id: UUID
    ) -> RGroupDecompositionRun | None: ...
```

with:

```python
    async def find_by_id_in_workspace(
        self, workspace_id: UUID, id: UUID
    ) -> RGroupDecompositionRun | None: ...
```

(Leave the other three protocols — scaffold/umap/projection — untouched; they migrate in later plans.)

---

## Task 5 — Runner

- [ ] **5a. Rewrite `application/sar_analysis/run_decomposition.py`'s `run()`** to use the helpers. Keep `ready_counts` and the dataclass fields. New body:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import structlog

from cellar.application.sar_analysis.decomposition_members import DecompositionMemberStream
from cellar.application.sar_analysis.repositories import RGroupDecompositionRunRepository
from cellar.application.sar_analysis.rgroup_decomposition import StreamingDecomposer
from cellar.application.shared.async_job_runner import claim_job, finalize_if_still_running
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.rgroup_types import RGroupDecompositionResult

logger = structlog.get_logger(__name__)

_JOB_TYPE = "rgroup_decomposition"


def ready_counts(result: RGroupDecompositionResult) -> tuple[int, int, int]:
    """The verified count bridge: (matched, unmatched, total)."""
    matched = len(result.assignments)
    unmatched = len(result.unmatched_ids)
    return matched, unmatched, matched + unmatched


@dataclass
class RunDecomposition:
    members: DecompositionMemberStream
    decomposer: StreamingDecomposer
    repository: RGroupDecompositionRunRepository
    uow: UnitOfWork

    async def run(
        self,
        *,
        run_id: UUID,
        workspace_id: UUID,
        core_smiles: str,
        collection_id: UUID | None = None,
        molecule_ids: list[UUID] | None = None,
    ) -> None:
        log = logger.bind(run_id=str(run_id), workspace_id=str(workspace_id))
        try:
            if not await claim_job(
                self.repository,
                self.uow,
                job_id=run_id,
                workspace_id=workspace_id,
                now=datetime.now(UTC),
                job_type=_JOB_TYPE,
            ):
                return

            async with self.uow:
                await self.repository.delete_assignments(run_id)
                session = self.decomposer.session(core_smiles=core_smiles)
                async for batch in self.members.stream(
                    workspace_id=workspace_id,
                    collection_id=collection_id,
                    molecule_ids=molecule_ids,
                ):
                    for molecule_id, smiles, _version in batch:
                        session.add(molecule_id, smiles or "")
                result = session.finish()
                await self.repository.write_assignments(run_id, result.assignments)
                matched, unmatched, total = ready_counts(result)

                await finalize_if_still_running(
                    self.repository,
                    self.uow,
                    job_id=run_id,
                    workspace_id=workspace_id,
                    apply_ready=lambda run: run.mark_ready(
                        rgroup_labels=result.rgroup_labels,
                        matched_count=matched,
                        unmatched_count=unmatched,
                        total_count=total,
                        now=datetime.now(UTC),
                    ),
                    job_type=_JOB_TYPE,
                )
            log.info("rgroup_decomposition_run_ready", matched=matched, unmatched=unmatched)
        except Exception:
            # FAILED is marked at the orchestration boundary, not here — so a
            # retry can re-enter and recover. Re-raise for the boundary.
            log.exception("rgroup_decomposition_run_failed")
            raise
```

The trailing `await self.uow.commit()` is gone — `finalize_if_still_running` commits inside the block (atomic with the assignment writes).

---

## Task 6 — Use cases

- [ ] **6a. `start_decomposition_run.py`:**
  - Imports: drop `MarkDecompositionRunFailed`/`MarkDecompositionRunFailedInput`; add `from cellar.application.shared.mark_job_failed import MarkJobFailed, MarkJobFailedInput`. Replace `from cellar.domain.sar_analysis.rgroup_decomposition_run import (RGroupDecompositionRun, RGroupDecompositionRunStatus)` with `from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRun` and `from cellar.domain.shared.async_job import AsyncJobStatus`.
  - In `__init__`: `self._mark_failed = MarkDecompositionRunFailed(repository=repository, uow=uow)` → `self._mark_failed = MarkJobFailed(repository=repository, uow=uow, job_type="rgroup_decomposition")`.
  - The initial-save line (mutable `mark_running`):
    ```python
    is_inline = count <= self._inline_threshold
    if is_inline:
        run.mark_running(payload.now)
    await self._repo.save(run)
    await self._uow.commit()
    ```
  - Inline finalize block:
    ```python
    current = await self._repo.find_by_id_in_workspace(payload.workspace_id, run.id)
    if current is None or current.status != AsyncJobStatus.RUNNING:
        return current if current is not None else run
    current.mark_ready(
        rgroup_labels=result.rgroup_labels,
        matched_count=matched,
        unmatched_count=unmatched,
        total_count=total,
        now=payload.now,
    )
    await self._repo.save(current)
    await self._uow.commit()
    return current
    ```
  - The `except` mark-failed: `MarkDecompositionRunFailedInput(run_id=run.id, ...)` → `MarkJobFailedInput(job_id=run.id, workspace_id=payload.workspace_id, error="inline decomposition failed", now=payload.now)`.

- [ ] **6b. `get_decomposition_run.py`:** `run = await self._repo.find_by_id(payload.run_id, workspace_id=payload.workspace_id)` → `run = await self._repo.find_by_id_in_workspace(payload.workspace_id, payload.run_id)`.

- [ ] **6c. `cancel_decomposition_run.py`:**
  - Import: `from cellar.domain.sar_analysis.rgroup_decomposition_run import (InvalidRGroupRunTransition, RGroupDecompositionRun)` → `from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRun` + `from cellar.domain.shared.async_job import InvalidJobTransition`.
  - Body:
    ```python
    run = await self._repo.find_by_id_in_workspace(payload.workspace_id, payload.run_id)
    if run is None:
        return Failure(NotFoundError("RGroupDecompositionRun", str(payload.run_id)))
    try:
        run.mark_cancelled(payload.now)
    except InvalidJobTransition:
        return Success(run)  # already terminal — idempotent no-op
    await self._repo.save(run)
    await self._uow.commit()
    await self._orchestrator.cancel(run_id=run.id)
    return Success(run)
    ```

---

## Task 7 — Delete the per-job mark-failed use case

- [ ] **7a.** `git rm backend/src/cellar/application/sar_analysis/mark_decomposition_run_failed.py`

---

## Task 8 — Temporal glue

- [ ] **8a. `infrastructure/temporal/activities/rgroup_decomposition.py`:**
  - Imports: drop `MarkDecompositionRunFailed`/`MarkDecompositionRunFailedInput`; add `from cellar.application.shared.mark_job_failed import MarkJobFailed, MarkJobFailedInput`.
  - `mark_failed: MarkDecompositionRunFailed` → `mark_failed: MarkJobFailed` in `__init__`.
  - In `mark_rgroup_decomposition_failed`: `MarkDecompositionRunFailedInput(run_id=uuid.UUID(input.run_id), ...)` → `MarkJobFailedInput(job_id=uuid.UUID(input.run_id), workspace_id=uuid.UUID(input.workspace_id), error=input.error, now=datetime.now(UTC))`. (Keep `MarkRunFailedInput` Temporal payload dataclass unchanged.)

- [ ] **8b. `infrastructure/temporal/workflows/rgroup_decomposition.py`:** replace the `try/except ActivityError` body of `run()` with a call to the helper. New `run`:

```python
from datetime import timedelta

from temporalio import workflow

from cellar.infrastructure.temporal.workflow_support import run_job_with_failure_marking

with workflow.unsafe.imports_passed_through():
    from cellar.infrastructure.temporal.activities.rgroup_decomposition import (
        MarkRunFailedInput,
        RGroupDecompositionActivities,
        RunDecompositionInput,
    )

# ... RGroupDecompositionWorkflowInput dataclass unchanged ...

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
```

- [ ] **8c. `infrastructure/temporal/orchestrators/rgroup_decomposition.py`:** `NullRGroupDecompositionOrchestrator` extends `NullJobOrchestrator`; the `TemporalRGroupDecompositionOrchestrator` is unchanged. Replace the Null class with:

```python
from cellar.application.shared.mark_job_failed import MarkJobFailed
from cellar.infrastructure.temporal.orchestrator_base import NullJobOrchestrator


class NullRGroupDecompositionOrchestrator(NullJobOrchestrator):
    """In-process fallback when Temporal is unavailable."""

    def __init__(
        self,
        runner: RGroupDecompositionRunner | RunDecomposition,
        *,
        mark_failed: MarkJobFailed | None = None,
    ) -> None:
        super().__init__(mark_failed=mark_failed, job_type="rgroup_decomposition")
        self._runner = runner

    async def schedule(
        self,
        *,
        run_id: UUID,
        workspace_id: UUID,
        core_smiles: str,
        collection_id: UUID | None = None,
        molecule_ids: list[UUID] | None = None,
    ) -> None:
        self._spawn(
            lambda: self._runner.run(
                run_id=run_id,
                workspace_id=workspace_id,
                core_smiles=core_smiles,
                collection_id=collection_id,
                molecule_ids=molecule_ids,
            ),
            job_id=run_id,
            workspace_id=workspace_id,
        )

    async def cancel(self, *, run_id: UUID) -> None:
        return None  # inline tasks cannot be cancelled by run id
```

Drop the now-unused imports (`asyncio`, `datetime`, `MarkDecompositionRunFailed`, `MarkDecompositionRunFailedInput`) from this module; keep `Protocol`, `UUID`, `Client`, `RunDecomposition`, the workflow imports, `MAIN_TASK_QUEUE`, `structlog` only if still used (the Temporal class is unchanged so its imports stay).

---

## Task 9 — DI + worker

- [ ] **9a. `infrastructure/di/_sar_analysis.py`:**
  - Import: `from cellar.application.sar_analysis.mark_decomposition_run_failed import MarkDecompositionRunFailed` → `from cellar.application.shared.mark_job_failed import MarkJobFailed`.
  - In `_null_rgroup_orchestrator`:
    ```python
    return NullRGroupDecompositionOrchestrator(
        c[RunDecomposition],
        mark_failed=MarkJobFailed(
            repository=SQLAlchemyRGroupDecompositionRunRepository(fail_uow),
            uow=fail_uow,
            job_type="rgroup_decomposition",
        ),
    )
    ```

- [ ] **9b. `infrastructure/temporal/worker.py`:**
  - Import: `from cellar.application.sar_analysis.mark_decomposition_run_failed import MarkDecompositionRunFailed` → `from cellar.application.shared.mark_job_failed import MarkJobFailed`.
  - In `rgroup_decomposition_activities = RGroupDecompositionActivities(...)`:
    ```python
    MarkJobFailed(
        repository=SQLAlchemyRGroupDecompositionRunRepository(_dec_fail_uow),
        uow=_dec_fail_uow,
        job_type="rgroup_decomposition",
    )
    ```

---

## Task 10 — Test updates

- [ ] **10a. `tests/unit/domain/sar_analysis/test_rgroup_decomposition_run.py`:** rewrite for the mutable API:
  - Import `from cellar.domain.shared.async_job import AsyncJobStatus, InvalidJobTransition` instead of the old enum/exception.
  - Replace every `run.mark_running(_NOW)` (returns new) with mutate-then-use: `run = _new_run(); run.mark_running(_NOW)`. `mark_ready`/`mark_failed`/`mark_cancelled` likewise mutate `run` then assert on `run`.
  - `RGroupDecompositionRunStatus` → `AsyncJobStatus`; `InvalidRGroupRunTransition` → `InvalidJobTransition`.

- [ ] **10b. `tests/unit/application/sar_analysis/test_run_decomposition.py`:** in `FakeRunRepo`, rename `find_by_id(self, run_id, *, workspace_id)` → `find_by_id_in_workspace(self, workspace_id, run_id)` (swap arg order). Update the `CancellingSession.finish` line `repo._runs[run.id] = repo._runs[run.id].mark_cancelled(_NOW)` → `repo._runs[run.id].mark_cancelled(_NOW)` (mutate in place). `RGroupDecompositionRunStatus` → `AsyncJobStatus`. The `running = _pending_run(ws).mark_running(_NOW)` helper → `running = _pending_run(ws); running.mark_running(_NOW)`.

- [ ] **10c. `tests/unit/application/sar_analysis/test_get_cancel_decomposition_run.py`:** `FakeRunRepo.find_by_id` → `find_by_id_in_workspace(self, workspace_id, run_id)`. `RGroupDecompositionRunStatus` → `AsyncJobStatus`. Mutable transitions: `_pending(ws).mark_running(_NOW).mark_ready(...)` → build then mutate step by step (e.g. `ready = _pending(ws); ready.mark_running(_NOW); ready.mark_ready(...)`).

- [ ] **10d. `tests/unit/application/sar_analysis/test_mark_job_failed.py` (the sar_analysis one):** remove the decomposition half — delete the `MarkDecompositionRunFailed`/`MarkDecompositionRunFailedInput` import, `FakeRunRepo`, `_running_run`, and the two `test_mark_run_failed_*` tests. Keep the `MarkActivityProjectionFailed` half intact (projection isn't migrated yet). The generic `MarkJobFailed` is already covered by `tests/unit/application/shared/test_mark_job_failed.py`.

- [ ] **10e. `tests/unit/infrastructure/temporal/test_rgroup_decomposition_orchestrators.py`:** read it; update any `MarkDecompositionRunFailed` references to `MarkJobFailed(..., job_type="rgroup_decomposition")` and any `find_by_id` fake to `find_by_id_in_workspace`. The `NullRGroupDecompositionOrchestrator` construction signature is unchanged (`runner`, `mark_failed=`), so behavioral assertions should hold.

- [ ] **10f. `tests/integration/persistence/sar_analysis/test_decomposition_async_e2e.py`:** read it; replace any direct `repo.find_by_id(id, workspace_id=...)` with `repo.find_by_id_in_workspace(workspace_id, id)`; `RGroupDecompositionRunStatus` → `AsyncJobStatus`; mutable transitions if it constructs/transitions runs directly.

---

## Task 11 — Verification gate

- [ ] **11a.** `uv run pytest tests/unit/domain/sar_analysis tests/unit/application/sar_analysis tests/unit/infrastructure/temporal -q` → all green.
- [ ] **11b.** `uv run pytest tests/integration/persistence/sar_analysis -q` (requires Docker) → green, OR record as deferred if Docker unavailable.
- [ ] **11c.** `uv run lint-imports` → 3 contracts kept. `uv run ruff check src/cellar/{domain,application,infrastructure}/...` (the touched modules) → clean.
- [ ] **11d.** Full SAR unit suite as the zero-behavior-change regression gate: `uv run pytest tests/unit -q -k "sar or decomposition or async_job or temporal"` (or the whole `tests/unit`) → green.
- [ ] **11e.** Commit (single cohesive commit, explicit pathspec — never `git add -A`; the `run-dr-results.tsx` WIP must stay unstaged):
  `git commit -m "refactor(sar): migrate R-group decomposition onto the AsyncJob mechanism" -- <each touched path>` with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.

---

## Self-Review

**Spec coverage:** mutable `AsyncJob` subclass (T2) + reuse `SQLAlchemyRepository` (T3) + runner helpers (T5) + generic `MarkJobFailed` (T6/7/8/9) + Temporal primitives (T1, consumed in T8) + the `find_by_id` rename ripple (T4/5/6/10) — all present. Zero behavior change is enforced by the existing suite (T11).

**Type/signature consistency:** `find_by_id_in_workspace(workspace_id, id)` order matches the base + `JobRepository`. `mark_ready(*, rgroup_labels, matched_count, unmatched_count, total_count, now) -> None` matches the runner's `apply_ready` closure and the inline path. `MarkJobFailed(repository=, uow=, job_type=)` + `MarkJobFailedInput(job_id=, workspace_id=, error=, now=)` match Plan 1. `run_job_with_failure_marking(run_activity=, run_input=, mark_failed_activity=, mark_failed_input=, run_timeout=)` matches the workflow call.

**Risks:** (1) the e2e integration test needs Docker — if unavailable, run the unit suite as the gate and note the e2e as deferred-verify. (2) `orchestrator_base.py` imports the application layer — confirm `lint-imports` still passes (infrastructure → application is allowed). (3) confirm no *other* module imports `mark_decomposition_run_failed` before deleting it (`grep -rl mark_decomposition_run_failed src tests`).
