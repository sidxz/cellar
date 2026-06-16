# Generic `AsyncJob` mechanism — design spec

**Date:** 2026-06-16
**Branch:** `design-7`
**Status:** Approved design; ready for implementation planning (writing-plans next).
**Supersedes:** the frozen-base recommendation in
`docs/superpowers/specs/2026-06-16-sar-14-generic-asyncjob-handoff.md` — see
[Key Decision 2](#kd2). That handoff's goal and 5-job analysis still stand; only
its "build new frozen job-infrastructure" mechanism is replaced.

---

## Problem

Five async compute-job types each hand-reimplement the same lifecycle
(`pending → running → {ready|failed|cancelled}`):

| Job | Context |
|---|---|
| rgroup decomposition | sar_analysis |
| SAR activity-projection | sar_analysis |
| scaffold_tree | sar_analysis |
| umap | sar_analysis |
| export | export (deferred — see [Out of scope](#oos)) |

The lifecycle is copy-pasted across ~12 files per job (domain aggregate, repo,
runner, start/get/cancel/mark-failed use cases, Temporal orchestrator/workflow/
activity, DI + worker registration). Because nothing is shared, the recent
lifecycle-correctness fix landed in **only 2 of 5** jobs. The other three still
carry the same latent bugs the corrected pair had:

- **Blind / version-frozen `save()`** — no version-checked UPDATE, no
  `ConcurrencyConflictError`; `_apply_to_model` copies `model.version =
  job.version`, so the version column never advances and a concurrent cancel is
  silently clobbered.
- **FAILED marked inside the runner** — flips the row terminal-FAILED on the
  first attempt's exception, so a Temporal retry can never re-enter and recover.
- **Non-idempotent claim** — unconditional `mark_running`; a retry against a
  RUNNING (or already-FAILED) row raises `InvalidTransition` and crashes.
- **No re-read guard before the terminal transition** — reuses the stale
  in-memory aggregate, so a cancel landing mid-compute is overwritten to READY.
- **No `Mark*Failed` boundary use case** and no workflow `except ActivityError`
  handler.

### Root cause

The save-layer duplication and the blind-save bugs exist **because the SAR jobs
deviated from the codebase norm.** The dominant idiom is a mutable
`AggregateRoot` aggregate persisted through the shared
`SQLAlchemyRepository[T, ModelType]` base — used by **34 repositories** across
**36 `AggregateRoot` aggregates**. That base already implements the exact
version-checked optimistic-concurrency `save()` (workspace guard,
`ConcurrencyConflictError`, version sync on both model and aggregate).

The SAR jobs instead hand-rolled **frozen dataclasses** and, because the shared
base mutates `aggregate.version` (illegal on a frozen instance), hand-rolled
their own `save()` too. Two of those hand-rolled saves are the buggy blind ones.
Had the jobs been `AggregateRoot` + `SQLAlchemyRepository` like everything else,
they would have inherited the correct save and these bugs could not exist.

---

## Goal

Extract one shared async-job mechanism and migrate the 4 SAR-family jobs onto it
so a lifecycle fix lands **once, not 4×**. Migrating scaffold_tree + umap fixes
their bugs as a *consequence* of adopting the shared mechanism. The 2
already-correct jobs migrate with **zero behavior change** (their existing tests
are the regression gate). Tests stay green at every step.

---

## Scope

- **In:** the 4 SAR-family jobs (decomposition, activity-projection,
  scaffold_tree, umap).
- **Out:** export — structurally divergent; gets its own follow-up spec. See
  [Out of scope](#oos).

---

## Key decisions

### KD1 — Export deferred
Export is the structural outlier (mutable already, but blind save **plus**
in-domain version bumping, two extra states `EXPIRED` / `CANCEL_REQUESTED`, a
file/blob result with no child rows to reset, a TTL reaper, and a download
route). Build and prove the mechanism on the 4 jobs that fit; export migrates in
a separate spec.

<a id="kd2"></a>
### KD2 — Mutable `AggregateRoot` + reuse the existing `SQLAlchemyRepository` base
The `AsyncJob` base is a **mutable `AggregateRoot` subclass**, and every job repo
**extends the existing `SQLAlchemyRepository`** base. This:

- **Reuses the proven save** (no new optimistic-concurrency code; the 34-repo
  base *is* the shared save mechanism the handoff doc wanted to build).
- **Fixes the root cause** — scaffold/umap's blind-save + version-frozen bugs
  vanish by inheritance.
- **Unifies the codebase** on one aggregate idiom + one repo base (the frozen
  SAR jobs were the deviation).
- **Eases the later export migration** (export is already an `AggregateRoot`).

Cost: the 4 frozen SAR aggregates (including the 2 just-corrected) are rewritten
to mutable `AggregateRoot` subclasses; transitions become **mutate-self + save**
(the codebase norm, e.g. `ExportJob`, `Molecule`) instead of returning a new
`replace`d instance. Re-verified by the existing SAR test suite.

This **supersedes** the handoff doc's `@dataclass(frozen=True, kw_only=True)`
base + new frozen-compatible repo recommendation, which predated noticing the
existing base and would have built parallel infrastructure (reinvention) while
perpetuating two aggregate idioms.

### KD3 — Hybrid mechanism (inheritance where clean, composition where a template leaks)
- **Aggregate → inheritance.** The 9 common fields + `mark_running/failed/
  cancelled` are identical; `mark_ready` is a clean per-subclass override.
- **Repository → inheritance.** Variation is exactly the model class + the three
  mapping methods — natural overrides on the existing base.
- **Runner → composition.** Share only the lifecycle bits that diverged into
  bugs (claim, re-read-finalize); keep each `run()` body explicit. A rigid
  `_reset/_compute/_finalize` template leaks (streaming-per-batch jobs vs
  compute-once jobs don't share a hook shape).
- **Temporal → composition + thin per-job classes.** Temporal resists
  generualization (determinism, per-payload typing, per-workflow registration);
  share the `ActivityError → mark-failed → re-raise` helper and the Null
  orchestrator base, keep per-job `@workflow.defn` glue.

---

## Design

Five shared primitives, placed where the codebase already keeps shared code.

| Layer | Shared primitive | Location |
|---|---|---|
| Domain | `AsyncJobStatus`, `JOB_TERMINAL_STATES`, `InvalidJobTransition`, `AsyncJob(AggregateRoot)` | `domain/shared/async_job.py` (new) |
| Persistence | *(reuse)* `SQLAlchemyRepository[Job, JobModel]` | `…/sqlalchemy/base_repository.py` (existing) |
| Application | `JobRepository` protocol + generic `MarkJobFailed`; `AsyncJobRunner` base | `application/shared/mark_job_failed.py`, `application/shared/async_job_runner.py` (new) |
| Temporal | `run_job_with_failure_marking(...)`; `NullJobOrchestrator` base | `infrastructure/temporal/shared.py` (new) |

### Domain — `domain/shared/async_job.py`

```python
class AsyncJobStatus(StrEnum):
    PENDING = "pending"; RUNNING = "running"
    READY = "ready"; FAILED = "failed"; CANCELLED = "cancelled"

JOB_TERMINAL_STATES = frozenset({READY, FAILED, CANCELLED})

class InvalidJobTransition(DomainError): ...

class AsyncJob(AggregateRoot):
    # __init__ sets: workspace_id, requested_by, requested_at, status,
    #   started_at, completed_at, error_message (+ id/version/timestamps via super)
    def mark_running(self, now) -> None:       # guard PENDING
    def mark_failed(self, error, now) -> None:  # guard {PENDING, RUNNING}
    def mark_cancelled(self, now) -> None:      # guard not in JOB_TERMINAL_STATES
    def _enter_ready(self, now) -> None:        # guard RUNNING; set READY + completed_at
```

- The enum's string values **match all 4 jobs today**, so there is **no DB data
  migration** — only Python type references change.
- Transitions **mutate `self` and return `None`** (codebase norm). `version` is
  **not** touched by transitions — the repo's `save()` owns it.
- `mark_ready` is per-subclass: it calls `self._enter_ready(now)` then sets its
  own result fields.

Each job: `class ScaffoldTreeJob(AsyncJob)` adds its result/cache-key fields, a
`mark_ready(self, *, <result>, now)`, and a `create(...)` classmethod.

### Persistence — extend `SQLAlchemyRepository[Job, JobModel]`

Each job repo:
- sets `model_class`;
- implements `_to_domain`, `_to_model`, `_update_model` (largely a rename of
  today's `_to_model` / `_apply_to_model`, plus `_to_domain` which the read
  helpers already need);
- **inherits** `save()` (version-checked optimistic concurrency) and
  `find_by_id_in_workspace`;
- keeps per-job read/reset helpers as added methods: `find_cached`,
  `delete_assignments` / `delete_values`, `write_*`, `count_*`.

Deletes ~30–40 lines of hand-rolled `save()` per repo (×4). scaffold/umap's
blind-save + version-frozen bugs disappear by inheritance.

### Application — `MarkJobFailed` + `AsyncJobRunner`

**`JobRepository` protocol** (`application/shared/`): `find_by_id_in_workspace`
+ `save`.

**`MarkJobFailed`** — one class for all 4 (replaces the 2 existing per-job
`Mark*Failed`, supplies the 2 missing ones):
load → `mark_failed` (swallow `InvalidJobTransition` → idempotent no-op) →
save+commit (swallow `ConcurrencyConflictError` → a cancel won the race).

**`AsyncJobRunner`** base (composition — two protected helpers):
- `_claim(job_id, ws, now) -> bool` — load; PENDING → `mark_running`+save+commit
  → `True`; RUNNING → `True` (re-claim a crashed retry); terminal/missing →
  `False`.
- `_finalize_if_still_running(job_id, ws, apply_ready) -> None` — re-read; if not
  RUNNING → log + return; else `apply_ready(job)` (which calls
  `job.mark_ready(...)`) → save+commit.

Each job runner subclasses it and writes an explicit `run()` (claim → its own
compute → finalize). **On exception: re-raise, never mark FAILED in the runner.**
Deletes the in-runner `except: mark_failed` blocks (the headline bug) and the
duplicated claim/finalize from all 4.

### Temporal — `infrastructure/temporal/shared.py`

- `run_job_with_failure_marking(run_activity, run_payload, mark_failed_activity,
  fail_payload, *, timeout, retries)` — execute the run-activity under
  `RetryPolicy`; on `ActivityError` after exhaustion call the mark-failed
  activity; re-raise. Called from inside each thin `@workflow.defn`. This is
  exactly what scaffold/umap workflows are **missing** today.
- `NullJobOrchestrator` base — the fire-and-forget asyncio-task fallback that
  self-marks-failed on exception. Per-job Null orchestrators extend it (fixes
  scaffold's no-mark and umap's await-inline divergence).
- Per-job stays thin: `@workflow.defn` + payload dataclass + activity class +
  `worker.py` registration. New `mark_scaffold_tree_failed` /
  `mark_umap_failed` activities are registered.

### Per-job parameterization (the only genuinely job-specific parts)

1. `mark_ready`'s signature + result/header fields (`rgroup_labels`+counts /
   `value_count`+`channel_spec` / scaffold `result` / umap `result`).
2. Cache-key fields + `find_cached` predicate (`membership_hash` /
   `+channel_hash` / `+core_*` / `+picker_param_hash`).
3. Result storage + reset helper + the actual compute (child-row jobs use
   `delete_*`/`write_*`; header-only jobs store a `result_json` on the row).
4. Temporal workflow-id prefix, activity names, and **timeout/retry constants**
   (preserve each job's tuned values — decomposition 1h, scaffold 5m, umap 30m).

---

## Migration order (test-gated; commit per step, explicit pathspec)

1. **Build + unit-test the 5 primitives.** No job wired yet → all existing tests
   stay green.
2. **Migrate decomposition** (correct → *zero behavior change*) → SAR suite
   green. Proves the mechanism.
3. **Migrate activity-projection** (correct → zero behavior change) → green.
4. **Migrate scaffold_tree** (*fixes its 5 bugs*) → existing tests green **+ new
   lifecycle tests**.
5. **Migrate umap** (fixes its bugs) → green + new tests.

Stop at any green state if budget runs out; **never leave a half-migration.**

---

## Testing strategy

- **New unit tests:** `AsyncJob` transitions (guards + terminal); `MarkJobFailed`
  (idempotent no-op on already-terminal; swallows `ConcurrencyConflictError`);
  `AsyncJobRunner` helpers (claim returns by state; finalize skips when not
  RUNNING).
- **Regression gate (the 2 correct jobs):** existing tests pass **unchanged** —
  that is the proof the migration is behavior-preserving.
- **New behavior tests (scaffold/umap):** RUNNING→re-claim does not throw
  (idempotent retry); a concurrent cancel mid-compute is **not** clobbered to
  READY; failure is marked at the boundary, not in-runner; `version` increments
  on save.
- **Integration (persistence):** the base `save()` is already covered; add
  per-job `find_cached` / `delete_*` coverage.
- **Per-step verification:**
  `cd backend && uv run pytest tests/unit/{application,domain}/sar_analysis tests/unit/infrastructure/temporal tests/integration/persistence/sar_analysis -q`
  + `uv run ruff check src/cellar/...`. Frontend only if a response shape changes
  (it should not).

---

## Risks / known ripples

- **`find_by_id` → `find_by_id_in_workspace` rename.** The base exposes
  `find_by_id_in_workspace(workspace_id, id)`; SAR call sites currently call
  `find_by_id(id, *, workspace_id=…)`. Mechanical migration across runners + use
  cases (the base's `find_by_id` is the deprecated unscoped one — do not alias
  over it).
- **Rewriting the 2 correct jobs re-opens just-landed work.** Mitigated by the
  existing SAR suite as the regression gate and by doing them first (lowest risk,
  zero behavior change).
- **Base-repo assumptions.** `SQLAlchemyRepository.save()` calls
  `self._uow.track(aggregate)` and the UoW dispatches domain events on commit.
  Confirm the job `AsyncUnitOfWork` satisfies this (jobs emit no events → empty
  list → harmless, but verify the `track()` surface).
- **Don't homogenize Temporal constants.** Each job's timeout/retry values are
  tuned — preserve them per job; only the failure-handling *structure* is shared.
- **Enum unification churn.** Every `XxxStatus.READY` etc. across 4 repos, ~15
  use cases, routes, and tests collapses onto `AsyncJobStatus`. Largest source of
  diff; no data migration (string values match).

---

<a id="oos"></a>
## Out of scope — export (follow-up spec)

Export shares the orchestration skeleton but conflicts with the
persistence/failure contract on load-bearing axes, so it is **not** a drop-in:

- Mutable `AggregateRoot` already, **but** its transitions bump `version`
  in-domain (`self.version += 1`) paired with a **blind save** — the inverse of
  the shared contract.
- Two extra states — `EXPIRED` (TTL reap + blob delete via
  `PurgeExpiredExports`) and `CANCEL_REQUESTED` (two-phase cancel).
- Result is a stored **file** (`file_key`/`byte_size`/…), so there is no
  child-row reset step; idempotent re-run = overwrite the same object-store key.
- Owns a TTL reaper and a download route (`PrepareExportDownload`) with no SAR
  analogue.

Its migration = drop the in-domain version bumps, extend `SQLAlchemyRepository`,
delete the runner's inline `mark_failed`, add `MarkExportFailed` + a workflow
`except ActivityError` handler, and reconcile the two extra states with the
generic enum (likely an export-specific extension rather than folding them into
`AsyncJobStatus`). Tracked as its own spec.

---

## File inventory (for the implementation plan)

**New shared files**
- `domain/shared/async_job.py`
- `application/shared/async_job_runner.py`
- `application/shared/mark_job_failed.py` (+ `JobRepository` protocol — colocate
  or in an existing `application/shared` protocol module)
- `infrastructure/temporal/shared.py`

**Per job (×4), changed**
- domain aggregate → `class XxxJob(AsyncJob)`; drop the local status enum +
  `InvalidXxxTransition`; transitions mutate + return `None`.
- repo → `class …Repository(SQLAlchemyRepository[XxxJob, XxxModel])`; delete
  hand-rolled `save()`; implement the 3 mapping methods; keep read/reset helpers.
- runner → `class RunXxx(AsyncJobRunner)`; use `_claim` / `_finalize_if_still_
  running`; strip any in-runner FAILED handling to `log + raise`.
- use cases → `start/get/cancel` keep per-job shape but reference the shared
  enum + `find_by_id_in_workspace`; **delete** per-job `mark_*_failed.py`
  (replaced by generic `MarkJobFailed`).
- temporal → thin `@workflow.defn` calls `run_job_with_failure_marking`; Null
  orchestrator extends `NullJobOrchestrator`; register new `mark_*_failed`
  activities (scaffold + umap) in `worker.py`.
- DI (`_sar_analysis.py`) → wire `MarkJobFailed` + the shared runner base per
  job; same per-resolve-UoW pattern.

**Removed**
- 4× hand-rolled repo `save()`; 4× duplicated claim/finalize runner logic; 2×
  in-runner FAILED blocks (scaffold, umap); 2× per-job `Mark*Failed` use cases
  (folded into one generic); 4× per-job status enums + `InvalidXxxTransition`.
