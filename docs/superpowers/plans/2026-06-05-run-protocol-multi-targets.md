# Multi-Target Links for Runs & Protocols — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let every Run link one-or-more biological targets (independent set) and every Protocol link one-or-more targets, where a protocol's effective targets = its direct additions ∪ the union of its runs' targets (computed read-time → roll-up on add, auto-prune of orphans on remove).

**Architecture:** Two pure M2M association tables (`run_targets`, `protocol_targets`) mirroring the existing `protocol_projects` convention — managed in the repository/application layer, not on the domain aggregates. The protocol's inherited targets are computed via a union query, so no write ever crosses an aggregate boundary. The scalar `protocols.target_id` is migrated into `protocol_targets` (as direct) and dropped.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy 2.0 async / Alembic / Lagom DI / returns Railway; Next.js 16 / React 19 / TanStack Query / shadcn.

**Spec:** `docs/superpowers/specs/2026-06-05-run-protocol-multi-targets-design.md`

**Layer order (per CLAUDE.md):** Domain → Persistence → Integration tests → Application → API → API tests → UI → E2E. Commit after each task.

---

## Reference patterns (read before starting)

- M2M repo methods: `protocol_repository.py:131-250` (`add_to_project`, `remove_from_project`, `find_project_ids`) — idempotent `pg_insert(...).on_conflict_do_nothing()`, defense-in-depth workspace checks.
- M2M endpoints: `protocols.py:928-973` (`POST/DELETE /protocols/{id}/projects/{id}`), 204 responses.
- M2M command/use-cases + DI: `manage_protocol.py` (`AddProtocolToProjectCommand`, `RemoveProtocolFromProjectCommand`), `cellar/interface/dependencies.py` (`AddProtocolToProjectDep`), and the Lagom container.
- Migration template: `backend/alembic/versions/050_tagging_expansion.py` (assoc-table creation), `001_001_initial_schema.py` (`protocol_projects`).
- Target reference entity: `target.py`, `TargetModel` (`models.py:65-80`), `target_repository.py`, `targets.py` routes.
- FE single-select to replace: `create-protocol-dialog.tsx:477-485` (`SearchableSelect` + `useTargets()`).
- FE grids: `protocol-list.tsx` (138 lines), `run-list.tsx`. Detail: `run-detail.tsx`, design tab `design-tab.tsx`.

---

## Phase 1 — Domain & data model

### Task 1: Association tables in the SQLAlchemy models

**Files:** Modify `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/models.py`

- [ ] **Step 1:** After the `protocol_projects` table (`:42-57`), add two pure association tables:

```python
protocol_targets = Table(
    "protocol_targets",
    Base.metadata,
    Column(
        "protocol_id",
        Uuid(as_uuid=True),
        ForeignKey("protocols.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "target_id",
        Uuid(as_uuid=True),
        ForeignKey("targets.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Index("ix_protocol_targets_target", "target_id"),
)

run_targets = Table(
    "run_targets",
    Base.metadata,
    Column(
        "run_id",
        Uuid(as_uuid=True),
        ForeignKey("runs.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "target_id",
        Uuid(as_uuid=True),
        ForeignKey("targets.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Index("ix_run_targets_target", "target_id"),
)
```

- [ ] **Step 2:** Remove the scalar column `target_id` from `ProtocolModel` (`:110`).
- [ ] **Step 3:** Commit: `models(screening): add protocol_targets + run_targets, drop ProtocolModel.target_id`.

### Task 2: Alembic migration `051_protocol_run_targets_m2m`

**Files:** Create `backend/alembic/versions/051_protocol_run_targets_m2m.py`

- [ ] **Step 1:** Write the migration (down_revision `"050_tagging_expansion"`):

