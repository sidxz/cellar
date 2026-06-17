# SAR Activity-Projection Migration (Plan 3 of N)

> **Execution model:** CONTROLLER-DRIVEN, identical in shape to Plan 2 (R-group decomposition). This is the 2nd already-correct job → **zero behavior change**; the existing SAR suite + integration + API are the regression gate. The Temporal primitives (`run_job_with_failure_marking`, `NullJobOrchestrator`) already exist (Plan 2) — this plan only *consumes* them.

**Goal:** Migrate `SarActivityProjection` onto the shared AsyncJob mechanism, mirroring the decomposition migration (`11c4c24b`). The projection job is a line-for-line structural mirror of decomposition (its aggregate docstring even says "Mirrors RGroupDecompositionRun").

**Reference:** the decomposition migration plan `2026-06-16-asyncjob-02-decomposition-migration.md` and commit `11c4c24b` are the proven template. Primitives in `cellar.domain.shared.async_job`, `cellar.application.shared.{job_repository,async_job_runner,mark_job_failed}`, `cellar.infrastructure.temporal.{workflow_support,orchestrator_base}`.

**Run all commands from `backend/`.**

---

## Projection-specific deltas vs decomposition

| Aspect | decomposition | activity-projection |
|---|---|---|
| Cache key | `membership_hash` + `core_hash` | `membership_hash` + `channel_hash` |
| Header result fields | `rgroup_labels` + 3 counts | `value_count` + `channel_spec` |
| `mark_ready` sig | `(*, rgroup_labels, matched/unmatched/total_count, now)` | `(*, value_count, now)` |
| Child rows | `rgroup_assignments` (`write/delete_assignments`) | `sar_activity_values` (`write/delete_values`) |
| Compute | streaming decompose | `enrich_to_scalars` per batch |
| Workflow-id prefix | `rgroup-decomposition-{id}` | `sar-activity-projection-{id}` (unchanged) |
| Status string values | identical → **no DB migration** | identical → **no DB migration** |

The model (`sar_activity_projection_models.py`) has `WorkspaceIdMixin` + `VersionMixin`, no timestamp columns — same as decomposition; `_to_model`/`_to_domain` never reference `created_at`/`updated_at`.

---

## Task 1 — Domain aggregate

Replace the body of `domain/sar_analysis/sar_activity_projection.py` with a mutable `AsyncJob` subclass (drop the local `SarActivityProjectionStatus` enum, `InvalidSarProjectionTransition`, `_TERMINAL`, `@dataclass(frozen=True)`):

```python
"""SarActivityProjection — persisted async materialization of one activity scalar
per molecule for a color channel, over a member set.

Lifecycle (see ``AsyncJob``): pending -> running -> {ready | failed | cancelled};
pending -> cancelled. The aggregate holds only the *header* (channel spec + value
count). Per-molecule scalars are persisted as separate SPARSE rows (see the
repository). Keyed by (membership_hash, channel_hash); core-independent.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from cellar.domain.shared.async_job import AsyncJob, AsyncJobStatus


class SarActivityProjection(AsyncJob):
    def __init__(
        self,
        *,
        workspace_id: UUID,
        requested_by: UUID,
        membership_hash: str,
        channel_hash: str,
        channel_spec: dict[str, Any],
        requested_at: datetime,
        id: UUID | None = None,
        status: AsyncJobStatus = AsyncJobStatus.PENDING,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
        value_count: int = 0,
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
        self.channel_hash = channel_hash
        self.channel_spec = dict(channel_spec)
        self.value_count = value_count

    @classmethod
    def create(
        cls,
        *,
        workspace_id: UUID,
        requested_by: UUID,
        membership_hash: str,
        channel_hash: str,
        channel_spec: dict[str, Any],
        now: datetime,
    ) -> SarActivityProjection:
        return cls(
            workspace_id=workspace_id,
            requested_by=requested_by,
            membership_hash=membership_hash,
            channel_hash=channel_hash,
            channel_spec=channel_spec,
            requested_at=now,
        )

    def mark_ready(self, *, value_count: int, now: datetime) -> None:
        self._enter_ready(now)
        self.value_count = value_count
```

