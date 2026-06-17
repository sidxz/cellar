# Scaffold-Tree Migration (Plan 4 of N)

> **NOT zero behavior change.** scaffold_tree is one of the two BUGGY jobs. Migrating it onto the AsyncJob mechanism **fixes** its latent bugs and **adds** the boundary FAILED-handling it lacks. So: mechanical migration (mirror Plan 2/3) + bug fixes + new boundary wiring + NEW tests asserting the corrected behavior. Controller-driven; suite + new tests are the gate.

**Reference:** decomposition `11c4c24b` / projection `1ac1c4ea` are the mechanism template. Primitives already exist.

## Bugs being fixed (current → correct)
1. **Blind/version-frozen save** (`scaffold_tree_job_repository.py:32-38` — `_apply_to_model` then no version-checked UPDATE) → reuse base `SQLAlchemyRepository.save()`.
2. **Unconditional claim** (`run_scaffold_tree.py:63-65` — `job.mark_running()` with no PENDING-check / no RUNNING re-claim → a retry crashes on `InvalidTransition`) → `claim_job`.
3. **No re-read guard** (`run_scaffold_tree.py:75` reuses the stale `running` object → a concurrent cancel is clobbered to READY) → `finalize_if_still_running`.
4. **FAILED marked inside the runner** (`run_scaffold_tree.py:80-91` → terminal-FAILED on attempt 1 means Temporal retries can't recover) → re-raise only; FAILED at the boundary.
5. **No boundary mark-failed**: the workflow has no `except ActivityError`→mark-failed; the Null orchestrator has no `mark_failed` (it relied on the in-runner path); there is no mark-failed activity → ADD all three via the generic `MarkJobFailed` + `run_job_with_failure_marking` + `NullJobOrchestrator`.

Result is **header-only** (`result_json`, no child rows) → the runner is claim → compute → finalize (no reset/write-rows step). Model has `WorkspaceIdMixin`+`VersionMixin` → base-compatible. No DB migration (status strings match).

## Task 1 — Aggregate (`domain/sar_analysis/scaffold_tree_job.py`)

```python
"""ScaffoldTreeJob — persisted unit of async scaffold-network compute.

Lifecycle (see ``AsyncJob``): pending -> running -> {ready | failed | cancelled};
pending -> cancelled. The result tree is stored on the header (no child rows).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from cellar.domain.sar_analysis.scaffold_tree_types import ScaffoldTreeResult
from cellar.domain.shared.async_job import AsyncJob, AsyncJobStatus


class ScaffoldTreeJob(AsyncJob):
    def __init__(
        self,
        *,
        workspace_id: UUID,
        requested_by: UUID,
        ids_hash: str,
        requested_at: datetime,
        id: UUID | None = None,
        status: AsyncJobStatus = AsyncJobStatus.PENDING,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
        result: ScaffoldTreeResult | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(
            id=id, workspace_id=workspace_id, requested_by=requested_by,
            requested_at=requested_at, status=status, started_at=started_at,
            completed_at=completed_at, error_message=error_message, version=version,
        )
        self.ids_hash = ids_hash
        self.result = result

    @classmethod
    def create(
        cls, *, workspace_id: UUID, requested_by: UUID, ids_hash: str, now: datetime
    ) -> ScaffoldTreeJob:
        return cls(workspace_id=workspace_id, requested_by=requested_by, ids_hash=ids_hash, requested_at=now)

    def mark_ready(self, *, result: ScaffoldTreeResult, now: datetime) -> None:
        self._enter_ready(now)
        self.result = result
```

(Drop the local `ScaffoldTreeJobStatus`, `InvalidScaffoldTreeJobTransition`, `_TERMINAL`, `@dataclass(frozen=True)`, and the inherited transitions. NOTE: `mark_ready` becomes keyword-only `(*, result, now)` — callers + tests update.)

## Task 2 — Repo (extend base; keep the JSON (de)serialize helpers)

`…/sqlalchemy/sar_analysis/scaffold_tree_job_repository.py`: `class SQLAlchemyScaffoldTreeJobRepository(SQLAlchemyRepository[ScaffoldTreeJob, ScaffoldTreeJobModel])` with `model_class = ScaffoldTreeJobModel`; `_to_domain`/`_to_model`/`_update_model` (status via `aggregate.status.value`, `result_json = _serialize_result(aggregate.result) if aggregate.result else None`; `_update_model` omits version); keep `find_cached(*, ids_hash, ttl_seconds)` (uses `AsyncJobStatus.READY.value`, `self._session`, `_deserialize_result`). Keep `_serialize_result`/`_deserialize_result` as module functions. Drop the hand-rolled `save()` + `find_by_id`. Drop the `ScaffoldTreeJobStatus`/`AsyncUnitOfWork` imports; add `AsyncJobStatus` + `SQLAlchemyRepository`.

## Task 3 — Protocol
`repositories.py` `ScaffoldTreeJobRepository`: `find_by_id(job_id, *, workspace_id)` → `find_by_id_in_workspace(workspace_id, id)`. (`find_cached(*, ids_hash, ttl_seconds)` stays.)

## Task 4 — Runner (the core bug-fix)
`run_scaffold_tree.py`:
```python
from cellar.application.shared.async_job_runner import claim_job, finalize_if_still_running
...
_JOB_TYPE = "scaffold_tree"

@dataclass
class RunScaffoldTree:
    builder: BuildScaffoldNetwork
    repository: ScaffoldTreeJobRepository
    uow: UnitOfWork

    async def run(self, *, job_id: UUID, workspace_id: UUID, molecule_ids: list[UUID]) -> None:
        log = logger.bind(job_id=str(job_id), workspace_id=str(workspace_id))
        try:
            if not await claim_job(self.repository, self.uow, job_id=job_id, workspace_id=workspace_id, now=datetime.now(UTC), job_type=_JOB_TYPE):
                return
            tree = await self.builder.execute(
                BuildScaffoldNetworkInput(molecule_ids=molecule_ids, workspace_id=workspace_id)
            )
            async with self.uow:
                await finalize_if_still_running(
                    self.repository, self.uow, job_id=job_id, workspace_id=workspace_id,
                    apply_ready=lambda job: job.mark_ready(result=tree, now=datetime.now(UTC)),
                    job_type=_JOB_TYPE,
                )
            log.info("scaffold_tree_job_ready", node_count=tree.stats.node_count)
        except Exception:
            log.exception("scaffold_tree_job_failed")
            raise   # FAILED is recorded at the boundary, never in the runner
```

## Task 5 — Use cases
- `start_scaffold_tree_job.py`: the sync-path chained `ScaffoldTreeJob.create(...).mark_running(now).mark_ready(tree, now)` → statements: `job = ScaffoldTreeJob.create(...); job.mark_running(payload.now); job.mark_ready(result=tree, now=payload.now)`. (No find_by_id, no status-enum, no inline mark-failed — unchanged otherwise.)
- `get_scaffold_tree_job.py`: `find_by_id` → `find_by_id_in_workspace`.
- `cancel_scaffold_tree_job.py`: `find_by_id` → `find_by_id_in_workspace`; `InvalidScaffoldTreeJobTransition` → `InvalidJobTransition`; mutate `mark_cancelled` then `save(job)`; return `job`.

## Task 6 — Temporal (add the missing boundary handling)
- `activities/scaffold_tree.py`: add `mark_failed: MarkJobFailed` to `__init__`; add `@dataclass MarkScaffoldFailedInput(job_id, workspace_id, error)`; add `@activity.defn mark_scaffold_tree_job_failed` that calls `self._mark_failed.execute(MarkJobFailedInput(job_id=uuid.UUID(input.job_id), workspace_id=uuid.UUID(input.workspace_id), error=input.error, now=datetime.now(UTC)))`. Keep `RunScaffoldTreeInput` + `run_scaffold_tree`.
- `workflows/scaffold_tree.py`: body → `run_job_with_failure_marking(run_activity=ScaffoldTreeActivities.run_scaffold_tree, run_input=RunScaffoldTreeInput(...), mark_failed_activity=ScaffoldTreeActivities.mark_scaffold_tree_job_failed, mark_failed_input=MarkScaffoldFailedInput(job_id=input.job_id, workspace_id=input.workspace_id, error="scaffold tree build failed after retries"), run_timeout=timedelta(minutes=5))`. Import `MarkScaffoldFailedInput` in the unsafe block.
- `orchestrators/scaffold_tree.py`: `NullScaffoldTreeOrchestrator(NullJobOrchestrator)` — `__init__(self, runner, *, mark_failed: MarkJobFailed | None = None)` → `super().__init__(mark_failed=mark_failed, job_type="scaffold_tree")`; `schedule` → `self._spawn(lambda: self._runner.run(job_id=job_id, workspace_id=workspace_id, molecule_ids=molecule_ids), job_id=job_id, workspace_id=workspace_id)`; `cancel` no-op. Drop the `asyncio` import; Temporal orchestrator unchanged.

## Task 7 — DI + worker (wire MarkJobFailed + register the new activity)
- `_sar_analysis.py` `_null_orchestrator` → `NullScaffoldTreeOrchestrator(c[RunScaffoldTree], mark_failed=MarkJobFailed(repository=SQLAlchemyScaffoldTreeJobRepository(AsyncUnitOfWork(c[async_sessionmaker])), uow=<that same uow>, job_type="scaffold_tree"))`. (Build the fail UoW first, like the decomposition Null binding.)
- `worker.py`: `scaffold_tree_activities = ScaffoldTreeActivities(run_scaffold_tree, MarkJobFailed(repository=SQLAlchemyScaffoldTreeJobRepository(_scaffold_fail_uow), uow=_scaffold_fail_uow, job_type="scaffold_tree"))` (add `_scaffold_fail_uow = AsyncUnitOfWork(session_factory)` + the repo import is already present); and ADD `scaffold_tree_activities.mark_scaffold_tree_job_failed` to the `activities=[...]` list.

## Task 8 — Tests
**Mechanical (mirror Plan 2/3):**
- `tests/unit/domain/sar_analysis/test_scaffold_tree_job.py` — mutable API (`AsyncJobStatus`/`InvalidJobTransition`; `mark_ready(result=…, now=…)`; chains→statements).
- `tests/unit/application/sar_analysis/test_start_scaffold_tree_job.py` — sync-path chain → statements.
- `tests/unit/application/sar_analysis/test_get_and_cancel_scaffold_tree_job.py` — fake `find_by_id`→`find_by_id_in_workspace`; mutable; status enum.
- `tests/integration/persistence/sar_analysis/test_scaffold_tree_job_repository.py` — base save + `find_by_id_in_workspace` + chains→statements + (optimistic-concurrency split if present; capture `v_before`).

**Behavior-FIX tests (NEW — these prove the bugs are gone; the OLD run test asserted the buggy behavior and must be rewritten):**
- `tests/unit/application/sar_analysis/test_run_scaffold_tree.py` — rewrite: (a) RUNNING re-claim does NOT raise (idempotent retry); (b) a concurrent cancel mid-build is NOT clobbered to READY (stays CANCELLED); (c) on builder exception the runner RE-RAISES and leaves the job RUNNING (does NOT mark FAILED in-runner); (d) happy path reaches READY with the result.
- `tests/unit/infrastructure/temporal/test_scaffold_tree_orchestrators.py` — the Null orchestrator now records FAILED at the boundary: with a boom runner + a spy mark_failed, assert the spy is called with `job_id` (it was NOT before); construction `NullScaffoldTreeOrchestrator(runner, mark_failed=spy)`.

## Task 9 — Verification + review
- `uv run pytest tests/unit -q --deselect tests/unit/cascade/test_fk_coverage.py::test_every_fk_is_categorized` → green.
- `uv run pytest tests/integration/persistence/sar_analysis -q` → green (Docker).
- `uv run ruff check src/cellar/...touched...` + `uv run lint-imports`.
- Commit (explicit pathspec; never the WIP), then spec + code-quality review (focus: are all 5 bugs actually fixed, and is the new boundary wiring correct).

## Risks
- This is the FIRST migration that ADDS a Temporal activity + worker registration — double-check the new `mark_scaffold_tree_job_failed` activity is in the worker's `activities=[...]` (else the workflow's mark-failed step fails at runtime, though no unit test exercises a real worker).
- The Null orchestrator gains a `mark_failed` — DI + worker must both wire it; tests that construct `NullScaffoldTreeOrchestrator(runner)` without it still work (mark_failed optional) but won't record FAILED.
- grep `ScaffoldTreeJobStatus|InvalidScaffoldTreeJobTransition|\.mark_running(...).mark_` across src+tests before finishing.