```python
"""protocol/run multi-target M2M

Revision ID: 051_protocol_run_targets_m2m
Revises: 050_tagging_expansion
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "051_protocol_run_targets_m2m"
down_revision = "050_tagging_expansion"
branch_labels = None
depends_on = None


def _link_table(name: str, owner_col: str, owner_table: str) -> None:
    op.create_table(
        name,
        sa.Column(
            owner_col, sa.Uuid(),
            sa.ForeignKey(f"{owner_table}.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column(
            "target_id", sa.Uuid(),
            sa.ForeignKey("targets.id", ondelete="CASCADE"), primary_key=True,
        ),
    )
    op.create_index(f"ix_{name}_target", name, ["target_id"])


def upgrade() -> None:
    _link_table("protocol_targets", "protocol_id", "protocols")
    _link_table("run_targets", "run_id", "runs")
    # Backfill: existing single target_id becomes a DIRECT protocol target.
    op.execute(
        "INSERT INTO protocol_targets (protocol_id, target_id) "
        "SELECT id, target_id FROM protocols WHERE target_id IS NOT NULL"
    )
    op.drop_column("protocols", "target_id")


def downgrade() -> None:
    op.add_column(
        "protocols",
        sa.Column("target_id", sa.Uuid(), sa.ForeignKey("targets.id"), nullable=True),
    )
    # Lossy restore: only single-direct-target protocols round-trip.
    op.execute(
        "UPDATE protocols p SET target_id = sub.target_id FROM ("
        "  SELECT protocol_id, MIN(target_id::text)::uuid AS target_id "
        "  FROM protocol_targets GROUP BY protocol_id HAVING COUNT(*) = 1"
        ") sub WHERE p.id = sub.protocol_id"
    )
    op.drop_table("run_targets")
    op.drop_table("protocol_targets")
```

- [ ] **Step 2:** Run `cd backend && uv run alembic upgrade head`. Expected: applies `051`, no error.
- [ ] **Step 3:** Run `uv run alembic downgrade -1 && uv run alembic upgrade head` to verify round-trip.
- [ ] **Step 4:** Commit: `migration(051): protocol/run target M2M tables + backfill`.

### Task 3: Drop `target_id` from the Protocol domain aggregate

**Files:** Modify `backend/src/cellar/domain/screening_assay/protocol.py`, `protocol_versioning_service.py`

- [ ] **Step 1:** Remove `target_id` param + assignment from `Protocol.__init__` (`:309`, `:339`), `Protocol.create` (`:431`, `:446`), and the `update` method (`:510`, `:527-528`).
- [ ] **Step 2:** In `protocol_versioning_service.py:88`, remove `target_id=parent.target_id` from the constructor call (direct targets are copied at the repo/application layer in Task 9).
- [ ] **Step 3:** Run `cd backend && uv run pytest tests/unit/screening_assay/ -q -k protocol` and fix any references in those tests (remove `target_id=` kwargs).
- [ ] **Step 4:** Commit: `domain(protocol): drop scalar target_id (moving to M2M)`.

---

## Phase 2 — Persistence + integration tests

### Task 4: Protocol repository target methods

**Files:** Modify `protocol_repository.py`; import `protocol_targets`, `run_targets`, `TargetModel`, `RunModel`.

- [ ] **Step 1:** Remove the scalar `target_id` from `_to_domain` (`:335`), `_to_model` (`:394`), `_update_model` (`:427`).
- [ ] **Step 2:** Add a small DTO + methods (mirror `add_to_project`/`remove_from_project`):

```python
# at module top
from dataclasses import dataclass

@dataclass(frozen=True)
class EffectiveTarget:
    id: uuid.UUID
    name: str
    target_type: str
    is_direct: bool
    run_count: int
```

```python
async def add_direct_target(
    self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, target_id: uuid.UUID
) -> None:
    """Link a direct target to a protocol (idempotent, workspace-checked)."""
    if not await self._owns(ProtocolModel, protocol_id, workspace_id):
        return
    if not await self._owns(TargetModel, target_id, workspace_id):
        return
    await self._session.execute(
        pg_insert(protocol_targets)
        .values(protocol_id=protocol_id, target_id=target_id)
        .on_conflict_do_nothing()
    )

async def remove_direct_target(
    self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, target_id: uuid.UUID
) -> None:
    await self._session.execute(
        protocol_targets.delete().where(
            protocol_targets.c.protocol_id == protocol_id,
            protocol_targets.c.target_id == target_id,
            protocol_targets.c.protocol_id.in_(
                select(ProtocolModel.id).where(ProtocolModel.workspace_id == workspace_id)
            ),
        )
    )

async def _owns(self, model, id_: uuid.UUID, workspace_id: uuid.UUID) -> bool:
    r = await self._session.execute(
        select(model.id).where(model.id == id_, model.workspace_id == workspace_id)
    )
    return r.scalar_one_or_none() is not None
```