## Task 2 — Repository (extend the base)

Rewrite `…/sqlalchemy/sar_analysis/sar_activity_projection_repository.py` to extend `SQLAlchemyRepository[SarActivityProjection, SarActivityProjectionModel]`:

```python
"""SQLAlchemy implementation of SarActivityProjectionRepository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, insert, select

from cellar.domain.sar_analysis.activity_projection_types import ActivityScalar
from cellar.domain.sar_analysis.sar_activity_projection import SarActivityProjection
from cellar.domain.shared.async_job import AsyncJobStatus
from cellar.infrastructure.persistence.sqlalchemy.base_repository import SQLAlchemyRepository
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_models import (  # noqa: E501
    SarActivityProjectionModel,
    SarActivityValueModel,
)


class SQLAlchemySarActivityProjectionRepository(
    SQLAlchemyRepository[SarActivityProjection, SarActivityProjectionModel]
):
    model_class = SarActivityProjectionModel

    def _to_domain(self, model: SarActivityProjectionModel) -> SarActivityProjection:
        return SarActivityProjection(
            id=model.id,
            workspace_id=model.workspace_id,
            requested_by=model.requested_by,
            membership_hash=model.membership_hash,
            channel_hash=model.channel_hash,
            channel_spec=dict(model.channel_spec or {}),
            requested_at=model.requested_at,
            status=AsyncJobStatus(model.status),
            started_at=model.started_at,
            completed_at=model.completed_at,
            error_message=model.error_message,
            value_count=model.value_count,
            version=model.version,
        )

    def _to_model(self, aggregate: SarActivityProjection) -> SarActivityProjectionModel:
        return SarActivityProjectionModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            requested_by=aggregate.requested_by,
            membership_hash=aggregate.membership_hash,
            channel_hash=aggregate.channel_hash,
            channel_spec=dict(aggregate.channel_spec),
            requested_at=aggregate.requested_at,
            status=aggregate.status.value,
            started_at=aggregate.started_at,
            completed_at=aggregate.completed_at,
            error_message=aggregate.error_message,
            value_count=aggregate.value_count,
            version=aggregate.version,
        )

    def _update_model(
        self, model: SarActivityProjectionModel, aggregate: SarActivityProjection
    ) -> None:
        # version is owned by the base save()'s optimistic-concurrency UPDATE.
        model.status = aggregate.status.value
        model.started_at = aggregate.started_at
        model.completed_at = aggregate.completed_at
        model.error_message = aggregate.error_message
        model.value_count = aggregate.value_count

    async def find_cached(
        self, *, workspace_id: UUID, membership_hash: str, channel_hash: str
    ) -> SarActivityProjection | None:
        stmt = (
            select(SarActivityProjectionModel)
            .where(
                SarActivityProjectionModel.workspace_id == workspace_id,
                SarActivityProjectionModel.membership_hash == membership_hash,
                SarActivityProjectionModel.channel_hash == channel_hash,
                SarActivityProjectionModel.status == AsyncJobStatus.READY.value,
            )
            .order_by(SarActivityProjectionModel.completed_at.desc())
            .limit(1)
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def write_values(self, projection_id: UUID, values: list[ActivityScalar]) -> None:
        batch = 1000
        rows = [
            {
                "projection_id": projection_id,
                "molecule_id": v.molecule_id,
                "scalar": v.scalar,
                "unit": v.unit,
                "qualifier": v.qualifier,
                "source": v.source,
                "snapshot": v.snapshot,
            }
            for v in values
        ]
        for i in range(0, len(rows), batch):
            await self._session.execute(insert(SarActivityValueModel), rows[i : i + batch])

    async def delete_values(self, projection_id: UUID) -> None:
        """Reset value rows before recompute, so a retry is idempotent and never
        collides on the (projection_id, molecule_id) PK."""
        await self._session.execute(
            sa_delete(SarActivityValueModel).where(
                SarActivityValueModel.projection_id == projection_id
            )
        )

    async def count_values(self, projection_id: UUID, *, workspace_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(SarActivityValueModel)
            .join(
                SarActivityProjectionModel,
                SarActivityProjectionModel.id == SarActivityValueModel.projection_id,
            )
            .where(
                SarActivityValueModel.projection_id == projection_id,
                SarActivityProjectionModel.workspace_id == workspace_id,
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())
```