- [ ] **Step 3:** Add the effective-targets query for a single protocol (direct ∪ run union, with provenance + run_count):

```python
async def find_effective_targets(
    self, workspace_id: uuid.UUID, protocol_id: uuid.UUID
) -> list[EffectiveTarget]:
    direct_rows = await self._session.execute(
        select(protocol_targets.c.target_id).where(
            protocol_targets.c.protocol_id == protocol_id
        )
    )
    direct_ids = set(direct_rows.scalars().all())

    run_count_rows = await self._session.execute(
        select(run_targets.c.target_id, func.count(run_targets.c.run_id))
        .select_from(run_targets.join(RunModel, run_targets.c.run_id == RunModel.id))
        .where(RunModel.protocol_id == protocol_id)
        .group_by(run_targets.c.target_id)
    )
    run_counts = {tid: n for tid, n in run_count_rows.all()}

    all_ids = direct_ids | set(run_counts)
    if not all_ids:
        return []
    targets = await self._session.execute(
        select(TargetModel).where(
            TargetModel.workspace_id == workspace_id, TargetModel.id.in_(all_ids)
        )
    )
    out = [
        EffectiveTarget(
            id=t.id, name=t.name, target_type=t.target_type,
            is_direct=t.id in direct_ids, run_count=run_counts.get(t.id, 0),
        )
        for t in targets.scalars().all()
    ]
    out.sort(key=lambda e: e.name.lower())
    return out
```

(Add `from sqlalchemy import func` import.)

- [ ] **Step 4:** Add a batched variant for the summary list (avoid N+1): `find_effective_targets_for_protocols(workspace_id, protocol_ids) -> dict[uuid.UUID, list[tuple[id, name]]]` — three queries (direct rows, run-union rows joined on `RunModel.protocol_id IN ids`, target id→name map), union in Python.
- [ ] **Step 5:** Commit: `repo(protocol): direct-target M2M + effective-targets union queries`.

### Task 5: Run repository target methods

**Files:** Modify `run_repository.py`

- [ ] **Step 1:** Add `add_target`, `remove_target` (mirror Task 4 step 2 against `run_targets` + `RunModel`/`TargetModel`), and:

```python
async def find_target_ids(self, run_id: uuid.UUID) -> list[uuid.UUID]:
    r = await self._session.execute(
        select(run_targets.c.target_id).where(run_targets.c.run_id == run_id)
    )
    return list(r.scalars().all())

async def find_target_refs(
    self, workspace_id: uuid.UUID, run_id: uuid.UUID
) -> list[tuple[uuid.UUID, str, str]]:
    r = await self._session.execute(
        select(TargetModel.id, TargetModel.name, TargetModel.target_type)
        .select_from(run_targets.join(TargetModel, run_targets.c.target_id == TargetModel.id))
        .where(run_targets.c.run_id == run_id, TargetModel.workspace_id == workspace_id)
        .order_by(TargetModel.name)
    )
    return [(i, n, tt) for i, n, tt in r.all()]
```

- [ ] **Step 2:** Add `find_target_refs_for_runs(workspace_id, run_ids)` batched variant for the run list grid.
- [ ] **Step 3:** Commit: `repo(run): target M2M methods + batched refs`.

### Task 6: Integration tests — union & auto-prune

**Files:** Create `backend/tests/integration/screening_assay/test_target_links.py`

- [ ] **Step 1:** Write tests (use existing integration fixtures — a session + workspace + a protocol + targets). Assert:
  - add target T1 to run A, T2 to run B (both runs of protocol P) → `find_effective_targets(P)` returns {T1,T2}, both `is_direct=False`, `run_count=1`.
  - add direct target T3 to P → effective {T1,T2,T3}; T3 `is_direct=True`.
  - remove T1 from run A (only run with T1) → effective drops T1 (auto-prune).
  - remove all runs' T3 references never existed; T3 (direct) stays.
  - delete target T2 (via target repo / session) → cascade removes its `run_targets` rows; effective no longer lists T2.
- [ ] **Step 2:** Run `cd backend && uv run pytest tests/integration/screening_assay/test_target_links.py -q`. Expected: PASS.
- [ ] **Step 3:** Commit: `test(integration): target union + auto-prune + cascade`.

---

## Phase 3 — Application layer

### Task 7: Protocol use cases

**Files:** Modify `create_protocol.py`, `manage_protocol.py`, `list_protocol_summaries.py`, `get_protocol.py` (or wherever the protocol query enriches), `get_molecule_activity_detail.py`, `close_campaign.py`. Create `manage_protocol_targets.py` if cleaner.

- [ ] **Step 1:** `CreateProtocolCommand`: replace `target_id` with `target_ids: list[uuid.UUID] = field(default_factory=list)`; in the use case, after `repo.save(protocol)`, loop `await repo.add_direct_target(ws, protocol.id, tid)`.
- [ ] **Step 2:** `manage_protocol.py`: drop `target_id` from `UpdateProtocolCommand` + its application. Add `AddProtocolTargetCommand` / `RemoveProtocolTargetCommand` (mirror `AddProtocolToProjectCommand`) calling `repo.add_direct_target` / `repo.remove_direct_target`. Guard: load protocol, reject if `is_locked` or `status == RETIRED` (use the same error style as existing guards).
- [ ] **Step 3:** `list_protocol_summaries.py`: replace the single `target_name` enrichment (`:93-94`) — call `repo.find_effective_targets_for_protocols(...)`, set a new `targets: list[TargetRefDTO]` on the summary DTO (drop `target_id`/`target_name`).
- [ ] **Step 4:** The single-protocol read path (`GetProtocolQuery` handler / wherever `ProtocolResponse` is built) must expose effective targets — add an enrichment that calls `repo.find_effective_targets`. (Carry it through as a separate return alongside the aggregate, like `project_ids` are surfaced.)
- [ ] **Step 5:** `get_molecule_activity_detail.py:227`: replace `target_id=proto.target_id` with `targets=[...]` via `repo.find_effective_targets` (or names only).
- [ ] **Step 6:** `close_campaign.py:173`: serialize effective target names instead of scalar `target_id`.
- [ ] **Step 7:** Run `cd backend && uv run pytest tests/unit -q -k "protocol or campaign or activity"`; fix references.
- [ ] **Step 8:** Commit: `app(protocol): target_ids on create, direct-target commands, effective-target enrichment`.

### Task 8: Run use cases

**Files:** Modify `create_run.py`, create `manage_run_targets.py` (or add to an existing run management module)

- [ ] **Step 1:** `CreateRunCommand`: add `target_ids: list[uuid.UUID] = field(default_factory=list)`; after `repo.save(run)`, loop `await run_repo.add_target(ws, run.id, tid)`.
- [ ] **Step 2:** Add `AddRunTargetCommand` / `RemoveRunTargetCommand` use cases → `run_repo.add_target` / `remove_target`. Guard: load run, reject if `is_locked`.
- [ ] **Step 3:** Run `cd backend && uv run pytest tests/unit -q -k run`; fix references.
- [ ] **Step 4:** Commit: `app(run): target_ids on create + add/remove run-target commands`.

### Task 9: Versioning copies direct targets

**Files:** Modify the version-protocol use case (`manage_protocol.py` `VersionProtocolCommand` handler) / `protocol_versioning_service` caller

- [ ] **Step 1:** After the new version is saved, copy parent direct targets: `for tid in await repo.find_direct_target_ids(ws, parent_id): await repo.add_direct_target(ws, new_id, tid)`. (Add `find_direct_target_ids` to the repo if not already.)
- [ ] **Step 2:** Test: versioning a protocol with 2 direct targets → new version has the same 2 direct targets; inherited ones are NOT copied.
- [ ] **Step 3:** Commit: `app(protocol): carry direct targets to new version`.

---

## Phase 4 — API + API tests

### Task 10: Protocol routes + DI

**Files:** Modify `protocols.py`, `cellar/interface/dependencies.py`, the Lagom container module.

- [ ] **Step 1:** Define `TargetRefResponse` (`id, name, target_type`) and `ProtocolTargetRefResponse` (`id, name, target_type, is_direct, run_count`). Replace `ProtocolResponse.target_id` (`:132`) with `targets: list[ProtocolTargetRefResponse] = []`; thread an optional `targets=` kwarg through `from_domain` (like `project_ids`). Replace `ProtocolSummaryResponse.target_id`/`target_name` (`:356-357`) with `targets: list[TargetRefResponse] = []`.
- [ ] **Step 2:** `CreateProtocolRequest.target_id` → `target_ids: list[uuid.UUID] = []`; pass to command. Remove `target_id` from `UpdateProtocolRequest` + its handler block (`:565`, `:590`).
- [ ] **Step 3:** Add endpoints mirroring the projects ones (`:928-973`):
  `POST /protocols/{protocol_id}/targets/{target_id}` (204) and `DELETE /protocols/{protocol_id}/targets/{target_id}` (204), wired to the new deps.