## Task 3 — Protocol

`application/sar_analysis/repositories.py`: in `SarActivityProjectionRepository`, `find_by_id(projection_id, *, workspace_id)` → `find_by_id_in_workspace(workspace_id, id)`.

## Task 4 — Runner

`run_activity_projection.py` → mirror `run_decomposition.py`: use `claim_job` + `finalize_if_still_running` (apply_ready = `lambda proj: proj.mark_ready(value_count=total, now=…)`), drop trailing `uow.commit()`, drop the `SarActivityProjectionStatus` import, keep the enrich loop. `job_type="sar_activity_projection"`. Re-raise on exception (no in-runner FAILED).

## Task 5 — Use cases

- `start_activity_projection.py`: mutable `mark_running`/`mark_ready`; `find_by_id` → `find_by_id_in_workspace`; `MarkActivityProjectionFailed`/`Input` → generic `MarkJobFailed`/`MarkJobFailedInput(job_id=…, job_type="sar_activity_projection")`; `SarActivityProjectionStatus` → `AsyncJobStatus`. Restructure the initial save (`if is_inline: proj.mark_running(now)` then `save(proj)`) and the inline finalize (mutate `current` then `save(current)`).
- `get_activity_projection.py`: `find_by_id` → `find_by_id_in_workspace`.
- `cancel_activity_projection.py`: `find_by_id` → `find_by_id_in_workspace`; `InvalidSarProjectionTransition` → `InvalidJobTransition`; mutate `mark_cancelled` then `save`.

## Task 6 — Delete per-job mark-failed

`git rm backend/src/cellar/application/sar_analysis/mark_activity_projection_failed.py` → generic `MarkJobFailed`.

## Task 7 — Temporal glue

- `activities/sar_activity_projection.py`: `MarkActivityProjectionFailed`/`Input` → `MarkJobFailed`/`MarkJobFailedInput(job_id=uuid.UUID(input.projection_id), …)`.
- `workflows/sar_activity_projection.py`: body → `run_job_with_failure_marking(run_activity=…run_sar_activity_projection, mark_failed_activity=…mark_sar_activity_projection_failed, run_timeout=timedelta(hours=1), …)` (preserve the 1h timeout + the workflow input/payload dataclasses).
- `orchestrators/sar_activity_projection.py`: `NullSarActivityProjectionOrchestrator(NullJobOrchestrator)` with `super().__init__(mark_failed=mark_failed, job_type="sar_activity_projection")` and `schedule` calling `self._spawn(lambda: self._runner.run(run_id=projection_id, workspace_id=…, channel_spec=…, collection_id=…, molecule_ids=…), job_id=projection_id, workspace_id=…)`; drop asyncio/datetime/MarkActivityProjectionFailed imports; Temporal orchestrator unchanged.

## Task 8 — DI + worker

- `infrastructure/di/_sar_analysis.py` (activity-projection slice): `MarkActivityProjectionFailed` import → already have `MarkJobFailed`; in the Null orchestrator binding use `MarkJobFailed(repository=SQLAlchemySarActivityProjectionRepository(fail_uow), uow=fail_uow, job_type="sar_activity_projection")`. Drop the now-unused `MarkActivityProjectionFailed` import (verify nothing else uses it).
- `infrastructure/temporal/worker.py`: the `SarActivityProjectionActivities(...)` wiring → `MarkJobFailed(repository=…, uow=_proj_fail_uow, job_type="sar_activity_projection")`; drop the `MarkActivityProjectionFailed` import.