- [ ] **Step 4:** Thread effective targets into the `get_protocol`, `list_protocols`, and `list_protocol_summaries` responses (the enrichment from Task 7).
- [ ] **Step 5:** Add DI deps (`AddProtocolTargetDep`, `RemoveProtocolTargetDep`) in `dependencies.py` + register the use cases in the container (mirror `AddProtocolToProjectDep`).
- [ ] **Step 6:** Commit: `api(protocol): targets in responses, create target_ids, add/remove target endpoints`.

### Task 11: Run routes + DI

**Files:** Modify `runs.py`, `dependencies.py`, container.

- [ ] **Step 1:** Add `targets: list[TargetRefResponse] = []` to `RunResponse`; populate from `run_repo.find_target_refs` (single) / `find_target_refs_for_runs` (list).
- [ ] **Step 2:** `CreateRunRequest`: add `target_ids: list[uuid.UUID] = []`; pass to command.
- [ ] **Step 3:** Add `POST/DELETE /runs/{run_id}/targets/{target_id}` (204) wired to new deps.
- [ ] **Step 4:** DI deps + container registration for run-target use cases.
- [ ] **Step 5:** Commit: `api(run): targets in response, create target_ids, add/remove target endpoints`.

### Task 12: API tests

**Files:** Create `backend/tests/api/test_protocol_targets.py`, `backend/tests/api/test_run_targets.py`

- [ ] **Step 1:** Protocol: create with `target_ids` → response `targets` shows them `is_direct=True`; POST a run target via run endpoint → protocol GET shows it `is_direct=False, run_count=1`; DELETE the last run's target → pruned; DELETE a direct target → gone.
- [ ] **Step 2:** Run: create with `target_ids`; add/remove endpoints; locked run rejects add (409/conflict).
- [ ] **Step 3:** Run `cd backend && uv run pytest tests/api/test_protocol_targets.py tests/api/test_run_targets.py -q`. Expected: PASS.
- [ ] **Step 4:** Commit: `test(api): protocol + run target endpoints`.

### Task 13: Regenerate OpenAPI types (orval)

- [ ] **Step 1:** With backend up on :8000, run `cd frontend && pnpm generate:api`. Review the `model/` diff (additive: `TargetRefResponse`, etc.).
- [ ] **Step 2:** Commit: `chore(api): regen orval model for target refs`.

---

## Phase 5 — Frontend

### Task 14: Types + hooks

**Files:** Modify `frontend/src/features/screening-assay/types/index.ts`, `hooks/use-protocols.ts`, create `hooks/use-protocol-targets.ts` + `hooks/use-run-targets.ts`.

- [ ] **Step 1:** Add `TargetRef = { id: string; name: string; target_type: string }` and `ProtocolTargetRef = TargetRef & { is_direct: boolean; run_count: number }` (alias generated orval types where available, per CLAUDE.md). Replace `Protocol.target_id` with `targets: ProtocolTargetRef[]`; `ProtocolSummary.target_id`/`target_name` → `targets: TargetRef[]`; add `Run.targets: TargetRef[]`.
- [ ] **Step 2:** Write hand-written mutation hooks (`customInstance` convention) for add/remove protocol target + run target, invalidating the relevant query keys (`["protocols"]`, `["protocol", id]`, `["runs"]`, `["run", id]`).
- [ ] **Step 3:** Update `CreateProtocolInput`/`CreateRunInput` to carry `target_ids?: string[]`.
- [ ] **Step 4:** Commit: `fe(types): multi-target refs + target mutation hooks`.

### Task 15: Shared presentational components

**Files:** Create `components/target-chips.tsx`, `components/target-multi-select.tsx`.

- [ ] **Step 1:** `TargetChips({ targets, max=3 })` — renders `Badge` per target, collapses overflow to `+N` (used by both grids + detail cards).
- [ ] **Step 2:** `TargetMultiSelect` — built on `SearchableSelect` (`src/shared/components/searchable-select.tsx`): multi-select of targets from `useTargets()`, selected shown as removable chips, plus an inline "Create target…" affordance (opens `CreateTargetDialog`). Props: `value: string[]`, `onChange`, `disabled`. No UUID entry.
- [ ] **Step 3:** Component test for `TargetMultiSelect` (search filters, select adds chip, remove works).
- [ ] **Step 4:** Commit: `fe(components): TargetChips + TargetMultiSelect`.

### Task 16: Protocol design tab + create dialog

**Files:** Modify `components/design-tab.tsx`, `components/create-protocol-dialog.tsx`.

- [ ] **Step 1:** Design tab: replace the single-target field with a **Targets** section. Direct targets (`is_direct`) render as removable chips (calls remove-protocol-target hook). Inherited targets render with a muted "from N runs" badge, no remove. An "Add target" `TargetMultiSelect`/picker calls add-protocol-target on select. Honor lock/RETIRED (disable controls). Explicit gestures — persist on select/remove, no autosave-on-blur.
- [ ] **Step 2:** Create-protocol dialog: replace the `SearchableSelect` (`:477-485`) with `TargetMultiSelect` bound to `target_ids` in the form.
- [ ] **Step 3:** Commit: `fe(protocol): multi-target design section + create dialog`.

### Task 17: Run detail card + create dialog

**Files:** Modify `components/run-detail.tsx`, `components/create-run-dialog.tsx`.

- [ ] **Step 1:** Run detail: add a **Targets** card — chips for the run's targets, add via `TargetMultiSelect` (add-run-target hook), remove per chip (remove-run-target hook). Disable when run `is_locked`. Explicit gestures.
- [ ] **Step 2:** Create-run dialog: add a `TargetMultiSelect` bound to `target_ids`.
- [ ] **Step 3:** Commit: `fe(run): targets card + create dialog`.

### Task 18: Grid columns (protocol dash + run table)

**Files:** Modify `components/protocol-list.tsx`, `components/run-list.tsx`.

- [ ] **Step 1:** Protocol dash table: add a **Targets** column rendering `<TargetChips targets={row.targets} />` (from `ProtocolSummary.targets`).
- [ ] **Step 2:** Run table: add a **Targets** column rendering `<TargetChips targets={row.targets} />` (from `Run.targets`).
- [ ] **Step 3:** Commit: `fe(grids): target columns on protocol dash + run table`.

### Task 19: Search sections

**Files:** Modify `frontend/src/features/research-organization/components/search/protocol-section.tsx`, `frontend/src/features/screen-campaign/components/campaign-view/source-protocols-list.tsx`.

- [ ] **Step 1:** `protocol-section.tsx` (`:133`, `:162-164`): include all target names in the searchable string; render `<TargetChips>` instead of the single badge.
- [ ] **Step 2:** `source-protocols-list.tsx:27`: render effective target chips (replace `p.target_name ?? p.target`).
- [ ] **Step 3:** Commit: `fe(search): multi-target chips + search across target names`.

---

## Phase 6 — Verify

### Task 20: Full verification

- [ ] **Step 1:** `cd backend && uv run pytest -q` — all green (fix any remaining `target_id` references surfaced by the suite).
- [ ] **Step 2:** `cd backend && uv run ruff check . && uv run mypy src` (or the repo's configured lint/type commands).
- [ ] **Step 3:** `cd frontend && pnpm biome check src && pnpm tsc --noEmit && pnpm test` (component tests).
- [ ] **Step 4:** Manual smoke (or Playwright if present): add a target to a run → appears on the protocol; remove last → pruned; direct target persists; grids show chips.
- [ ] **Step 5:** Commit any fixes; update `docs/implementation-status.md` if this maps to a tracked item.

---

## Self-review notes
- Spec coverage: data model (T1-2), domain drop (T3), repo union/prune (T4-6), app create/add/remove/version/enrichment (T7-9), API + tests (T10-13), FE components/dialogs/grids/search (T14-19), verify (T20). All spec §3–§10 mapped.
- Type consistency: `EffectiveTarget`(py) ↔ `ProtocolTargetRefResponse`(api) ↔ `ProtocolTargetRef`(ts) carry `is_direct`+`run_count`; `TargetRef` is the lightweight `{id,name,target_type}` used for runs + summaries + chips.
- Auto-prune is read-time (no prune code) — verified by T6 union assertions.