## Task 9 — Consumers (projection `find_by_id` ripple)

Flip the **projection** repo calls (the run-repo calls already flipped in Plan 2; leave any scaffold/umap):
- `activity_heatmap.py:111` `self._projections.find_by_id(payload.projection_id, workspace_id=…)` → `find_by_id_in_workspace(payload.workspace_id, payload.projection_id)`.
- `decomposition_rows.py:133` `self._projections.find_by_id(…)` → `find_by_id_in_workspace(…)`.
- `save_decomposition_collection.py:77` `self._projections.find_by_id(…)` → `find_by_id_in_workspace(…)`.
- Route `interface/routes/sar_analysis.py`: `SarActivityProjectionStatus` → `AsyncJobStatus` (import + usages). (`AsyncJobStatus` is already imported there from Plan 2.)

## Task 10 — Tests

- `tests/unit/domain/sar_analysis/test_sar_activity_projection.py` → mutable API (AsyncJobStatus / InvalidJobTransition; chained transitions → statements).
- `test_run_activity_projection.py`: FakeRepo `find_by_id` → `find_by_id_in_workspace`; mutable transitions; `SarActivityProjectionStatus` → `AsyncJobStatus`.
- `test_get_cancel_activity_projection.py`: same.
- start test (if present): same.
- `tests/unit/application/sar_analysis/test_mark_job_failed.py` — now projection-only after Plan 2; the projection half migrates to the generic `MarkJobFailed` (covered by `tests/unit/application/shared/test_mark_job_failed.py`), so **`git rm`** this file.
- `tests/unit/infrastructure/temporal/test_sar_activity_projection_orchestrators.py`: `spy.calls[0].run_id`/`projection_id` → `.job_id`; Null orchestrator construction unchanged.
- **Projection-fixture rebuilds in shared tests** (chained `.create().mark_running().mark_ready(value_count=…)` → statements; projection `find_by_id` fakes → `find_by_id_in_workspace`): `test_fetch_activity_heatmap.py`, `test_decomposition_rows.py`, `test_save_decomposition_collection.py` (proj fake) — and the integration/api: `test_activity_heatmap_reader.py`, `test_decomposition_rows_explain.py`, `test_decomposition_row_reader.py`, `test_sar_activity_projection_routes.py`, `test_sar_activity_projection_repository.py`.

(Use a comprehensive grep — `SarActivityProjectionStatus`, `InvalidSarProjectionTransition`, `mark_activity_projection_failed`, `MarkActivityProjectionFailed`, and `SarActivityProjection ... .mark_running(...).mark_` chains — to catch every site, as in Plan 2.)

## Task 11 — Verification gate

- `uv run pytest tests/unit -q --deselect tests/unit/cascade/test_fk_coverage.py::test_every_fk_is_categorized` → green (the FK test is pre-existing — backlog #5).
- `uv run pytest tests/integration/persistence/sar_analysis tests/api/test_sar_activity_projection_routes.py -q` → green (Docker).
- `uv run ruff check src/cellar/...touched...` + `uv run lint-imports` → clean.
- Commit (explicit pathspec — never the `run-dr-results.tsx` WIP), then spec + code-quality review of the diff.

## Risks
- The heatmap/rows readers hold BOTH a run repo (migrated) and a projection repo (migrating now) — only flip the projection calls; the run calls already flipped.
- `MarkActivityProjectionFailed` is referenced in worker + DI + start + orchestrator + activities — replace ALL, then delete the use case; grep to confirm zero refs before `git rm`.
- After deleting the sar `test_mark_job_failed.py`, confirm the generic shared test still covers the behavior.
