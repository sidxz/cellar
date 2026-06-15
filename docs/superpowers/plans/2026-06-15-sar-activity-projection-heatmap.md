# SAR Activity Projection + Heatmap (Part 2 backend / completes Unit A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the server-side **activity projection** async-job slice (materializes one scalar/molecule for a color channel), the server-aggregated **`/heatmap`** endpoint, and the **`/rows` activity extension** — completing Unit A so the SAR FE (Unit B) has its full backend.

**Architecture:** Mirrors the merged decomposition slice (Part 1a+1b) **exactly** — a second async job type keyed by `(membership_hash, channel_hash)`: cache → inline ≤200 → 202+Temporal job; Null asyncio fallback in dev; poll + cancel. Two novel pieces ride on top: (1) the **scalar port** — `RunActivityProjection` streams member ids → `MoleculeActivityService.enrich_molecules(...)` → a 4-line `pick_scalar` (the server port of FE `colorSpecScalar`) → sparse `sar_activity_values`; (2) two pure-SQL read endpoints — `/heatmap` (GROUP BY argmin over assignment ⋈ activity_value) and the `/rows` activity LEFT JOIN.

**Tech Stack:** Python 3.13 · SQLAlchemy 2.0 async · Temporal · Lagom DI · dry-python/returns · FastAPI · pytest (`asyncio_mode=auto`, testcontainers `uow`/`session_factory` fixtures, httpx `client`/`api_app`/`workspace_id` api fixtures). All commands run from `backend/`.

**Spec:** `docs/superpowers/specs/2026-06-11-sar-full-collection-coverage-design.md` (§3 Pair 2 + §4). **Handoff:** `docs/superpowers/specs/2026-06-15-sar-part2-activity-heatmap-handoff.md` (the "Locked decisions" block).

**Locked decisions (brainstorm 2026-06-15):**
- **Scalar port** — `enrich_molecules` already aggregates (selection rule applied); the port only *picks*: `intercept_key` set ⇒ match `av.intercept_values` by `(kind, level)` → `.value`; else ⇒ `av.value`. No aggregation re-implementation.
- **`channel_hash`** = `sha256_hex` of normalized JSON over the **semantic** fields only — `{column, intercept_key, selection_rule, qualifier_handling, run_scopes}`; `label`/`protocol_id`/`source` excluded so a relabel is a cache hit.
- **Parity defaults** (match today's FE `use-sar-activity`): `qualifier_handling = exclude_qualified`, `run_scopes = null`.
- **`snapshot`** per value = `json.loads(json.dumps(asdict(av), default=…))` — the same wire shape the search grid already consumes, made JSON-safe (curve-expand off-set).
- **Heatmap cell representative** = `argmin(scalar)` (lower-is-better). Correct for v1: the FE gates coloring/curve-expand to `dr_curve` channels, every DR potency scalar is a concentration (lower = more potent). No direction flag (YAGNI). Document at the SQL site.
- **Inline threshold = 200** (match decomposition; tunable constructor param).
- **Heatmap axis cap = top-30 per axis** ranked by descending member count; endpoint returns `y_total`/`x_total`/`truncated` for honest "top 30 of N" labeling; omitted substituents dropped.
- **Member fetch** = reuse `DecompositionMemberStream` + `fetch_for_decomposition` as-is.

**Migration:** head is `057_rgroup_decomposition_runs`; Part 2 adds **`058`** (`sar_activity_projections` + `sar_activity_values`). Confirm `alembic heads == 057_rgroup_decomposition_runs` before starting; if not, STOP and reconcile.

**Commit convention:** Every commit uses explicit pathspec (`git commit ... -- <paths>`) because the working tree may carry unrelated staged work, and ends with the trailer:
`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

**Amendment (2026-06-15, post-implementation security review):** `SarActivityProjectionRepository.find_cached`
takes a **`workspace_id`** keyword and filters on it (defense-in-depth — every sibling lookup is
workspace-scoped; the hash inputs already are, but the cache key is filtered explicitly). This applies to the
Protocol (Task 6), the SQLAlchemy impl + its test (Task 8), and the `StartActivityProjection` call site + its
fake (Task 10) — all carry `workspace_id=...`. Canonical change: commit `ae064e0a`.

---

## File Structure

**Create — domain:**
- `src/cellar/domain/sar_analysis/sar_activity_projection.py` — `SarActivityProjection` aggregate + status enum + `InvalidSarProjectionTransition`.
- `src/cellar/domain/sar_analysis/activity_projection_types.py` — `ActivityScalar` VO.

**Create — application:**
- `src/cellar/application/sar_analysis/activity_channel.py` — `ActivityChannelSpec`, `pick_scalar`, `channel_hash`, `activity_value_snapshot`.
- `src/cellar/application/sar_analysis/activity_enrichment.py` — `MoleculeActivityEnricher` Protocol + `enrich_to_scalars`.
- `src/cellar/application/sar_analysis/run_activity_projection.py` — `RunActivityProjection`.
- `src/cellar/application/sar_analysis/start_activity_projection.py` — `SarActivityProjectionOrchestrator` Protocol, `StartActivityProjectionInput`, `StartActivityProjection`.
- `src/cellar/application/sar_analysis/get_activity_projection.py` — `GetActivityProjectionInput`, `GetActivityProjection`.
- `src/cellar/application/sar_analysis/cancel_activity_projection.py` — `CancelActivityProjectionInput`, `CancelActivityProjection`.
- `src/cellar/application/sar_analysis/activity_heatmap.py` — `HeatmapCell`, `HeatmapResult`, `ActivityHeatmapReader` Protocol, `FetchActivityHeatmapInput`, `FetchActivityHeatmap`.

**Create — infrastructure:**
- `src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/sar_activity_projection_models.py` — `SarActivityProjectionModel`, `SarActivityValueModel`.
- `src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/sar_activity_projection_repository.py` — `SQLAlchemySarActivityProjectionRepository`.
- `src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/activity_heatmap_reader.py` — `SQLAlchemyActivityHeatmapReader`.
- `src/cellar/infrastructure/temporal/workflows/sar_activity_projection.py`
- `src/cellar/infrastructure/temporal/activities/sar_activity_projection.py`
- `src/cellar/infrastructure/temporal/orchestrators/sar_activity_projection.py`
- `backend/alembic/versions/058_sar_activity_projections.py`

**Modify:**
- `src/cellar/application/sar_analysis/repositories.py` — add `SarActivityProjectionRepository`.
- `src/cellar/application/sar_analysis/decomposition_rows.py` — add `projection_id` + `activity`.
- `src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/decomposition_row_reader.py` — optional activity LEFT JOIN + "activity" sort.
- `src/cellar/infrastructure/di/_sar_analysis.py` — register projection slice + Null fallback.
- `src/cellar/interface/dependencies/_sar_analysis.py` — add Deps.
- `src/cellar/interface/routes/sar_analysis.py` — activity-projection routes + heatmap + rows-activity.
- `src/cellar/infrastructure/temporal/worker.py` — register workflow + activity.
- `src/cellar/interface/app.py` — lifespan orchestrator binding.
- `tests/unit/infrastructure/di/test_sar_analysis_wiring.py` — wiring assertions.
- `tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py` — activity-join cases.
- `tests/api/test_sar_analysis_routes.py` — heatmap + rows-activity cases.

**Test (create):** one per source module — paths given inline per task.

---

## Task 0: Pre-flight

- [ ] **Step 1: Confirm migration head + Part 1a/1b seams**

Run:
```bash
cd backend && uv run alembic heads && uv run python -c "from cellar.application.screening.molecule_activity_service import MoleculeActivityService; from cellar.domain.screening_assay.activity_types import ActivityValue; from cellar.domain.shared.hit_criterion import InterceptKey; from cellar.domain.shared.aggregation_types import SelectionRule, QualifierHandling; from cellar.application.sar_analysis.decomposition_members import DecompositionMemberStream; print('seams ok')"
```
Expected: head is `057_rgroup_decomposition_runs`; prints `seams ok`. If the head differs, STOP and reconcile.

---

## Task 1: Migration 058 — projection header + sparse values

**Files:**
- Create: `backend/alembic/versions/058_sar_activity_projections.py`

- [ ] **Step 1: Write the migration** (mirror `057_rgroup_decomposition_runs.py`)

Create `backend/alembic/versions/058_sar_activity_projections.py`:

```python
"""058 — sar_activity_projections + sar_activity_values.

Persisted SarActivityProjection aggregate (one materialized scalar per molecule
for a color channel). The header doubles as a (membership_hash, channel_hash)
cache via a partial index WHERE status='ready'. Values are SPARSE — only
molecules with a value — so a LEFT JOIN nulls render as heatmap gaps / uncolored
cells, exactly as the client did pre-Part-2. Core-independent: reused across
decomposition runs of the same membership.

Revision ID: 058_sar_activity_projections
Revises: 057_rgroup_decomposition_runs
Create Date: 2026-06-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "058_sar_activity_projections"
down_revision: str | None = "057_rgroup_decomposition_runs"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "sar_activity_projections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("membership_hash", sa.Text(), nullable=False),
        sa.Column("channel_hash", sa.Text(), nullable=False),
        sa.Column("channel_spec", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("value_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index(
        "sar_activity_proj_workspace_status",
        "sar_activity_projections",
        ["workspace_id", "status"],
    )
    op.create_index(
        "sar_activity_proj_cache",
        "sar_activity_projections",
        ["membership_hash", "channel_hash", sa.text("completed_at DESC")],
        postgresql_where=sa.text("status = 'ready'"),
    )

    op.create_table(
        "sar_activity_values",
        sa.Column(
            "projection_id",
            sa.Uuid(),
            sa.ForeignKey("sar_activity_projections.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("molecule_id", sa.Uuid(), primary_key=True),
        sa.Column("scalar", sa.Float(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("qualifier", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sar_activity_values")
    op.drop_index("sar_activity_proj_cache", table_name="sar_activity_projections")
    op.drop_index("sar_activity_proj_workspace_status", table_name="sar_activity_projections")
    op.drop_table("sar_activity_projections")
```

- [ ] **Step 2: Verify it applies (upgrade/downgrade round-trip)**

Run:
```bash
cd backend && uv run alembic upgrade head && uv run alembic heads && uv run alembic downgrade -1 && uv run alembic upgrade head
```
Expected: head becomes `058_sar_activity_projections`; downgrade and re-upgrade both succeed without error. (Requires the dev Postgres up.)

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(sar): migration 058 — sar_activity_projections + sar_activity_values" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- backend/alembic/versions/058_sar_activity_projections.py
```

---

## Task 2: Domain — `SarActivityProjection` aggregate

**Files:**
- Create: `src/cellar/domain/sar_analysis/sar_activity_projection.py`
- Test: `tests/unit/domain/sar_analysis/test_sar_activity_projection.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/domain/sar_analysis/test_sar_activity_projection.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.domain.sar_analysis.sar_activity_projection import (
    InvalidSarProjectionTransition,
    SarActivityProjection,
    SarActivityProjectionStatus,
)

_NOW = datetime(2026, 6, 15, tzinfo=UTC)


def _pending() -> SarActivityProjection:
    return SarActivityProjection.create(
        workspace_id=uuid.uuid4(),
        requested_by=uuid.uuid4(),
        membership_hash="m",
        channel_hash="ch",
        channel_spec={"column": "drc:x"},
        now=_NOW,
    )


def test_create_is_pending():
    p = _pending()
    assert p.status == SarActivityProjectionStatus.PENDING
    assert p.value_count == 0
    assert p.channel_spec == {"column": "drc:x"}
    assert p.version == 1


def test_running_then_ready_sets_value_count():
    ready = _pending().mark_running(_NOW).mark_ready(value_count=7, now=_NOW)
    assert ready.status == SarActivityProjectionStatus.READY
    assert ready.value_count == 7
    assert ready.completed_at == _NOW


def test_ready_requires_running():
    with pytest.raises(InvalidSarProjectionTransition):
        _pending().mark_ready(value_count=1, now=_NOW)


def test_failed_from_running_carries_message():
    failed = _pending().mark_running(_NOW).mark_failed("boom", _NOW)
    assert failed.status == SarActivityProjectionStatus.FAILED
    assert failed.error_message == "boom"


def test_cancel_terminal_is_rejected():
    ready = _pending().mark_running(_NOW).mark_ready(value_count=0, now=_NOW)
    with pytest.raises(InvalidSarProjectionTransition):
        ready.mark_cancelled(_NOW)


def test_cancel_pending_ok():
    cancelled = _pending().mark_cancelled(_NOW)
    assert cancelled.status == SarActivityProjectionStatus.CANCELLED
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/unit/domain/sar_analysis/test_sar_activity_projection.py -v`
Expected: FAIL — `ModuleNotFoundError: ...sar_activity_projection`.

- [ ] **Step 3: Implement the aggregate** (mirror `rgroup_decomposition_run.py`)

Create `src/cellar/domain/sar_analysis/sar_activity_projection.py`:

```python
"""SarActivityProjection — persisted async materialization of one activity scalar
per molecule for a color channel, over a member set.

State machine (mirrors RGroupDecompositionRun):
  pending -> running -> {ready | failed | cancelled}
  pending             ->  cancelled

ready / failed / cancelled are terminal.

The aggregate holds only the *header* (channel spec + value count). The
per-molecule scalars are persisted as separate SPARSE rows (see the repository) —
only molecules that have a value, so a LEFT JOIN nulls render as heatmap gaps.
Keyed by (membership_hash, channel_hash); core-independent, reused across cores.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any
from uuid import UUID


class SarActivityProjectionStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InvalidSarProjectionTransition(Exception):
    pass


_TERMINAL = {
    SarActivityProjectionStatus.READY,
    SarActivityProjectionStatus.FAILED,
    SarActivityProjectionStatus.CANCELLED,
}


@dataclass(frozen=True)
class SarActivityProjection:
    id: UUID
    workspace_id: UUID
    requested_by: UUID
    membership_hash: str
    channel_hash: str
    channel_spec: dict[str, Any]
    requested_at: datetime
    status: SarActivityProjectionStatus = SarActivityProjectionStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    value_count: int = 0
    version: int = 1

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
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            requested_by=requested_by,
            membership_hash=membership_hash,
            channel_hash=channel_hash,
            channel_spec=dict(channel_spec),
            requested_at=now,
        )

    def mark_running(self, now: datetime) -> SarActivityProjection:
        if self.status != SarActivityProjectionStatus.PENDING:
            raise InvalidSarProjectionTransition(f"Cannot mark RUNNING from {self.status}")
        return replace(self, status=SarActivityProjectionStatus.RUNNING, started_at=now)

    def mark_ready(self, *, value_count: int, now: datetime) -> SarActivityProjection:
        if self.status != SarActivityProjectionStatus.RUNNING:
            raise InvalidSarProjectionTransition(f"Cannot mark READY from {self.status}")
        return replace(
            self,
            status=SarActivityProjectionStatus.READY,
            completed_at=now,
            value_count=value_count,
        )

    def mark_failed(self, error: str, now: datetime) -> SarActivityProjection:
        if self.status not in {
            SarActivityProjectionStatus.PENDING,
            SarActivityProjectionStatus.RUNNING,
        }:
            raise InvalidSarProjectionTransition(f"Cannot mark FAILED from {self.status}")
        return replace(
            self,
            status=SarActivityProjectionStatus.FAILED,
            completed_at=now,
            error_message=error,
        )

    def mark_cancelled(self, now: datetime) -> SarActivityProjection:
        if self.status in _TERMINAL:
            raise InvalidSarProjectionTransition(f"Cannot CANCEL terminal {self.status}")
        return replace(self, status=SarActivityProjectionStatus.CANCELLED, completed_at=now)
```

(Note: `field` import is unused here but kept off — remove if your linter flags it; the model uses `dict` defaults via `create`.)

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `cd backend && uv run pytest tests/unit/domain/sar_analysis/test_sar_activity_projection.py -v && uv run lint-imports`
Expected: all PASS; import-linter clean (domain imports nothing forbidden).

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(sar): SarActivityProjection aggregate + state machine" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/domain/sar_analysis/sar_activity_projection.py tests/unit/domain/sar_analysis/test_sar_activity_projection.py
```

---

## Task 3: Domain — `ActivityScalar` VO

**Files:**
- Create: `src/cellar/domain/sar_analysis/activity_projection_types.py`
- Test: `tests/unit/domain/sar_analysis/test_activity_projection_types.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/domain/sar_analysis/test_activity_projection_types.py`:

```python
from __future__ import annotations

import uuid

from cellar.domain.sar_analysis.activity_projection_types import ActivityScalar


def test_activity_scalar_holds_value_and_snapshot():
    mid = uuid.uuid4()
    s = ActivityScalar(
        molecule_id=mid,
        scalar=0.42,
        unit="uM",
        qualifier=None,
        source="dose_response",
        snapshot={"value": 0.42},
    )
    assert s.molecule_id == mid
    assert s.scalar == 0.42
    assert s.snapshot == {"value": 0.42}


def test_snapshot_defaults_to_empty_dict():
    s = ActivityScalar(
        molecule_id=uuid.uuid4(), scalar=1.0, unit=None, qualifier=None, source="readout"
    )
    assert s.snapshot == {}
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/unit/domain/sar_analysis/test_activity_projection_types.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/cellar/domain/sar_analysis/activity_projection_types.py`:

```python
"""Pure-data result type for activity projection.

One ``ActivityScalar`` per molecule that has a value for the channel (sparse).
``snapshot`` is the molecule's full ``ActivityValue`` in wire shape (JSON-safe) so
heatmap curve-expand works without the client holding ``props.molecules``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class ActivityScalar:
    molecule_id: UUID
    scalar: float
    unit: str | None
    qualifier: str | None
    source: str
    snapshot: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `cd backend && uv run pytest tests/unit/domain/sar_analysis/test_activity_projection_types.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(sar): ActivityScalar result VO" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/domain/sar_analysis/activity_projection_types.py tests/unit/domain/sar_analysis/test_activity_projection_types.py
```

---

## Task 4: Application — the scalar port (`activity_channel.py`)

**The keystone.** `ActivityChannelSpec` + `pick_scalar` (port of FE `colorSpecScalar`) + `channel_hash` (label-insensitive) + `activity_value_snapshot` (JSON-safe wire shape).

**Files:**
- Create: `src/cellar/application/sar_analysis/activity_channel.py`
- Test: `tests/unit/application/sar_analysis/test_activity_channel.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/application/sar_analysis/test_activity_channel.py`:

```python
from __future__ import annotations

import uuid

from cellar.application.sar_analysis.activity_channel import (
    ActivityChannelSpec,
    activity_value_snapshot,
    channel_hash,
    pick_scalar,
)
from cellar.domain.screening_assay.activity_types import ActivityValue, RunSummary
from cellar.domain.shared.aggregation_types import QualifierHandling, SelectionRule
from cellar.domain.shared.hit_criterion import InterceptKey


def _spec(**over) -> ActivityChannelSpec:
    base = dict(
        column="drc:" + str(uuid.uuid4()),
        source="dr_curve",
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.EXCLUDE_QUALIFIED,
        intercept_key=None,
        run_scopes=None,
        protocol_id=None,
        label="EGFR · IC50",
    )
    base.update(over)
    return ActivityChannelSpec(**base)


def test_pick_scalar_primary_returns_value_when_no_intercept_key():
    av = ActivityValue(value=0.5, qualifier=None, unit="uM", source="dose_response")
    assert pick_scalar(av, None) == 0.5


def test_pick_scalar_intercept_matches_by_kind_and_level():
    av = ActivityValue(
        value=0.5,
        qualifier=None,
        unit="uM",
        source="dose_response",
        intercept_values=[
            {"spec": {"kind": "ic", "level": 50.0}, "value": 0.5},
            {"spec": {"kind": "ic", "level": 90.0}, "value": 3.2},
        ],
    )
    assert pick_scalar(av, InterceptKey(kind="ic", level=90.0)) == 3.2


def test_pick_scalar_intercept_miss_returns_none():
    av = ActivityValue(
        value=0.5, qualifier=None, unit="uM", source="dose_response",
        intercept_values=[{"spec": {"kind": "ic", "level": 50.0}, "value": 0.5}],
    )
    assert pick_scalar(av, InterceptKey(kind="ec", level=50.0)) is None


def test_pick_scalar_primary_none_value():
    av = ActivityValue(value=None, qualifier="nd", unit="uM", source="dose_response")
    assert pick_scalar(av, None) is None


def test_channel_hash_ignores_label():
    a = _spec(label="EGFR · IC50")
    b = _spec(column=a.column, label="totally different label")
    assert channel_hash(a) == channel_hash(b)


def test_channel_hash_changes_on_intercept_key():
    a = _spec(intercept_key=None)
    b = _spec(column=a.column, intercept_key=InterceptKey(kind="ic", level=90.0))
    assert channel_hash(a) != channel_hash(b)


def test_channel_hash_changes_on_selection_rule():
    a = _spec(selection_rule=SelectionRule.LATEST_APPROVED_RUN)
    b = _spec(column=a.column, selection_rule=SelectionRule.GEOMETRIC_MEAN)
    assert channel_hash(a) != channel_hash(b)


def test_to_spec_dict_round_trips():
    a = _spec(intercept_key=InterceptKey(kind="ec", level=50.0), run_scopes={"drc:x": {"mode": "latest"}})
    d = a.to_spec_dict()
    back = ActivityChannelSpec.from_spec_dict(d)
    assert back.column == a.column
    assert back.intercept_key == a.intercept_key
    assert back.selection_rule == a.selection_rule
    assert back.run_scopes == a.run_scopes
    assert channel_hash(back) == channel_hash(a)


def test_resolved_run_scopes_parses_wire_to_runscope():
    a = _spec(run_scopes={"drc:x": {"mode": "latest"}})
    rs = a.resolved_run_scopes()
    assert rs is not None
    assert rs["drc:x"].last_n_count == 1


def test_snapshot_is_json_safe_even_with_uuid_and_date_fields():
    import datetime
    import json

    av = ActivityValue(
        value=0.5, qualifier=None, unit="uM", source="dose_response",
        runs=[RunSummary(
            run_id=uuid.uuid4(),
            run_date=datetime.date(2026, 6, 1),
            curve_id=uuid.uuid4(),
            curve_class="active",
            r_squared=0.99,
            intercept_values=[],
        )],
    )
    snap = activity_value_snapshot(av)
    # Round-trips through JSON without raising (UUID -> str, date -> isoformat).
    assert json.dumps(snap)
    assert snap["value"] == 0.5
    assert isinstance(snap["runs"][0]["run_id"], str)
    assert snap["runs"][0]["run_date"] == "2026-06-01"
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis/test_activity_channel.py -v`
Expected: FAIL — `ModuleNotFoundError: ...activity_channel`.

- [ ] **Step 3: Implement**

Create `src/cellar/application/sar_analysis/activity_channel.py`:

```python
"""The activity color channel: spec, scalar selection, cache hash, snapshot.

``pick_scalar`` is the server-side port of the FE ``colorSpecScalar``
(``frontend/.../sar-analysis/lib/sar-color-spec.ts``). It does NOT aggregate —
``MoleculeActivityService.enrich_molecules`` already applied the selection rule
and returns a per-cell ``ActivityValue``. The port only *picks* one scalar:
``intercept_key`` set ⇒ match ``av.intercept_values`` by ``(kind, level)`` →
``.value``; else ⇒ ``av.value``. This guarantees parity with what the FE used to
compute client-side.

``channel_hash`` is the cache key's channel half. It normalizes over the
SEMANTIC fields only — what actually determines the scalar — so two channels that
differ only by display ``label`` (or redundant ``protocol_id``/``source``) hash
equal and reuse the cached projection.
"""

from __future__ import annotations

import datetime
import json
import uuid
from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

from cellar.application.sar_analysis.hashing import sha256_hex
from cellar.domain.screening_assay.activity_types import ActivityValue
from cellar.domain.screening_assay.run_scope import RunScope
from cellar.domain.shared.aggregation_types import QualifierHandling, SelectionRule
from cellar.domain.shared.hit_criterion import InterceptKey


@dataclass(frozen=True)
class ActivityChannelSpec:
    """One SAR color channel. ``column`` is the enrich token (``drc:<rd>`` or
    ``rd:<proto>:<rd>``); ``intercept_key`` narrows which scalar on the cell;
    ``run_scopes`` is the raw FE wire shape (mode-keyed), parsed at run time."""

    column: str
    source: str  # "dr_curve" | "readout_data"
    selection_rule: SelectionRule
    qualifier_handling: QualifierHandling
    intercept_key: InterceptKey | None = None
    run_scopes: dict[str, Any] | None = None
    protocol_id: UUID | None = None
    label: str = ""

    def resolved_run_scopes(self) -> dict[str, RunScope] | None:
        if not self.run_scopes:
            return None
        return {k: RunScope.from_wire(v) for k, v in self.run_scopes.items()}

    def to_spec_dict(self) -> dict[str, Any]:
        """Full JSON-safe dict for the ``channel_spec`` JSONB column (carries
        ``label``/``protocol_id`` for provenance; those are excluded from the
        hash)."""
        return {
            "column": self.column,
            "source": self.source,
            "selection_rule": self.selection_rule.value,
            "qualifier_handling": self.qualifier_handling.value,
            "intercept_key": (
                {"kind": self.intercept_key.kind, "level": self.intercept_key.level}
                if self.intercept_key is not None
                else None
            ),
            "run_scopes": self.run_scopes,
            "protocol_id": str(self.protocol_id) if self.protocol_id is not None else None,
            "label": self.label,
        }

    @classmethod
    def from_spec_dict(cls, d: dict[str, Any]) -> ActivityChannelSpec:
        ik = d.get("intercept_key")
        pid = d.get("protocol_id")
        return cls(
            column=d["column"],
            source=d.get("source", "dr_curve"),
            selection_rule=SelectionRule(d["selection_rule"]),
            qualifier_handling=QualifierHandling(d["qualifier_handling"]),
            intercept_key=(
                InterceptKey(kind=ik["kind"], level=float(ik["level"])) if ik else None
            ),
            run_scopes=d.get("run_scopes"),
            protocol_id=uuid.UUID(pid) if pid else None,
            label=d.get("label", ""),
        )


def channel_hash(spec: ActivityChannelSpec) -> str:
    """SHA-256 over the SEMANTIC determinants of the scalar — column, intercept,
    selection rule, qualifier handling, run scopes. ``label``/``protocol_id``/
    ``source`` are excluded (cosmetic or redundant with ``column``)."""
    semantic = {
        "column": spec.column,
        "intercept_key": (
            {"kind": spec.intercept_key.kind, "level": spec.intercept_key.level}
            if spec.intercept_key is not None
            else None
        ),
        "selection_rule": spec.selection_rule.value,
        "qualifier_handling": spec.qualifier_handling.value,
        "run_scopes": spec.run_scopes,
    }
    return sha256_hex(json.dumps(semantic, sort_keys=True, separators=(",", ":")))


def pick_scalar(av: ActivityValue, intercept_key: InterceptKey | None) -> float | None:
    """Port of FE ``colorSpecScalar``. Pre-aggregated ``av`` in, one scalar out."""
    if intercept_key is not None:
        for iv in av.intercept_values or []:
            spec = iv.get("spec") or {}
            level = spec.get("level")
            if (
                spec.get("kind") == intercept_key.kind
                and isinstance(level, (int, float))
                and float(level) == intercept_key.level
            ):
                val = iv.get("value")
                return float(val) if isinstance(val, (int, float)) else None
        return None
    return av.value


def _json_default(o: Any) -> Any:
    if isinstance(o, uuid.UUID):
        return str(o)
    if isinstance(o, (datetime.date, datetime.datetime)):
        return o.isoformat()
    raise TypeError(f"not JSON serializable: {type(o)!r}")


def activity_value_snapshot(av: ActivityValue) -> dict[str, Any]:
    """The ``ActivityValue`` as the same JSON wire shape the search grid consumes
    (``asdict`` + UUID→str / date→isoformat), so curve-expand renders off the
    snapshot without ``props.molecules``."""
    return json.loads(json.dumps(asdict(av), default=_json_default))
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis/test_activity_channel.py -v && uv run lint-imports`
Expected: all PASS; import-linter clean (application → domain only; cross-context `domain.screening_assay` import is permitted — the independence contract governs domain↔domain).

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(sar): activity channel — scalar port + channel hash + snapshot" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/application/sar_analysis/activity_channel.py tests/unit/application/sar_analysis/test_activity_channel.py
```

---

## Task 5: Application — enricher port + `enrich_to_scalars`

**Files:**
- Create: `src/cellar/application/sar_analysis/activity_enrichment.py`
- Test: `tests/unit/application/sar_analysis/test_activity_enrichment.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/application/sar_analysis/test_activity_enrichment.py`:

```python
from __future__ import annotations

import uuid

import pytest

from cellar.application.sar_analysis.activity_channel import ActivityChannelSpec
from cellar.application.sar_analysis.activity_enrichment import enrich_to_scalars
from cellar.domain.screening_assay.activity_types import ActivityValue
from cellar.domain.shared.aggregation_types import QualifierHandling, SelectionRule
from cellar.domain.shared.hit_criterion import InterceptKey

_COLUMN = "drc:" + str(uuid.uuid4())


class FakeEnricher:
    def __init__(self, table):
        self._table = table
        self.calls = []

    async def enrich_molecules(
        self, workspace_id, molecule_ids, protocol_columns, *,
        selection_rule, qualifier_handling, run_scopes=None,
    ):
        self.calls.append((list(molecule_ids), list(protocol_columns), selection_rule, run_scopes))
        return {mid: self._table[mid] for mid in molecule_ids if mid in self._table}


def _channel(intercept_key=None) -> ActivityChannelSpec:
    return ActivityChannelSpec(
        column=_COLUMN,
        source="dr_curve",
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.EXCLUDE_QUALIFIED,
        intercept_key=intercept_key,
    )


@pytest.mark.asyncio
async def test_enrich_to_scalars_picks_primary_value_and_snapshots():
    ws, a, b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    table = {
        a: {_COLUMN: ActivityValue(value=0.5, qualifier=None, unit="uM", source="dose_response")},
        b: {_COLUMN: ActivityValue(value=2.0, qualifier=">", unit="uM", source="dose_response")},
    }
    out = await enrich_to_scalars(FakeEnricher(table), workspace_id=ws, molecule_ids=[a, b], channel=_channel())
    by_id = {s.molecule_id: s for s in out}
    assert by_id[a].scalar == 0.5
    assert by_id[a].unit == "uM"
    assert by_id[b].qualifier == ">"
    assert by_id[a].snapshot["value"] == 0.5  # snapshot present


@pytest.mark.asyncio
async def test_enrich_to_scalars_skips_molecules_with_no_value():
    ws, a, b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    table = {
        a: {_COLUMN: ActivityValue(value=0.5, qualifier=None, unit="uM", source="dose_response")},
        b: {_COLUMN: ActivityValue(value=None, qualifier="nd", unit="uM", source="dose_response")},
        # 'a' present, 'b' has no scalar, unknown id dropped by the fake.
    }
    out = await enrich_to_scalars(FakeEnricher(table), workspace_id=ws, molecule_ids=[a, b], channel=_channel())
    assert {s.molecule_id for s in out} == {a}  # b skipped (None scalar -> sparse)


@pytest.mark.asyncio
async def test_enrich_to_scalars_uses_intercept_key():
    ws, a = uuid.uuid4(), uuid.uuid4()
    table = {a: {_COLUMN: ActivityValue(
        value=0.5, qualifier=None, unit="uM", source="dose_response",
        intercept_values=[{"spec": {"kind": "ic", "level": 90.0}, "value": 3.2}],
    )}}
    out = await enrich_to_scalars(
        FakeEnricher(table), workspace_id=ws, molecule_ids=[a],
        channel=_channel(intercept_key=InterceptKey(kind="ic", level=90.0)),
    )
    assert out[0].scalar == 3.2


@pytest.mark.asyncio
async def test_enrich_to_scalars_empty_ids_returns_empty_no_call():
    enricher = FakeEnricher({})
    out = await enrich_to_scalars(enricher, workspace_id=uuid.uuid4(), molecule_ids=[], channel=_channel())
    assert out == []
    assert enricher.calls == []
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis/test_activity_enrichment.py -v`
Expected: FAIL — `ModuleNotFoundError: ...activity_enrichment`.

- [ ] **Step 3: Implement**

Create `src/cellar/application/sar_analysis/activity_enrichment.py`:

```python
"""The enricher port + the batch ``enrich_to_scalars`` bridge.

``MoleculeActivityEnricher`` is the application-layer Protocol that
``MoleculeActivityService`` satisfies structurally (wired via DI), so the
projection use cases stay unit-testable with a fake. ``enrich_to_scalars`` runs
one enrich call for a batch of ids and applies ``pick_scalar`` to produce SPARSE
``ActivityScalar`` rows — the shared bridge used by both ``StartActivityProjection``
(inline) and ``RunActivityProjection`` (per streamed batch).
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from cellar.application.sar_analysis.activity_channel import (
    ActivityChannelSpec,
    activity_value_snapshot,
    pick_scalar,
)
from cellar.domain.sar_analysis.activity_projection_types import ActivityScalar
from cellar.domain.screening_assay.activity_types import ActivityValue
from cellar.domain.screening_assay.run_scope import RunScope
from cellar.domain.shared.aggregation_types import QualifierHandling, SelectionRule


class MoleculeActivityEnricher(Protocol):
    async def enrich_molecules(
        self,
        workspace_id: UUID,
        molecule_ids: list[UUID],
        protocol_columns: list[str],
        *,
        selection_rule: SelectionRule = SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling: QualifierHandling = QualifierHandling.EXCLUDE_QUALIFIED,
        run_scopes: dict[str, RunScope] | None = None,
    ) -> dict[UUID, dict[str, ActivityValue]]: ...


async def enrich_to_scalars(
    enricher: MoleculeActivityEnricher,
    *,
    workspace_id: UUID,
    molecule_ids: list[UUID],
    channel: ActivityChannelSpec,
) -> list[ActivityScalar]:
    if not molecule_ids:
        return []
    enriched = await enricher.enrich_molecules(
        workspace_id,
        molecule_ids,
        [channel.column],
        selection_rule=channel.selection_rule,
        qualifier_handling=channel.qualifier_handling,
        run_scopes=channel.resolved_run_scopes(),
    )
    out: list[ActivityScalar] = []
    for molecule_id, cols in enriched.items():
        av = cols.get(channel.column)
        if av is None:
            continue
        scalar = pick_scalar(av, channel.intercept_key)
        if scalar is None:
            continue  # sparse — no value for this molecule on this channel
        out.append(
            ActivityScalar(
                molecule_id=molecule_id,
                scalar=scalar,
                unit=av.unit,
                qualifier=av.qualifier,
                source=av.source,
                snapshot=activity_value_snapshot(av),
            )
        )
    return out
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis/test_activity_enrichment.py -v && uv run lint-imports`
Expected: all PASS; import-linter clean.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(sar): MoleculeActivityEnricher port + enrich_to_scalars bridge" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/application/sar_analysis/activity_enrichment.py tests/unit/application/sar_analysis/test_activity_enrichment.py
```

---

## Task 6: Application — `SarActivityProjectionRepository` Protocol

**Files:**
- Modify: `src/cellar/application/sar_analysis/repositories.py`

- [ ] **Step 1: Add the Protocol** (append to `repositories.py`, after `RGroupDecompositionRunRepository`)

Add these imports at the top of `repositories.py` (next to the existing sar_analysis imports):

```python
from cellar.domain.sar_analysis.activity_projection_types import ActivityScalar
from cellar.domain.sar_analysis.sar_activity_projection import SarActivityProjection
```

Append at the end of `repositories.py`:

```python
class SarActivityProjectionRepository(Protocol):
    async def save(self, projection: SarActivityProjection) -> None: ...

    async def find_by_id(
        self, projection_id: UUID, *, workspace_id: UUID
    ) -> SarActivityProjection | None: ...

    async def find_cached(
        self, *, membership_hash: str, channel_hash: str
    ) -> SarActivityProjection | None:
        """Latest READY projection for this (membership_hash, channel_hash), or
        None. No TTL: valid until membership or channel changes (each changes a
        hash). Value rows for the returned projection are already persisted."""
        ...

    async def write_values(self, projection_id: UUID, values: list[ActivityScalar]) -> None: ...

    async def count_values(self, projection_id: UUID, *, workspace_id: UUID) -> int: ...
```

- [ ] **Step 2: Verify it imports + lints**

Run: `cd backend && uv run python -c "from cellar.application.sar_analysis.repositories import SarActivityProjectionRepository; print('ok')" && uv run lint-imports`
Expected: prints `ok`; import-linter clean.

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(sar): SarActivityProjectionRepository protocol" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/application/sar_analysis/repositories.py
```

---

## Task 7: Infra — SQLAlchemy models

**Files:**
- Create: `src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/sar_activity_projection_models.py`

- [ ] **Step 1: Implement the models** (mirror `rgroup_decomposition_models.py`; columns match migration 058)

Create `src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/sar_activity_projection_models.py`:

```python
"""SQLAlchemy models for the SarActivityProjection aggregate + its sparse value
rows. Columns match migration 058_sar_activity_projections exactly."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cellar.infrastructure.persistence.sqlalchemy.base import (
    Base,
    VersionMixin,
    WorkspaceIdMixin,
)


class SarActivityProjectionModel(Base, WorkspaceIdMixin, VersionMixin):
    __tablename__ = "sar_activity_projections"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    membership_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    channel_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    channel_spec: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class SarActivityValueModel(Base):
    __tablename__ = "sar_activity_values"

    projection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sar_activity_projections.id", ondelete="CASCADE"), primary_key=True
    )
    molecule_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    scalar: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualifier: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
```

- [ ] **Step 2: Verify the models import + match the table**

Run: `cd backend && uv run python -c "from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_models import SarActivityProjectionModel, SarActivityValueModel; print(SarActivityProjectionModel.__tablename__, SarActivityValueModel.__tablename__)"`
Expected: prints `sar_activity_projections sar_activity_values`.

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(sar): SQLAlchemy models for activity projection + values" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/sar_activity_projection_models.py
```

---

## Task 8: Infra — `SQLAlchemySarActivityProjectionRepository`

**Files:**
- Create: `src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/sar_activity_projection_repository.py`
- Test: `tests/integration/persistence/sar_analysis/test_sar_activity_projection_repository.py`

- [ ] **Step 1: Write the failing integration test**

Create `tests/integration/persistence/sar_analysis/test_sar_activity_projection_repository.py`:

```python
"""Integration tests for SQLAlchemySarActivityProjectionRepository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.domain.sar_analysis.activity_projection_types import ActivityScalar
from cellar.domain.sar_analysis.sar_activity_projection import (
    SarActivityProjection,
    SarActivityProjectionStatus,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_repository import (  # noqa: E501
    SQLAlchemySarActivityProjectionRepository,
)

_NOW = datetime(2026, 6, 15, tzinfo=UTC)


def _ready(ws, *, mh="m", ch="ch", value_count=0) -> SarActivityProjection:
    return (
        SarActivityProjection.create(
            workspace_id=ws, requested_by=uuid.uuid4(), membership_hash=mh,
            channel_hash=ch, channel_spec={"column": "drc:x"}, now=_NOW,
        )
        .mark_running(_NOW)
        .mark_ready(value_count=value_count, now=_NOW)
    )


@pytest.mark.asyncio
async def test_save_and_find_by_id_scoped_to_workspace(uow):
    ws = uuid.uuid4()
    proj = _ready(ws)
    async with uow:
        repo = SQLAlchemySarActivityProjectionRepository(uow)
        await repo.save(proj)
        await uow.commit()
    async with uow:
        repo = SQLAlchemySarActivityProjectionRepository(uow)
        found = await repo.find_by_id(proj.id, workspace_id=ws)
        other = await repo.find_by_id(proj.id, workspace_id=uuid.uuid4())
    assert found is not None and found.status == SarActivityProjectionStatus.READY
    assert other is None  # cross-workspace invisible


@pytest.mark.asyncio
async def test_find_cached_returns_latest_ready_for_keys(uow):
    ws = uuid.uuid4()
    async with uow:
        repo = SQLAlchemySarActivityProjectionRepository(uow)
        await repo.save(_ready(ws, mh="m1", ch="c1", value_count=3))
        # Different channel hash -> not a hit for (m1, c1).
        await repo.save(_ready(ws, mh="m1", ch="OTHER"))
        await uow.commit()
    async with uow:
        repo = SQLAlchemySarActivityProjectionRepository(uow)
        hit = await repo.find_cached(membership_hash="m1", channel_hash="c1")
        miss = await repo.find_cached(membership_hash="m1", channel_hash="nope")
    assert hit is not None and hit.value_count == 3
    assert miss is None


@pytest.mark.asyncio
async def test_write_values_and_count(uow):
    ws = uuid.uuid4()
    proj = _ready(ws)
    a, b = uuid.uuid4(), uuid.uuid4()
    async with uow:
        repo = SQLAlchemySarActivityProjectionRepository(uow)
        await repo.save(proj)
        await repo.write_values(
            proj.id,
            [
                ActivityScalar(molecule_id=a, scalar=0.5, unit="uM", qualifier=None,
                               source="dose_response", snapshot={"value": 0.5}),
                ActivityScalar(molecule_id=b, scalar=2.0, unit="uM", qualifier=">",
                               source="dose_response", snapshot={"value": 2.0}),
            ],
        )
        await uow.commit()
    async with uow:
        repo = SQLAlchemySarActivityProjectionRepository(uow)
        n = await repo.count_values(proj.id, workspace_id=ws)
    assert n == 2
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/integration/persistence/sar_analysis/test_sar_activity_projection_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: ...sar_activity_projection_repository`. (Requires Docker — testcontainers.)

- [ ] **Step 3: Implement the repository** (mirror `rgroup_decomposition_run_repository.py`)

Create `src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/sar_activity_projection_repository.py`:

```python
"""SQLAlchemy implementation of SarActivityProjectionRepository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, insert, select

from cellar.domain.sar_analysis.activity_projection_types import ActivityScalar
from cellar.domain.sar_analysis.sar_activity_projection import (
    SarActivityProjection,
    SarActivityProjectionStatus,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_models import (  # noqa: E501
    SarActivityProjectionModel,
    SarActivityValueModel,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemySarActivityProjectionRepository:
    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def save(self, projection: SarActivityProjection) -> None:
        session = self._uow.session
        existing = await session.get(SarActivityProjectionModel, projection.id)
        if existing is None:
            session.add(_to_model(projection))
        else:
            _apply_to_model(existing, projection)

    async def find_by_id(
        self, projection_id: UUID, *, workspace_id: UUID
    ) -> SarActivityProjection | None:
        session = self._uow.session
        stmt = select(SarActivityProjectionModel).where(
            SarActivityProjectionModel.id == projection_id,
            SarActivityProjectionModel.workspace_id == workspace_id,
        )
        model = (await session.execute(stmt)).scalar_one_or_none()
        return _to_domain(model) if model else None

    async def find_cached(
        self, *, membership_hash: str, channel_hash: str
    ) -> SarActivityProjection | None:
        session = self._uow.session
        stmt = (
            select(SarActivityProjectionModel)
            .where(
                SarActivityProjectionModel.membership_hash == membership_hash,
                SarActivityProjectionModel.channel_hash == channel_hash,
                SarActivityProjectionModel.status == SarActivityProjectionStatus.READY.value,
            )
            .order_by(SarActivityProjectionModel.completed_at.desc())
            .limit(1)
        )
        model = (await session.execute(stmt)).scalar_one_or_none()
        return _to_domain(model) if model else None

    async def write_values(self, projection_id: UUID, values: list[ActivityScalar]) -> None:
        session = self._uow.session
        BATCH = 1000
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
        for i in range(0, len(rows), BATCH):
            await session.execute(insert(SarActivityValueModel), rows[i : i + BATCH])

    async def count_values(self, projection_id: UUID, *, workspace_id: UUID) -> int:
        session = self._uow.session
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
        return int((await session.execute(stmt)).scalar_one())


def _to_model(p: SarActivityProjection) -> SarActivityProjectionModel:
    return SarActivityProjectionModel(
        id=p.id,
        workspace_id=p.workspace_id,
        requested_by=p.requested_by,
        membership_hash=p.membership_hash,
        channel_hash=p.channel_hash,
        channel_spec=dict(p.channel_spec),
        requested_at=p.requested_at,
        status=p.status.value,
        started_at=p.started_at,
        completed_at=p.completed_at,
        error_message=p.error_message,
        value_count=p.value_count,
        version=p.version,
    )


def _apply_to_model(model: SarActivityProjectionModel, p: SarActivityProjection) -> None:
    model.status = p.status.value
    model.started_at = p.started_at
    model.completed_at = p.completed_at
    model.error_message = p.error_message
    model.value_count = p.value_count
    model.version = p.version


def _to_domain(model: SarActivityProjectionModel) -> SarActivityProjection:
    return SarActivityProjection(
        id=model.id,
        workspace_id=model.workspace_id,
        requested_by=model.requested_by,
        membership_hash=model.membership_hash,
        channel_hash=model.channel_hash,
        channel_spec=dict(model.channel_spec or {}),
        requested_at=model.requested_at,
        status=SarActivityProjectionStatus(model.status),
        started_at=model.started_at,
        completed_at=model.completed_at,
        error_message=model.error_message,
        value_count=model.value_count,
        version=model.version,
    )
```

- [ ] **Step 4: Run the test to confirm it passes**

Run: `cd backend && uv run pytest tests/integration/persistence/sar_analysis/test_sar_activity_projection_repository.py -v && uv run lint-imports`
Expected: all PASS; import-linter clean.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(sar): SQLAlchemy activity-projection repository (cache + sparse values)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/sar_activity_projection_repository.py tests/integration/persistence/sar_analysis/test_sar_activity_projection_repository.py
```

---

## Task 9: Application — `RunActivityProjection`

The in-process runner the Temporal activity wraps; the Null orchestrator invokes inline. Mirrors `RunDecomposition`: load → `mark_running` (commit) → stream members → enrich per batch → `write_values` per batch → `mark_ready` (commit); on exception `mark_failed` + reraise.

**Files:**
- Create: `src/cellar/application/sar_analysis/run_activity_projection.py`
- Test: `tests/unit/application/sar_analysis/test_run_activity_projection.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/application/sar_analysis/test_run_activity_projection.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.application.sar_analysis.activity_channel import ActivityChannelSpec
from cellar.application.sar_analysis.run_activity_projection import RunActivityProjection
from cellar.domain.sar_analysis.sar_activity_projection import (
    SarActivityProjection,
    SarActivityProjectionStatus,
)
from cellar.domain.screening_assay.activity_types import ActivityValue
from cellar.domain.shared.aggregation_types import QualifierHandling, SelectionRule

_NOW = datetime(2026, 6, 15, tzinfo=UTC)
_COLUMN = "drc:" + str(uuid.uuid4())


def _channel_spec_dict() -> dict:
    return ActivityChannelSpec(
        column=_COLUMN,
        source="dr_curve",
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.EXCLUDE_QUALIFIED,
    ).to_spec_dict()


class FakeUoW:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        return []


class FakeRepo:
    def __init__(self, proj):
        self._by_id = {proj.id: proj} if proj else {}
        self.written: dict[uuid.UUID, list] = {}

    async def save(self, p):
        self._by_id[p.id] = p

    async def find_by_id(self, pid, *, workspace_id):
        p = self._by_id.get(pid)
        return p if p and p.workspace_id == workspace_id else None

    async def write_values(self, pid, values):
        self.written.setdefault(pid, []).extend(values)


class FakeEnricher:
    def __init__(self, table, *, raise_on_call=False):
        self._table = table
        self._raise = raise_on_call

    async def enrich_molecules(self, ws, ids, cols, *, selection_rule, qualifier_handling, run_scopes=None):
        if self._raise:
            raise RuntimeError("enrich boom")
        return {mid: self._table[mid] for mid in ids if mid in self._table}


class FakeStream:
    def __init__(self, batches):
        self._batches = batches

    async def stream(self, *, workspace_id, collection_id, molecule_ids):
        for b in self._batches:
            yield b


def _pending(ws) -> SarActivityProjection:
    return SarActivityProjection.create(
        workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
        channel_hash="ch", channel_spec=_channel_spec_dict(), now=_NOW,
    )


@pytest.mark.asyncio
async def test_run_marks_ready_with_value_count():
    ws = uuid.uuid4()
    proj = _pending(ws)
    a, b = uuid.uuid4(), uuid.uuid4()
    table = {
        a: {_COLUMN: ActivityValue(value=0.5, qualifier=None, unit="uM", source="dose_response")},
        b: {_COLUMN: ActivityValue(value=None, qualifier="nd", unit="uM", source="dose_response")},
    }
    repo = FakeRepo(proj)
    uc = RunActivityProjection(
        members=FakeStream([[(a, "Fc1ccccc1", 1), (b, "CCO", 1)]]),
        enricher=FakeEnricher(table),
        repository=repo,
        uow=FakeUoW(),
    )
    await uc.run(run_id=proj.id, workspace_id=ws, channel_spec=_channel_spec_dict(), molecule_ids=[a, b])
    saved = repo._by_id[proj.id]
    assert saved.status == SarActivityProjectionStatus.READY
    assert saved.value_count == 1  # only 'a' had a scalar (sparse)
    assert len(repo.written[proj.id]) == 1


@pytest.mark.asyncio
async def test_run_marks_failed_and_reraises():
    ws = uuid.uuid4()
    proj = _pending(ws)
    repo = FakeRepo(proj)
    uc = RunActivityProjection(
        members=FakeStream([[(uuid.uuid4(), "Fc1ccccc1", 1)]]),
        enricher=FakeEnricher({}, raise_on_call=True),
        repository=repo,
        uow=FakeUoW(),
    )
    with pytest.raises(RuntimeError, match="enrich boom"):
        await uc.run(run_id=proj.id, workspace_id=ws, channel_spec=_channel_spec_dict(), molecule_ids=[uuid.uuid4()])
    assert repo._by_id[proj.id].status == SarActivityProjectionStatus.FAILED


@pytest.mark.asyncio
async def test_run_skips_when_not_pending():
    ws = uuid.uuid4()
    cancelled = _pending(ws).mark_cancelled(_NOW)
    repo = FakeRepo(cancelled)
    uc = RunActivityProjection(
        members=FakeStream([]), enricher=FakeEnricher({}), repository=repo, uow=FakeUoW()
    )
    await uc.run(run_id=cancelled.id, workspace_id=ws, channel_spec=_channel_spec_dict(), molecule_ids=[])
    assert repo._by_id[cancelled.id].status == SarActivityProjectionStatus.CANCELLED
    assert repo.written == {}
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis/test_run_activity_projection.py -v`
Expected: FAIL — `ModuleNotFoundError: ...run_activity_projection`.

- [ ] **Step 3: Implement** (mirror `run_decomposition.py`)

Create `src/cellar/application/sar_analysis/run_activity_projection.py`:

```python
"""RunActivityProjection — in-process runner: load -> stream + enrich -> persist.

The Temporal activity wraps this; the Null orchestrator invokes it inline. Mirrors
RunDecomposition's state-machine handling. Members are re-streamed by source at run
time (workspace-scoped, no auth context). Each batch is enriched and its sparse
scalars are written immediately, so memory stays O(batch). The enricher shares the
runner's UoW so enrich + persist run on one session (wired in DI).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

from cellar.application.sar_analysis.activity_channel import ActivityChannelSpec
from cellar.application.sar_analysis.activity_enrichment import (
    MoleculeActivityEnricher,
    enrich_to_scalars,
)
from cellar.application.sar_analysis.decomposition_members import DecompositionMemberStream
from cellar.application.sar_analysis.repositories import SarActivityProjectionRepository
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.sar_activity_projection import SarActivityProjectionStatus

logger = structlog.get_logger(__name__)


@dataclass
class RunActivityProjection:
    members: DecompositionMemberStream
    enricher: MoleculeActivityEnricher
    repository: SarActivityProjectionRepository
    uow: UnitOfWork

    async def run(
        self,
        *,
        run_id: UUID,
        workspace_id: UUID,
        channel_spec: dict[str, Any],
        collection_id: UUID | None = None,
        molecule_ids: list[UUID] | None = None,
    ) -> None:
        log = logger.bind(projection_id=str(run_id), workspace_id=str(workspace_id))
        channel = ActivityChannelSpec.from_spec_dict(channel_spec)
        try:
            async with self.uow:
                proj = await self.repository.find_by_id(run_id, workspace_id=workspace_id)
                if proj is None:
                    log.error("sar_activity_projection_not_found")
                    return
                if proj.status != SarActivityProjectionStatus.PENDING:
                    log.info("sar_activity_projection_not_pending", status=str(proj.status))
                    return
                running = proj.mark_running(datetime.now(UTC))
                await self.repository.save(running)
                await self.uow.commit()

            async with self.uow:
                total = 0
                async for batch in self.members.stream(
                    workspace_id=workspace_id,
                    collection_id=collection_id,
                    molecule_ids=molecule_ids,
                ):
                    ids = [molecule_id for molecule_id, _smiles, _version in batch]
                    scalars = await enrich_to_scalars(
                        self.enricher, workspace_id=workspace_id, molecule_ids=ids, channel=channel
                    )
                    if scalars:
                        await self.repository.write_values(run_id, scalars)
                        total += len(scalars)
                ready = running.mark_ready(value_count=total, now=datetime.now(UTC))
                await self.repository.save(ready)
                await self.uow.commit()
            log.info("sar_activity_projection_ready", value_count=total)

        except Exception as exc:
            log.exception("sar_activity_projection_failed")
            try:
                async with self.uow:
                    current = await self.repository.find_by_id(run_id, workspace_id=workspace_id)
                    if current is not None and current.status == SarActivityProjectionStatus.RUNNING:
                        failed = current.mark_failed(str(exc), datetime.now(UTC))
                        await self.repository.save(failed)
                        await self.uow.commit()
            except Exception:
                log.exception("sar_activity_projection_fail_mark_failed")
            raise
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis/test_run_activity_projection.py -v && uv run lint-imports`
Expected: all PASS; import-linter clean.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(sar): RunActivityProjection runner (stream -> enrich -> persist)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/application/sar_analysis/run_activity_projection.py tests/unit/application/sar_analysis/test_run_activity_projection.py
```

---

## Task 10: Application — `StartActivityProjection`

Single entry point. One pass folds `membership_hash` over `(id, version)`, counts, buffers ids up to `inline_threshold`. Cache hit ⇒ prior READY; miss + ≤200 ⇒ enrich inline + persist READY; miss + >200 ⇒ persist PENDING + schedule with the **source** + channel spec. Declares the `SarActivityProjectionOrchestrator` Protocol.

**Files:**
- Create: `src/cellar/application/sar_analysis/start_activity_projection.py`
- Test: `tests/unit/application/sar_analysis/test_start_activity_projection.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/application/sar_analysis/test_start_activity_projection.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.application.sar_analysis.activity_channel import ActivityChannelSpec
from cellar.application.sar_analysis.start_activity_projection import (
    StartActivityProjection,
    StartActivityProjectionInput,
)
from cellar.domain.sar_analysis.sar_activity_projection import (
    SarActivityProjection,
    SarActivityProjectionStatus,
)
from cellar.domain.screening_assay.activity_types import ActivityValue
from cellar.domain.shared.aggregation_types import QualifierHandling, SelectionRule

_NOW = datetime(2026, 6, 15, tzinfo=UTC)
_COLUMN = "drc:" + str(uuid.uuid4())


def _channel() -> ActivityChannelSpec:
    return ActivityChannelSpec(
        column=_COLUMN, source="dr_curve",
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.EXCLUDE_QUALIFIED,
    )


class FakeUoW:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        return []


class FakeRepo:
    def __init__(self, cached=None):
        self._by_id = {}
        self._cached = cached
        self.written = {}

    async def save(self, p):
        self._by_id[p.id] = p

    async def find_by_id(self, pid, *, workspace_id):
        return self._by_id.get(pid)

    async def find_cached(self, *, membership_hash, channel_hash):
        return self._cached

    async def write_values(self, pid, values):
        self.written.setdefault(pid, []).extend(values)


class FakeEnricher:
    def __init__(self, table):
        self._table = table

    async def enrich_molecules(self, ws, ids, cols, *, selection_rule, qualifier_handling, run_scopes=None):
        return {mid: self._table[mid] for mid in ids if mid in self._table}


class FakeStream:
    def __init__(self, batches):
        self._batches = batches

    async def stream(self, *, workspace_id, collection_id, molecule_ids):
        for b in self._batches:
            yield b


class FakeOrchestrator:
    def __init__(self):
        self.scheduled = []

    async def schedule(self, *, projection_id, workspace_id, channel_spec, collection_id=None, molecule_ids=None):
        self.scheduled.append(
            {"projection_id": projection_id, "collection_id": collection_id, "channel_spec": channel_spec}
        )

    async def cancel(self, *, projection_id):
        pass


def _input(ws, *, collection_id=None, molecule_ids=None):
    return StartActivityProjectionInput(
        workspace_id=ws, requested_by=uuid.uuid4(),
        collection_id=collection_id, molecule_ids=molecule_ids,
        channel=_channel(), now=_NOW,
    )


@pytest.mark.asyncio
async def test_cache_hit_returns_prior_ready_without_compute():
    ws = uuid.uuid4()
    prior = (
        SarActivityProjection.create(
            workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
            channel_hash="ch", channel_spec={"column": _COLUMN}, now=_NOW,
        )
        .mark_running(_NOW)
        .mark_ready(value_count=5, now=_NOW)
    )
    repo = FakeRepo(cached=prior)
    orch = FakeOrchestrator()
    a = uuid.uuid4()
    uc = StartActivityProjection(
        members=FakeStream([[(a, "Fc1ccccc1", 1)]]),
        enricher=FakeEnricher({}), repository=repo, orchestrator=orch, uow=FakeUoW(),
    )
    out = await uc.execute(_input(ws, molecule_ids=[a]))
    assert out.id == prior.id and out.status == SarActivityProjectionStatus.READY
    assert orch.scheduled == [] and repo.written == {}


@pytest.mark.asyncio
async def test_inline_path_enriches_and_persists_ready():
    ws = uuid.uuid4()
    a, b = uuid.uuid4(), uuid.uuid4()
    table = {
        a: {_COLUMN: ActivityValue(value=0.5, qualifier=None, unit="uM", source="dose_response")},
        b: {_COLUMN: ActivityValue(value=None, qualifier="nd", unit="uM", source="dose_response")},
    }
    repo = FakeRepo(cached=None)
    orch = FakeOrchestrator()
    uc = StartActivityProjection(
        members=FakeStream([[(a, "Fc1ccccc1", 1), (b, "CCO", 1)]]),
        enricher=FakeEnricher(table), repository=repo, orchestrator=orch, uow=FakeUoW(),
        inline_threshold=200,
    )
    out = await uc.execute(_input(ws, molecule_ids=[a, b]))
    assert out.status == SarActivityProjectionStatus.READY
    assert out.value_count == 1  # sparse — only 'a'
    assert len(repo.written[out.id]) == 1
    assert orch.scheduled == []


@pytest.mark.asyncio
async def test_async_path_schedules_pending_with_source():
    ws, cid = uuid.uuid4(), uuid.uuid4()
    batch = [(uuid.uuid4(), "Fc1ccccc1", 1) for _ in range(3)]
    repo = FakeRepo(cached=None)
    orch = FakeOrchestrator()
    uc = StartActivityProjection(
        members=FakeStream([batch]),
        enricher=FakeEnricher({}), repository=repo, orchestrator=orch, uow=FakeUoW(),
        inline_threshold=2,
    )
    out = await uc.execute(_input(ws, collection_id=cid))
    assert out.status == SarActivityProjectionStatus.PENDING
    assert repo.written == {}
    assert len(orch.scheduled) == 1
    assert orch.scheduled[0]["collection_id"] == cid  # source passed, not expanded ids
    assert orch.scheduled[0]["channel_spec"]["column"] == _COLUMN


@pytest.mark.asyncio
async def test_empty_input_yields_ready_empty():
    ws = uuid.uuid4()
    repo = FakeRepo(cached=None)
    uc = StartActivityProjection(
        members=FakeStream([]), enricher=FakeEnricher({}),
        repository=repo, orchestrator=FakeOrchestrator(), uow=FakeUoW(),
    )
    out = await uc.execute(_input(ws, molecule_ids=[]))
    assert out.status == SarActivityProjectionStatus.READY
    assert out.value_count == 0
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis/test_start_activity_projection.py -v`
Expected: FAIL — `ModuleNotFoundError: ...start_activity_projection`.

- [ ] **Step 3: Implement** (mirror `start_decomposition_run.py`)

Create `src/cellar/application/sar_analysis/start_activity_projection.py`:

```python
"""StartActivityProjection — single entry point for the activity-projection endpoint.

Dispatches one of three paths (mirrors StartDecompositionRun):
1. Cache hit (any size)            -> return the prior READY projection header.
2. Cache miss, <= inline_threshold -> enrich inline, persist a READY projection.
3. Cache miss, > inline_threshold  -> persist PENDING + schedule the workflow.

A single pass over the member stream folds ``membership_hash`` over ``(id, version)``,
counts members, and buffers ids only up to the inline threshold. The job is
scheduled with the **source** (``collection_id`` or a bounded id list) + the channel
spec, never the expanded membership.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from cellar.application.sar_analysis.activity_channel import ActivityChannelSpec, channel_hash
from cellar.application.sar_analysis.activity_enrichment import (
    MoleculeActivityEnricher,
    enrich_to_scalars,
)
from cellar.application.sar_analysis.decomposition_members import DecompositionMemberStream
from cellar.application.sar_analysis.hashing import compute_membership_hash
from cellar.application.sar_analysis.repositories import SarActivityProjectionRepository
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.sar_activity_projection import SarActivityProjection


@dataclass(frozen=True)
class StartActivityProjectionInput:
    workspace_id: UUID
    requested_by: UUID
    collection_id: UUID | None
    molecule_ids: list[UUID] | None
    channel: ActivityChannelSpec
    now: datetime


class SarActivityProjectionOrchestrator(Protocol):
    async def schedule(
        self,
        *,
        projection_id: UUID,
        workspace_id: UUID,
        channel_spec: dict[str, Any],
        collection_id: UUID | None = None,
        molecule_ids: list[UUID] | None = None,
    ) -> None: ...

    async def cancel(self, *, projection_id: UUID) -> None: ...


class StartActivityProjection:
    def __init__(
        self,
        *,
        members: DecompositionMemberStream,
        enricher: MoleculeActivityEnricher,
        repository: SarActivityProjectionRepository,
        orchestrator: SarActivityProjectionOrchestrator,
        uow: UnitOfWork,
        inline_threshold: int = 200,
    ) -> None:
        self._members = members
        self._enricher = enricher
        self._repo = repository
        self._orchestrator = orchestrator
        self._uow = uow
        self._inline_threshold = inline_threshold

    async def execute(self, payload: StartActivityProjectionInput) -> SarActivityProjection:
        ch_hash = channel_hash(payload.channel)
        spec_dict = payload.channel.to_spec_dict()

        async with self._uow:
            pairs, buffer_ids, count = await self._collect(payload)
            membership_hash = compute_membership_hash(pairs)

            cached = await self._repo.find_cached(
                membership_hash=membership_hash, channel_hash=ch_hash
            )
            if cached is not None:
                return cached

            proj = SarActivityProjection.create(
                workspace_id=payload.workspace_id,
                requested_by=payload.requested_by,
                membership_hash=membership_hash,
                channel_hash=ch_hash,
                channel_spec=spec_dict,
                now=payload.now,
            )

            if count <= self._inline_threshold:
                running = proj.mark_running(payload.now)
                await self._repo.save(running)
                await self._uow.commit()  # projection row must exist before value FKs

                scalars = await enrich_to_scalars(
                    self._enricher,
                    workspace_id=payload.workspace_id,
                    molecule_ids=buffer_ids,
                    channel=payload.channel,
                )
                await self._repo.write_values(proj.id, scalars)
                ready = running.mark_ready(value_count=len(scalars), now=payload.now)
                await self._repo.save(ready)
                await self._uow.commit()
                return ready

            await self._repo.save(proj)
            await self._uow.commit()

        await self._orchestrator.schedule(
            projection_id=proj.id,
            workspace_id=payload.workspace_id,
            channel_spec=spec_dict,
            collection_id=payload.collection_id,
            molecule_ids=payload.molecule_ids,
        )
        return proj

    async def _collect(
        self, payload: StartActivityProjectionInput
    ) -> tuple[list[tuple[UUID, int]], list[UUID], int]:
        """One pass: fold (id, version) for the hash, count, buffer ids only while
        at/under the inline threshold (so a huge collection is hashed/counted
        without materializing its ids)."""
        pairs: list[tuple[UUID, int]] = []
        buffer: list[UUID] = []
        overflowed = False
        async for batch in self._members.stream(
            workspace_id=payload.workspace_id,
            collection_id=payload.collection_id,
            molecule_ids=payload.molecule_ids,
        ):
            for molecule_id, _smiles, version in batch:
                pairs.append((molecule_id, version))
                if not overflowed:
                    buffer.append(molecule_id)
                    if len(buffer) > self._inline_threshold:
                        overflowed = True
                        buffer = []  # release — this projection will be async
        return pairs, buffer, len(pairs)
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis/test_start_activity_projection.py -v && uv run lint-imports`
Expected: all PASS; import-linter clean.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(sar): StartActivityProjection use case (cache/inline/async)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/application/sar_analysis/start_activity_projection.py tests/unit/application/sar_analysis/test_start_activity_projection.py
```

---

## Task 11: Application — `GetActivityProjection` + `CancelActivityProjection`

**Files:**
- Create: `src/cellar/application/sar_analysis/get_activity_projection.py`
- Create: `src/cellar/application/sar_analysis/cancel_activity_projection.py`
- Test: `tests/unit/application/sar_analysis/test_get_cancel_activity_projection.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/application/sar_analysis/test_get_cancel_activity_projection.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from returns.result import Failure, Success

from cellar.application.sar_analysis.cancel_activity_projection import (
    CancelActivityProjection,
    CancelActivityProjectionInput,
)
from cellar.application.sar_analysis.get_activity_projection import (
    GetActivityProjection,
    GetActivityProjectionInput,
)
from cellar.domain.sar_analysis.sar_activity_projection import (
    SarActivityProjection,
    SarActivityProjectionStatus,
)

_NOW = datetime(2026, 6, 15, tzinfo=UTC)


class FakeUoW:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        return []


class FakeRepo:
    def __init__(self, proj=None):
        self._by_id = {proj.id: proj} if proj else {}

    async def save(self, p):
        self._by_id[p.id] = p

    async def find_by_id(self, pid, *, workspace_id):
        p = self._by_id.get(pid)
        return p if p and p.workspace_id == workspace_id else None


class FakeOrchestrator:
    def __init__(self):
        self.cancelled = []

    async def schedule(self, **kw):
        pass

    async def cancel(self, *, projection_id):
        self.cancelled.append(projection_id)


def _pending(ws):
    return SarActivityProjection.create(
        workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
        channel_hash="ch", channel_spec={"column": "drc:x"}, now=_NOW,
    )


@pytest.mark.asyncio
async def test_get_returns_projection():
    ws = uuid.uuid4()
    proj = _pending(ws)
    uc = GetActivityProjection(repository=FakeRepo(proj), uow=FakeUoW())
    out = await uc.execute(GetActivityProjectionInput(projection_id=proj.id, workspace_id=ws))
    assert isinstance(out, Success)
    assert out.unwrap().id == proj.id


@pytest.mark.asyncio
async def test_get_missing_is_failure():
    uc = GetActivityProjection(repository=FakeRepo(None), uow=FakeUoW())
    out = await uc.execute(GetActivityProjectionInput(projection_id=uuid.uuid4(), workspace_id=uuid.uuid4()))
    assert isinstance(out, Failure)


@pytest.mark.asyncio
async def test_cancel_marks_cancelled_and_signals_orchestrator():
    ws = uuid.uuid4()
    proj = _pending(ws)
    repo = FakeRepo(proj)
    orch = FakeOrchestrator()
    uc = CancelActivityProjection(repository=repo, orchestrator=orch, uow=FakeUoW())
    out = await uc.execute(CancelActivityProjectionInput(projection_id=proj.id, workspace_id=ws, now=_NOW))
    assert isinstance(out, Success)
    assert repo._by_id[proj.id].status == SarActivityProjectionStatus.CANCELLED
    assert orch.cancelled == [proj.id]


@pytest.mark.asyncio
async def test_cancel_already_terminal_is_idempotent_noop():
    ws = uuid.uuid4()
    ready = _pending(ws).mark_running(_NOW).mark_ready(value_count=0, now=_NOW)
    repo = FakeRepo(ready)
    orch = FakeOrchestrator()
    uc = CancelActivityProjection(repository=repo, orchestrator=orch, uow=FakeUoW())
    out = await uc.execute(CancelActivityProjectionInput(projection_id=ready.id, workspace_id=ws, now=_NOW))
    assert isinstance(out, Success)
    assert repo._by_id[ready.id].status == SarActivityProjectionStatus.READY  # unchanged


@pytest.mark.asyncio
async def test_cancel_missing_is_failure():
    uc = CancelActivityProjection(repository=FakeRepo(None), orchestrator=FakeOrchestrator(), uow=FakeUoW())
    out = await uc.execute(CancelActivityProjectionInput(projection_id=uuid.uuid4(), workspace_id=uuid.uuid4(), now=_NOW))
    assert isinstance(out, Failure)
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis/test_get_cancel_activity_projection.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement Get** (mirror `get_decomposition_run.py`)

Create `src/cellar/application/sar_analysis/get_activity_projection.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from returns.result import Failure, Result, Success

from cellar.application.sar_analysis.repositories import SarActivityProjectionRepository
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.sar_activity_projection import SarActivityProjection
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True)
class GetActivityProjectionInput:
    projection_id: UUID
    workspace_id: UUID


class GetActivityProjection:
    def __init__(self, *, repository: SarActivityProjectionRepository, uow: UnitOfWork) -> None:
        self._repo = repository
        self._uow = uow

    async def execute(
        self, payload: GetActivityProjectionInput
    ) -> Result[SarActivityProjection, DomainError]:
        async with self._uow:
            proj = await self._repo.find_by_id(
                payload.projection_id, workspace_id=payload.workspace_id
            )
        if proj is None:
            return Failure(NotFoundError("SarActivityProjection", str(payload.projection_id)))
        return Success(proj)
```

- [ ] **Step 4: Implement Cancel** (mirror `cancel_decomposition_run.py`)

Create `src/cellar/application/sar_analysis/cancel_activity_projection.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from returns.result import Failure, Result, Success

from cellar.application.sar_analysis.repositories import SarActivityProjectionRepository
from cellar.application.sar_analysis.start_activity_projection import (
    SarActivityProjectionOrchestrator,
)
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.sar_activity_projection import (
    InvalidSarProjectionTransition,
    SarActivityProjection,
)
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True)
class CancelActivityProjectionInput:
    projection_id: UUID
    workspace_id: UUID
    now: datetime


class CancelActivityProjection:
    def __init__(
        self,
        *,
        repository: SarActivityProjectionRepository,
        orchestrator: SarActivityProjectionOrchestrator,
        uow: UnitOfWork,
    ) -> None:
        self._repo = repository
        self._orchestrator = orchestrator
        self._uow = uow

    async def execute(
        self, payload: CancelActivityProjectionInput
    ) -> Result[SarActivityProjection, DomainError]:
        async with self._uow:
            proj = await self._repo.find_by_id(
                payload.projection_id, workspace_id=payload.workspace_id
            )
            if proj is None:
                return Failure(NotFoundError("SarActivityProjection", str(payload.projection_id)))
            try:
                cancelled = proj.mark_cancelled(payload.now)
            except InvalidSarProjectionTransition:
                return Success(proj)  # already terminal — idempotent no-op
            await self._repo.save(cancelled)
            await self._uow.commit()
        await self._orchestrator.cancel(projection_id=proj.id)
        return Success(cancelled)
```

- [ ] **Step 5: Run the tests to confirm they pass**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis/test_get_cancel_activity_projection.py -v && uv run lint-imports`
Expected: all PASS; import-linter clean.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(sar): Get + Cancel activity projection use cases" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/application/sar_analysis/get_activity_projection.py src/cellar/application/sar_analysis/cancel_activity_projection.py tests/unit/application/sar_analysis/test_get_cancel_activity_projection.py
```

---

## Task 12: Infra — Temporal workflow + activity + orchestrators

**Files:**
- Create: `src/cellar/infrastructure/temporal/workflows/sar_activity_projection.py`
- Create: `src/cellar/infrastructure/temporal/activities/sar_activity_projection.py`
- Create: `src/cellar/infrastructure/temporal/orchestrators/sar_activity_projection.py`
- Test: `tests/unit/infrastructure/temporal/test_sar_activity_projection_orchestrators.py`

- [ ] **Step 1: Write the failing orchestrator test** (mirror `test_rgroup_decomposition_orchestrators.py`)

Create `tests/unit/infrastructure/temporal/test_sar_activity_projection_orchestrators.py`:

```python
from __future__ import annotations

import asyncio
import uuid

import pytest

from cellar.infrastructure.temporal.orchestrators.sar_activity_projection import (
    NullSarActivityProjectionOrchestrator,
)


class FakeRunner:
    def __init__(self):
        self.calls = []

    async def run(self, *, run_id, workspace_id, channel_spec, collection_id=None, molecule_ids=None):
        self.calls.append(
            {"run_id": run_id, "channel_spec": channel_spec, "collection_id": collection_id, "molecule_ids": molecule_ids}
        )


@pytest.mark.asyncio
async def test_null_orchestrator_runs_inline_as_background_task():
    runner = FakeRunner()
    orch = NullSarActivityProjectionOrchestrator(runner)
    pid = uuid.uuid4()
    await orch.schedule(
        projection_id=pid, workspace_id=uuid.uuid4(),
        channel_spec={"column": "drc:x"}, collection_id=uuid.uuid4(),
    )
    assert orch._tasks, "schedule should have spawned a background task"
    await asyncio.gather(*list(orch._tasks))
    assert runner.calls and runner.calls[0]["run_id"] == pid
    assert runner.calls[0]["channel_spec"] == {"column": "drc:x"}


@pytest.mark.asyncio
async def test_null_orchestrator_cancel_is_noop():
    orch = NullSarActivityProjectionOrchestrator(FakeRunner())
    assert await orch.cancel(projection_id=uuid.uuid4()) is None
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/unit/infrastructure/temporal/test_sar_activity_projection_orchestrators.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the workflow** (mirror `workflows/rgroup_decomposition.py`)

Create `src/cellar/infrastructure/temporal/workflows/sar_activity_projection.py`:

```python
"""SarActivityProjectionWorkflow — durable single-activity wrapper for
RunActivityProjection. The 1-hour timeout is generous because the activity
re-expands the membership and enriches it. Timeout + retry are baked into history
at schedule time (changing them later does not affect in-flight workflows)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from cellar.infrastructure.temporal.activities.sar_activity_projection import (
        RunActivityProjectionInput,
        SarActivityProjectionActivities,
    )


@dataclass
class SarActivityProjectionWorkflowInput:
    projection_id: str
    workspace_id: str
    channel_spec: dict[str, Any]
    collection_id: str | None = None
    molecule_ids: list[str] = field(default_factory=list)


@workflow.defn
class SarActivityProjectionWorkflow:
    @workflow.run
    async def run(self, input: SarActivityProjectionWorkflowInput) -> None:
        await workflow.execute_activity(
            SarActivityProjectionActivities.run_sar_activity_projection,
            RunActivityProjectionInput(
                projection_id=input.projection_id,
                workspace_id=input.workspace_id,
                channel_spec=input.channel_spec,
                collection_id=input.collection_id,
                molecule_ids=input.molecule_ids,
            ),
            start_to_close_timeout=timedelta(hours=1),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
```

- [ ] **Step 4: Implement the activity** (mirror `activities/rgroup_decomposition.py`)

Create `src/cellar/infrastructure/temporal/activities/sar_activity_projection.py`:

```python
"""SarActivityProjectionActivities — Temporal activity delegating to
RunActivityProjection. The source (collection_id XOR molecule_ids) crosses the
boundary as strings; the channel spec crosses as a JSON dict."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from temporalio import activity

from cellar.application.sar_analysis.run_activity_projection import RunActivityProjection


@dataclass
class RunActivityProjectionInput:
    projection_id: str
    workspace_id: str
    channel_spec: dict[str, Any]
    collection_id: str | None = None
    molecule_ids: list[str] = field(default_factory=list)


class SarActivityProjectionActivities:
    def __init__(self, run_activity_projection: RunActivityProjection) -> None:
        self._run = run_activity_projection

    @activity.defn
    async def run_sar_activity_projection(self, input: RunActivityProjectionInput) -> None:
        collection_id = uuid.UUID(input.collection_id) if input.collection_id else None
        molecule_ids = [uuid.UUID(m) for m in input.molecule_ids] if input.molecule_ids else None
        await self._run.run(
            run_id=uuid.UUID(input.projection_id),
            workspace_id=uuid.UUID(input.workspace_id),
            channel_spec=input.channel_spec,
            collection_id=collection_id,
            molecule_ids=molecule_ids,
        )
```

- [ ] **Step 5: Implement the orchestrators** (mirror `orchestrators/rgroup_decomposition.py`)

Create `src/cellar/infrastructure/temporal/orchestrators/sar_activity_projection.py`:

```python
"""Orchestrator implementations for the SAR activity-projection workflow.

``TemporalSarActivityProjectionOrchestrator`` submits the workflow and cancels via
handle. ``NullSarActivityProjectionOrchestrator`` runs RunActivityProjection inline
as a fire-and-forget asyncio task (dev / tests). Mirrors rgroup_decomposition exactly.
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol
from uuid import UUID

from temporalio.client import Client

from cellar.application.sar_analysis.run_activity_projection import RunActivityProjection
from cellar.infrastructure.temporal.task_queues import MAIN_TASK_QUEUE
from cellar.infrastructure.temporal.workflows.sar_activity_projection import (
    SarActivityProjectionWorkflow,
    SarActivityProjectionWorkflowInput,
)


class SarActivityProjectionRunner(Protocol):
    async def run(
        self,
        *,
        run_id: UUID,
        workspace_id: UUID,
        channel_spec: dict[str, Any],
        collection_id: UUID | None = None,
        molecule_ids: list[UUID] | None = None,
    ) -> None: ...


class TemporalSarActivityProjectionOrchestrator:
    def __init__(self, client: Client) -> None:
        self._client = client

    async def schedule(
        self,
        *,
        projection_id: UUID,
        workspace_id: UUID,
        channel_spec: dict[str, Any],
        collection_id: UUID | None = None,
        molecule_ids: list[UUID] | None = None,
    ) -> None:
        await self._client.start_workflow(
            SarActivityProjectionWorkflow.run,
            SarActivityProjectionWorkflowInput(
                projection_id=str(projection_id),
                workspace_id=str(workspace_id),
                channel_spec=channel_spec,
                collection_id=str(collection_id) if collection_id is not None else None,
                molecule_ids=[str(m) for m in (molecule_ids or [])],
            ),
            id=f"sar-activity-projection-{projection_id}",
            task_queue=MAIN_TASK_QUEUE,
        )

    async def cancel(self, *, projection_id: UUID) -> None:
        handle = self._client.get_workflow_handle(f"sar-activity-projection-{projection_id}")
        await handle.cancel()


class NullSarActivityProjectionOrchestrator:
    """In-process fallback when Temporal is unavailable."""

    def __init__(self, runner: SarActivityProjectionRunner | RunActivityProjection) -> None:
        self._runner = runner
        self._tasks: set[asyncio.Task] = set()

    async def schedule(
        self,
        *,
        projection_id: UUID,
        workspace_id: UUID,
        channel_spec: dict[str, Any],
        collection_id: UUID | None = None,
        molecule_ids: list[UUID] | None = None,
    ) -> None:
        task = asyncio.create_task(
            self._runner.run(
                run_id=projection_id,
                workspace_id=workspace_id,
                channel_spec=channel_spec,
                collection_id=collection_id,
                molecule_ids=molecule_ids,
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def cancel(self, *, projection_id: UUID) -> None:
        return None  # inline tasks cannot be cancelled by id
```

- [ ] **Step 6: Run the tests to confirm they pass**

Run: `cd backend && uv run pytest tests/unit/infrastructure/temporal/test_sar_activity_projection_orchestrators.py -v && uv run lint-imports`
Expected: all PASS; import-linter clean.

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(sar): Temporal workflow + activity + orchestrators for activity projection" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/infrastructure/temporal/workflows/sar_activity_projection.py src/cellar/infrastructure/temporal/activities/sar_activity_projection.py src/cellar/infrastructure/temporal/orchestrators/sar_activity_projection.py tests/unit/infrastructure/temporal/test_sar_activity_projection_orchestrators.py
```

---

## Task 13: Infra — DI wiring + worker + lifespan binding

Wire the projection slice into `_sar_analysis.py` (mirroring the decomposition block), register the workflow + activity in the worker, and bind the live/null orchestrator in `app.py`'s lifespan. **The enricher (`MoleculeActivityService`) is constructed with the runner's shared UoW** so enrich + persist run on one session.

**Files:**
- Modify: `src/cellar/infrastructure/di/_sar_analysis.py`
- Modify: `src/cellar/infrastructure/temporal/worker.py`
- Modify: `src/cellar/interface/app.py`
- Modify: `tests/unit/infrastructure/di/test_sar_analysis_wiring.py`

- [ ] **Step 1: Add the wiring assertions (failing test first)**

Append a test method to the `TestSarAnalysisWiring` class in `tests/unit/infrastructure/di/test_sar_analysis_wiring.py`:

```python
    def test_activity_projection_use_cases_resolve_with_temporal_disabled(
        self, test_settings: DatabaseSettings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Start/Cancel depend on SarActivityProjectionOrchestrator; under
        # TEMPORAL_DISABLED=1 _sar_analysis binds the Null one. RunActivityProjection
        # is what that Null wraps; FetchActivityHeatmap has no orchestrator dep.
        monkeypatch.setenv("TEMPORAL_DISABLED", "1")
        from cellar.application.sar_analysis.cancel_activity_projection import (
            CancelActivityProjection,
        )
        from cellar.application.sar_analysis.get_activity_projection import GetActivityProjection
        from cellar.application.sar_analysis.run_activity_projection import RunActivityProjection
        from cellar.application.sar_analysis.start_activity_projection import (
            SarActivityProjectionOrchestrator,
            StartActivityProjection,
        )

        container = create_container(test_settings)
        assert isinstance(container[RunActivityProjection], RunActivityProjection)
        assert isinstance(container[StartActivityProjection], StartActivityProjection)
        assert isinstance(container[GetActivityProjection], GetActivityProjection)
        assert isinstance(container[CancelActivityProjection], CancelActivityProjection)
        orch = container[SarActivityProjectionOrchestrator]
        assert orch.__class__.__name__ == "NullSarActivityProjectionOrchestrator"
```

(The `FetchActivityHeatmap` resolution is asserted separately in Task 14, after its module + DI registration land — keeping this task independently green.)

Run: `cd backend && uv run pytest tests/unit/infrastructure/di/test_sar_analysis_wiring.py -k activity_projection -v`
Expected: FAIL — `ModuleNotFoundError` (the projection use cases don't exist as DI bindings yet). Passes after Step 2 below.

- [ ] **Step 2: Extend `_sar_analysis.py`** — add imports (top of file, with the other sar imports):

```python
from cellar.application.sar_analysis.cancel_activity_projection import CancelActivityProjection
from cellar.application.sar_analysis.get_activity_projection import GetActivityProjection
from cellar.application.sar_analysis.run_activity_projection import RunActivityProjection
from cellar.application.sar_analysis.start_activity_projection import (
    SarActivityProjectionOrchestrator,
    StartActivityProjection,
)
from cellar.application.sar_analysis.repositories import SarActivityProjectionRepository  # add to existing repositories import group
from cellar.application.screening.molecule_activity_service import MoleculeActivityService
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_repository import (  # noqa: E501
    SQLAlchemySarActivityProjectionRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (  # noqa: E501
    SQLAlchemyDoseResponseCurveRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.readout_data_repository import (
    SQLAlchemyReadoutDataRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.run_repository import (
    SQLAlchemyRunRepository,
)
```

Then, inside `register_sar_analysis(container)`, add this block **after** the decomposition use-case registrations (after `container.define(FetchDecompositionRows, _fetch_decomposition_rows)`):

```python
    # =====================================================================
    # Activity projection slice (mirrors the decomposition slice above)
    # =====================================================================

    def _activity_projection_repo(c: Container) -> SarActivityProjectionRepository:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SQLAlchemySarActivityProjectionRepository(uow)  # type: ignore[return-value]

    container.define(SarActivityProjectionRepository, _activity_projection_repo)

    def _activity_enricher(uow: AsyncUnitOfWork) -> MoleculeActivityService:
        # Shares the caller's UoW so enrich reads + value writes run on one session.
        return MoleculeActivityService(
            uow=uow,
            readout_repo=SQLAlchemyReadoutDataRepository(uow),
            curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            run_repo=SQLAlchemyRunRepository(uow),
        )

    def _run_activity_projection(c: Container) -> RunActivityProjection:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        members = DecompositionMemberStream(
            molecule_fetcher=SQLAlchemyMoleculeRepository(uow),
            collection_reader=SQLAlchemyCollectionRepository(uow),
        )
        return RunActivityProjection(
            members=members,
            enricher=_activity_enricher(uow),
            repository=SQLAlchemySarActivityProjectionRepository(uow),
            uow=uow,
        )

    container.define(RunActivityProjection, _run_activity_projection)

    if os.environ.get("TEMPORAL_DISABLED") == "1":
        from cellar.infrastructure.temporal.orchestrators.sar_activity_projection import (
            NullSarActivityProjectionOrchestrator,
        )

        def _null_activity_orchestrator(c: Container) -> NullSarActivityProjectionOrchestrator:
            return NullSarActivityProjectionOrchestrator(c[RunActivityProjection])

        container.define(SarActivityProjectionOrchestrator, _null_activity_orchestrator)

    def _start_activity_projection(c: Container) -> StartActivityProjection:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        members = DecompositionMemberStream(
            molecule_fetcher=SQLAlchemyMoleculeRepository(uow),
            collection_reader=SQLAlchemyCollectionRepository(uow),
        )
        return StartActivityProjection(
            members=members,
            enricher=_activity_enricher(uow),
            repository=SQLAlchemySarActivityProjectionRepository(uow),
            orchestrator=c[SarActivityProjectionOrchestrator],
            uow=uow,
        )

    def _get_activity_projection(c: Container) -> GetActivityProjection:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetActivityProjection(
            repository=SQLAlchemySarActivityProjectionRepository(uow), uow=uow
        )

    def _cancel_activity_projection(c: Container) -> CancelActivityProjection:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CancelActivityProjection(
            repository=SQLAlchemySarActivityProjectionRepository(uow),
            orchestrator=c[SarActivityProjectionOrchestrator],
            uow=uow,
        )

    container.define(StartActivityProjection, _start_activity_projection)
    container.define(GetActivityProjection, _get_activity_projection)
    container.define(CancelActivityProjection, _cancel_activity_projection)
    # NOTE: FetchActivityHeatmap is registered in Task 14 (its module lands there).
```

- [ ] **Step 3: Extend `worker.py`** — add imports next to the rgroup ones (inside `run_worker`):

```python
    from cellar.application.sar_analysis.run_activity_projection import RunActivityProjection
    from cellar.infrastructure.temporal.activities.sar_activity_projection import (
        SarActivityProjectionActivities,
    )
    from cellar.infrastructure.temporal.workflows.sar_activity_projection import (
        SarActivityProjectionWorkflow,
    )
```

After `rgroup_decomposition_activities = RGroupDecompositionActivities(run_rgroup_decomposition)`, add:

```python
    # --- SAR activity projection activity ---
    run_sar_activity_projection = container[RunActivityProjection]
    sar_activity_projection_activities = SarActivityProjectionActivities(run_sar_activity_projection)
```

Add `SarActivityProjectionWorkflow,` to the `workflows=[...]` list (after `RGroupDecompositionWorkflow,`) and `sar_activity_projection_activities.run_sar_activity_projection,` to the `activities=[...]` list (after the R-group decomposition activity, with a `# SAR activity projection` comment).

- [ ] **Step 4: Extend `app.py` lifespan** — add the orchestrator import next to the rgroup one (~line 97):

```python
        from cellar.infrastructure.temporal.orchestrators.sar_activity_projection import (
            NullSarActivityProjectionOrchestrator,
            TemporalSarActivityProjectionOrchestrator,
        )
```

Import the application Protocol next to `RGroupDecompositionOrchestrator` (~line 76):

```python
        from cellar.application.sar_analysis.start_activity_projection import (
            SarActivityProjectionOrchestrator,
        )
```

In the `if app.state.temporal_client is not None:` branch (after `rgroup_orch = TemporalRGroupDecompositionOrchestrator(...)`):

```python
            activity_proj_orch: SarActivityProjectionOrchestrator = (
                TemporalSarActivityProjectionOrchestrator(app.state.temporal_client)
            )
```

In the `else:` branch (after `rgroup_orch = NullRGroupDecompositionOrchestrator(container[RunDecomposition])`), add the import + binding:

```python
            from cellar.application.sar_analysis.run_activity_projection import (
                RunActivityProjection,
            )

            activity_proj_orch = NullSarActivityProjectionOrchestrator(
                container[RunActivityProjection]
            )
```

After `container.define(RGroupDecompositionOrchestrator, Singleton(lambda: rgroup_orch))`:

```python
        container.define(
            SarActivityProjectionOrchestrator, Singleton(lambda: activity_proj_orch)
        )
```

- [ ] **Step 5: Run wiring + a smoke import of the worker + app**

Run:
```bash
cd backend && TEMPORAL_DISABLED=1 uv run pytest tests/unit/infrastructure/di/test_sar_analysis_wiring.py -v && uv run python -c "import cellar.infrastructure.temporal.worker, cellar.interface.app; print('imports ok')" && uv run lint-imports
```
Expected: all wiring tests PASS (the projection use cases resolve; the heatmap assertion lands in Task 14); worker + app import cleanly; import-linter clean.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(sar): DI wiring + worker + lifespan binding for activity projection" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/infrastructure/di/_sar_analysis.py src/cellar/infrastructure/temporal/worker.py src/cellar/interface/app.py tests/unit/infrastructure/di/test_sar_analysis_wiring.py
```

---

## Task 14: Heatmap — application contract + SQL reader

The server-aggregated heatmap: `GROUP BY (rgroups->>axis_y, rgroups->>axis_x)` over `assignment ⋈ activity_value ⋈ molecules`, `argmin(scalar)` per cell (lower-is-better), each axis capped to the **top-30 substituents by member count** with honest totals.

**Files:**
- Create: `src/cellar/application/sar_analysis/activity_heatmap.py`
- Create: `src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/activity_heatmap_reader.py`
- Test: `tests/integration/persistence/sar_analysis/test_activity_heatmap_reader.py`

- [ ] **Step 1: Write the application contract** (no test yet — pure dataclasses + Protocol + use case)

Create `src/cellar/application/sar_analysis/activity_heatmap.py`:

```python
"""Read contract for the server-aggregated activity heatmap.

One ``GROUP BY (rgroups->>axis_y, rgroups->>axis_x)`` over assignment ⋈
activity_value, ``argmin(scalar)`` per cell. Argmin is correct because the FE
gates heatmap coloring/curve-expand to dose-response potency channels, where the
scalar is a concentration (lower = more potent = the right cell representative).
Each axis is capped to the top-K substituents by member count; ``y_total`` /
``x_total`` / ``truncated`` let the UI label "top K of N" honestly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from returns.result import Failure, Result, Success

from cellar.application.sar_analysis.repositories import (
    RGroupDecompositionRunRepository,
    SarActivityProjectionRepository,
)
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError

HEATMAP_AXIS_TOP_K = 30


@dataclass(frozen=True)
class HeatmapCell:
    y: str
    x: str
    count: int
    best_scalar: float
    best_molecule_id: UUID
    best_molecule_label: str
    best_snapshot: dict[str, Any]


@dataclass(frozen=True)
class HeatmapResult:
    x_values: list[str]
    y_values: list[str]
    cells: list[HeatmapCell]
    y_total: int
    x_total: int
    truncated: bool


class ActivityHeatmapReader(Protocol):
    async def fetch_heatmap(
        self,
        run_id: UUID,
        *,
        workspace_id: UUID,
        projection_id: UUID,
        axis_y: str,
        axis_x: str,
        top_k: int = HEATMAP_AXIS_TOP_K,
    ) -> HeatmapResult: ...


@dataclass(frozen=True)
class FetchActivityHeatmapInput:
    run_id: UUID
    projection_id: UUID
    workspace_id: UUID
    axis_y: str
    axis_x: str


class FetchActivityHeatmap:
    def __init__(
        self,
        *,
        run_repository: RGroupDecompositionRunRepository,
        projection_repository: SarActivityProjectionRepository,
        reader: ActivityHeatmapReader,
        uow: UnitOfWork,
    ) -> None:
        self._runs = run_repository
        self._projections = projection_repository
        self._reader = reader
        self._uow = uow

    async def execute(
        self, payload: FetchActivityHeatmapInput
    ) -> Result[HeatmapResult, DomainError]:
        async with self._uow:
            run = await self._runs.find_by_id(payload.run_id, workspace_id=payload.workspace_id)
            if run is None:
                return Failure(NotFoundError("RGroupDecompositionRun", str(payload.run_id)))
            projection = await self._projections.find_by_id(
                payload.projection_id, workspace_id=payload.workspace_id
            )
            if projection is None:
                return Failure(
                    NotFoundError("SarActivityProjection", str(payload.projection_id))
                )
            result = await self._reader.fetch_heatmap(
                payload.run_id,
                workspace_id=payload.workspace_id,
                projection_id=payload.projection_id,
                axis_y=payload.axis_y,
                axis_x=payload.axis_x,
            )
        return Success(result)
```

- [ ] **Step 2: Write the failing integration test**

Create `tests/integration/persistence/sar_analysis/test_activity_heatmap_reader.py`:

```python
"""Integration tests for SQLAlchemyActivityHeatmapReader (argmin + top-K cap)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from cellar.domain.sar_analysis.activity_projection_types import ActivityScalar
from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRun
from cellar.domain.sar_analysis.rgroup_types import RGroupAssignment
from cellar.domain.sar_analysis.sar_activity_projection import SarActivityProjection
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.activity_heatmap_reader import (
    SQLAlchemyActivityHeatmapReader,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.rgroup_decomposition_run_repository import (  # noqa: E501
    SQLAlchemyRGroupDecompositionRunRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_repository import (  # noqa: E501
    SQLAlchemySarActivityProjectionRepository,
)

_NOW = datetime(2026, 6, 15, tzinfo=UTC)


async def _seed_org(uow, ws):
    org_id = uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
            "VALUES (:id, :ws, :n, 'internal', true, 1)"
        ),
        {"id": org_id, "ws": ws, "n": f"org-{org_id.hex[:6]}"},
    )
    return org_id


async def _seed_molecule(uow, ws, org, *, reg):
    mol_id = uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO molecules (id, workspace_id, registration_number, name, molecule_type, "
            "smiles, version, originating_org_id) "
            "VALUES (:id, :ws, :r, :r, 'small_molecule', 'Fc1ccccc1', 1, :org)"
        ),
        {"id": mol_id, "ws": ws, "r": reg, "org": org},
    )
    return mol_id


async def _ready_run(uow, ws):
    run = (
        RGroupDecompositionRun.create(
            workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
            core_smiles="c1ccccc1", core_hash="ch", now=_NOW,
        )
        .mark_running(_NOW)
        .mark_ready(rgroup_labels=["R1", "R2"], matched_count=0, unmatched_count=0, total_count=0, now=_NOW)
    )
    await SQLAlchemyRGroupDecompositionRunRepository(uow).save(run)
    return run


async def _ready_projection(uow, ws):
    proj = (
        SarActivityProjection.create(
            workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
            channel_hash="ch", channel_spec={"column": "drc:x"}, now=_NOW,
        )
        .mark_running(_NOW)
        .mark_ready(value_count=0, now=_NOW)
    )
    await SQLAlchemySarActivityProjectionRepository(uow).save(proj)
    return proj


@pytest.mark.asyncio
async def test_heatmap_argmin_per_cell(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _ready_run(uow, ws)
        proj = await _ready_projection(uow, ws)
        run_repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        proj_repo = SQLAlchemySarActivityProjectionRepository(uow)
        # Two molecules in the SAME cell (R1=F, R2=Cl): potent (0.1) and weak (5.0).
        potent = await _seed_molecule(uow, ws, org, reg="CV-POTENT")
        weak = await _seed_molecule(uow, ws, org, reg="CV-WEAK")
        # One molecule in a different cell (R1=Br, R2=Cl).
        other = await _seed_molecule(uow, ws, org, reg="CV-OTHER")
        await run_repo.write_assignments(run.id, [
            RGroupAssignment(molecule_id=potent, rgroups={"R1": "F", "R2": "Cl"}),
            RGroupAssignment(molecule_id=weak, rgroups={"R1": "F", "R2": "Cl"}),
            RGroupAssignment(molecule_id=other, rgroups={"R1": "Br", "R2": "Cl"}),
        ])
        await proj_repo.write_values(proj.id, [
            ActivityScalar(molecule_id=potent, scalar=0.1, unit="uM", qualifier=None,
                           source="dose_response", snapshot={"value": 0.1}),
            ActivityScalar(molecule_id=weak, scalar=5.0, unit="uM", qualifier=None,
                           source="dose_response", snapshot={"value": 5.0}),
            ActivityScalar(molecule_id=other, scalar=2.0, unit="uM", qualifier=None,
                           source="dose_response", snapshot={"value": 2.0}),
        ])
        await uow.commit()

    async with uow:
        reader = SQLAlchemyActivityHeatmapReader(uow)
        res = await reader.fetch_heatmap(
            run.id, workspace_id=ws, projection_id=proj.id, axis_y="R1", axis_x="R2"
        )

    cells = {(c.y, c.x): c for c in res.cells}
    assert ("F", "Cl") in cells and ("Br", "Cl") in cells
    fcl = cells[("F", "Cl")]
    assert fcl.count == 2
    assert fcl.best_scalar == pytest.approx(0.1)  # argmin = the potent one
    assert fcl.best_molecule_id == potent
    assert fcl.best_molecule_label == "CV-POTENT"
    assert fcl.best_snapshot == {"value": 0.1}
    assert res.truncated is False
    assert res.y_total == 2 and res.x_total == 1


@pytest.mark.asyncio
async def test_heatmap_caps_axis_to_top_k_by_member_count(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _ready_run(uow, ws)
        proj = await _ready_projection(uow, ws)
        run_repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        proj_repo = SQLAlchemySarActivityProjectionRepository(uow)
        assignments, values = [], []
        # 4 distinct R1 groups, all with R2=Cl. Group "A" has 3 members; others 1 each.
        plan = [("A", 3), ("B", 1), ("C", 1), ("D", 1)]
        for r1, n in plan:
            for _ in range(n):
                mid = await _seed_molecule(uow, ws, org, reg=f"CV-{r1}-{uuid.uuid4().hex[:4]}")
                assignments.append(RGroupAssignment(molecule_id=mid, rgroups={"R1": r1, "R2": "Cl"}))
                values.append(ActivityScalar(molecule_id=mid, scalar=1.0, unit="uM",
                                             qualifier=None, source="dose_response", snapshot={}))
        await run_repo.write_assignments(run.id, assignments)
        await proj_repo.write_values(proj.id, values)
        await uow.commit()

    async with uow:
        reader = SQLAlchemyActivityHeatmapReader(uow)
        res = await reader.fetch_heatmap(
            run.id, workspace_id=ws, projection_id=proj.id, axis_y="R1", axis_x="R2", top_k=2
        )

    # top_k=2 keeps the two most-populated R1 groups; "A" (3 members) must survive.
    kept = {c.y for c in res.cells}
    assert "A" in kept
    assert len(kept) == 2
    assert res.y_total == 4  # honest total
    assert res.truncated is True


@pytest.mark.asyncio
async def test_heatmap_excludes_molecules_missing_an_axis(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _ready_run(uow, ws)
        proj = await _ready_projection(uow, ws)
        run_repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        proj_repo = SQLAlchemySarActivityProjectionRepository(uow)
        full = await _seed_molecule(uow, ws, org, reg="CV-FULL")
        partial = await _seed_molecule(uow, ws, org, reg="CV-PARTIAL")
        await run_repo.write_assignments(run.id, [
            RGroupAssignment(molecule_id=full, rgroups={"R1": "F", "R2": "Cl"}),
            RGroupAssignment(molecule_id=partial, rgroups={"R1": "F"}),  # no R2
        ])
        await proj_repo.write_values(proj.id, [
            ActivityScalar(molecule_id=full, scalar=0.1, unit="uM", qualifier=None, source="dose_response", snapshot={}),
            ActivityScalar(molecule_id=partial, scalar=0.2, unit="uM", qualifier=None, source="dose_response", snapshot={}),
        ])
        await uow.commit()

    async with uow:
        reader = SQLAlchemyActivityHeatmapReader(uow)
        res = await reader.fetch_heatmap(run.id, workspace_id=ws, projection_id=proj.id, axis_y="R1", axis_x="R2")

    assert len(res.cells) == 1  # partial (no R2) is not placeable in a 2D cell
    assert res.cells[0].count == 1
```

- [ ] **Step 3: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/integration/persistence/sar_analysis/test_activity_heatmap_reader.py -v`
Expected: FAIL — `ModuleNotFoundError: ...activity_heatmap_reader`.

- [ ] **Step 4: Implement the SQL reader**

Create `src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/activity_heatmap_reader.py`:

```python
"""SQLAlchemy read-model for the activity heatmap.

GROUP BY (rgroups->>axis_y, rgroups->>axis_x) over assignment ⋈ activity_value ⋈
molecules, argmin(scalar) per cell. ``argmin`` is the *lower-is-better* cell
representative — correct because the FE only colors/expands dose-response potency
channels (concentrations, where lower = more potent). Each axis is capped to the
top-K substituents by member count; totals are reported separately so the UI can
label "top K of N" honestly. Molecules missing either axis substituent are not
placeable in a 2D cell and are excluded.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import distinct, func, select

from cellar.application.sar_analysis.activity_heatmap import (
    HEATMAP_AXIS_TOP_K,
    HeatmapCell,
    HeatmapResult,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.rgroup_decomposition_models import (
    RGroupAssignmentModel,
    RGroupDecompositionRunModel,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_models import (  # noqa: E501
    SarActivityValueModel,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyActivityHeatmapReader:
    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def fetch_heatmap(
        self,
        run_id: UUID,
        *,
        workspace_id: UUID,
        projection_id: UUID,
        axis_y: str,
        axis_x: str,
        top_k: int = HEATMAP_AXIS_TOP_K,
    ) -> HeatmapResult:
        session = self._uow.session
        y_expr = RGroupAssignmentModel.rgroups[axis_y].as_string()
        x_expr = RGroupAssignmentModel.rgroups[axis_x].as_string()
        label_expr = func.coalesce(MoleculeModel.registration_number, MoleculeModel.name)

        base = (
            select(
                RGroupAssignmentModel.molecule_id.label("molecule_id"),
                y_expr.label("y"),
                x_expr.label("x"),
                SarActivityValueModel.scalar.label("scalar"),
                label_expr.label("label"),
                SarActivityValueModel.snapshot.label("snapshot"),
            )
            .join(
                RGroupDecompositionRunModel,
                RGroupDecompositionRunModel.id == RGroupAssignmentModel.run_id,
            )
            .join(
                SarActivityValueModel,
                (SarActivityValueModel.projection_id == projection_id)
                & (SarActivityValueModel.molecule_id == RGroupAssignmentModel.molecule_id),
            )
            .join(MoleculeModel, MoleculeModel.id == RGroupAssignmentModel.molecule_id)
            .where(
                RGroupAssignmentModel.run_id == run_id,
                RGroupDecompositionRunModel.workspace_id == workspace_id,
                MoleculeModel.workspace_id == workspace_id,
                MoleculeModel.merged_into_id.is_(None),
                y_expr.isnot(None),
                x_expr.isnot(None),
            )
            .cte("base")
        )

        # Honest totals (distinct substituents per axis, before the cap).
        totals = (
            await session.execute(
                select(func.count(distinct(base.c.y)), func.count(distinct(base.c.x)))
            )
        ).one()
        y_total, x_total = int(totals[0]), int(totals[1])

        # Top-K substituents per axis by member count.
        y_top = (
            select(base.c.y)
            .group_by(base.c.y)
            .order_by(func.count().desc(), base.c.y)
            .limit(top_k)
        )
        x_top = (
            select(base.c.x)
            .group_by(base.c.x)
            .order_by(func.count().desc(), base.c.x)
            .limit(top_k)
        )
        capped = (
            select(
                base.c.molecule_id,
                base.c.y,
                base.c.x,
                base.c.scalar,
                base.c.label,
                base.c.snapshot,
            )
            .where(base.c.y.in_(y_top), base.c.x.in_(x_top))
            .cte("capped")
        )

        rn = func.row_number().over(
            partition_by=[capped.c.y, capped.c.x],
            order_by=[capped.c.scalar.asc(), capped.c.molecule_id],
        ).label("rn")
        cell_count = func.count().over(partition_by=[capped.c.y, capped.c.x]).label("cell_count")
        ranked = select(
            capped.c.molecule_id,
            capped.c.y,
            capped.c.x,
            capped.c.scalar,
            capped.c.label,
            capped.c.snapshot,
            rn,
            cell_count,
        ).cte("ranked")

        rows = (
            await session.execute(
                select(
                    ranked.c.y,
                    ranked.c.x,
                    ranked.c.cell_count,
                    ranked.c.scalar,
                    ranked.c.molecule_id,
                    ranked.c.label,
                    ranked.c.snapshot,
                ).where(ranked.c.rn == 1)
            )
        ).all()

        cells = [
            HeatmapCell(
                y=r.y,
                x=r.x,
                count=int(r.cell_count),
                best_scalar=float(r.scalar),
                best_molecule_id=r.molecule_id,
                best_molecule_label=r.label or "",
                best_snapshot=dict(r.snapshot or {}),
            )
            for r in rows
        ]
        y_values = sorted({c.y for c in cells})
        x_values = sorted({c.x for c in cells})
        return HeatmapResult(
            x_values=x_values,
            y_values=y_values,
            cells=cells,
            y_total=y_total,
            x_total=x_total,
            truncated=(y_total > top_k or x_total > top_k),
        )
```

- [ ] **Step 5: Run the test to confirm it passes**

Run: `cd backend && uv run pytest tests/integration/persistence/sar_analysis/test_activity_heatmap_reader.py -v && uv run lint-imports`
Expected: all PASS; import-linter clean. (If SQLAlchemy raises on `base.c.y.in_(y_top)` with a CTE-derived subquery, wrap each in `.scalar_subquery()` is **not** what you want for `IN` — instead materialize `y_top`/`x_top` as `.subquery()` and reference `select(sub.c.y)`. The `.in_(select(...))` form shown is the standard `IN (subquery)` and should render directly.)

- [ ] **Step 6: Register `FetchActivityHeatmap` in DI (now that its module exists)**

In `src/cellar/infrastructure/di/_sar_analysis.py`, add the imports (with the other sar imports):

```python
from cellar.application.sar_analysis.activity_heatmap import FetchActivityHeatmap
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.activity_heatmap_reader import (
    SQLAlchemyActivityHeatmapReader,
)
```

Replace the placeholder comment `# NOTE: FetchActivityHeatmap is registered in Task 14...` (added in Task 13) with the factory + define:

```python
    def _fetch_activity_heatmap(c: Container) -> FetchActivityHeatmap:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return FetchActivityHeatmap(
            run_repository=SQLAlchemyRGroupDecompositionRunRepository(uow),
            projection_repository=SQLAlchemySarActivityProjectionRepository(uow),
            reader=SQLAlchemyActivityHeatmapReader(uow),
            uow=uow,
        )

    container.define(FetchActivityHeatmap, _fetch_activity_heatmap)
```

Add the heatmap assertion to `test_activity_projection_use_cases_resolve_with_temporal_disabled` in `tests/unit/infrastructure/di/test_sar_analysis_wiring.py` (import + assert):

```python
        from cellar.application.sar_analysis.activity_heatmap import FetchActivityHeatmap
        # ... after the existing asserts:
        assert isinstance(container[FetchActivityHeatmap], FetchActivityHeatmap)
```

Run: `cd backend && TEMPORAL_DISABLED=1 uv run pytest tests/unit/infrastructure/di/test_sar_analysis_wiring.py -v && uv run python -c "import cellar.interface.app; print('app imports ok')"`
Expected: all PASS (including the `FetchActivityHeatmap` resolution); app imports cleanly.

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(sar): activity heatmap — argmin aggregation + top-K axis cap" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/application/sar_analysis/activity_heatmap.py src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/activity_heatmap_reader.py tests/integration/persistence/sar_analysis/test_activity_heatmap_reader.py src/cellar/infrastructure/di/_sar_analysis.py tests/unit/infrastructure/di/test_sar_analysis_wiring.py
```

---

## Task 15: `/rows` activity extension (optional `projection_id` → LEFT JOIN)

Extend the existing `/rows` read-model: when a `projection_id` is given, LEFT JOIN `sar_activity_values` and surface `activity` per row + enable sort-by-activity. Additive and backward-compatible (existing callers pass no `projection_id` → `activity` is null).

**Files:**
- Modify: `src/cellar/application/sar_analysis/decomposition_rows.py`
- Modify: `src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/decomposition_row_reader.py`
- Test: `tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py` (add cases)

- [ ] **Step 1: Write the failing reader test cases** — append to `test_decomposition_row_reader.py`:

```python
async def _seed_ready_projection(uow, ws):
    from cellar.domain.sar_analysis.sar_activity_projection import SarActivityProjection
    from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_repository import (  # noqa: E501
        SQLAlchemySarActivityProjectionRepository,
    )

    proj = (
        SarActivityProjection.create(
            workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
            channel_hash="ch", channel_spec={"column": "drc:x"}, now=_NOW,
        )
        .mark_running(_NOW)
        .mark_ready(value_count=0, now=_NOW)
    )
    await SQLAlchemySarActivityProjectionRepository(uow).save(proj)
    return proj


@pytest.mark.asyncio
async def test_fetch_rows_joins_activity_when_projection_given(uow):
    from cellar.domain.sar_analysis.activity_projection_types import ActivityScalar
    from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_repository import (  # noqa: E501
        SQLAlchemySarActivityProjectionRepository,
    )

    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        proj = await _seed_ready_projection(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        with_act = await _seed_molecule(uow, ws, org, reg="CV-ACT", smiles="Fc1ccccc1")
        no_act = await _seed_molecule(uow, ws, org, reg="CV-NONE", smiles="Clc1ccccc1")
        await repo.write_assignments(run.id, [
            RGroupAssignment(molecule_id=with_act, rgroups={"R1": "F"}),
            RGroupAssignment(molecule_id=no_act, rgroups={"R1": "Cl"}),
        ])
        await SQLAlchemySarActivityProjectionRepository(uow).write_values(proj.id, [
            ActivityScalar(molecule_id=with_act, scalar=0.7, unit="uM", qualifier=None,
                           source="dose_response", snapshot={}),
        ])
        await uow.commit()

    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        rows = await reader.fetch_rows(
            run.id, workspace_id=ws, offset=0, limit=50, sort=[], projection_id=proj.id
        )
    by_reg = {r.registration_number: r for r in rows}
    assert by_reg["CV-ACT"].activity == pytest.approx(0.7)
    assert by_reg["CV-NONE"].activity is None  # sparse LEFT JOIN null


@pytest.mark.asyncio
async def test_fetch_rows_sorts_by_activity(uow):
    from cellar.domain.sar_analysis.activity_projection_types import ActivityScalar
    from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_repository import (  # noqa: E501
        SQLAlchemySarActivityProjectionRepository,
    )

    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        proj = await _seed_ready_projection(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        values = []
        for reg, scalar in (("CV-HI", 9.0), ("CV-LO", 0.2), ("CV-MID", 1.5)):
            m = await _seed_molecule(uow, ws, org, reg=reg, smiles="Fc1ccccc1")
            await repo.write_assignments(run.id, [RGroupAssignment(molecule_id=m, rgroups={"R1": "F"})])
            values.append(ActivityScalar(molecule_id=m, scalar=scalar, unit="uM", qualifier=None,
                                         source="dose_response", snapshot={}))
        await SQLAlchemySarActivityProjectionRepository(uow).write_values(proj.id, values)
        await uow.commit()

    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        rows = await reader.fetch_rows(
            run.id, workspace_id=ws, offset=0, limit=50,
            sort=[DecompositionRowSort(col="activity", direction="asc")], projection_id=proj.id,
        )
    assert [r.registration_number for r in rows] == ["CV-LO", "CV-MID", "CV-HI"]


@pytest.mark.asyncio
async def test_fetch_rows_activity_is_none_without_projection(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        m = await _seed_molecule(uow, ws, org, reg="CV-1", smiles="Fc1ccccc1")
        await repo.write_assignments(run.id, [RGroupAssignment(molecule_id=m, rgroups={"R1": "F"})])
        await uow.commit()

    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        rows = await reader.fetch_rows(run.id, workspace_id=ws, offset=0, limit=50, sort=[])
    assert rows[0].activity is None  # no projection -> activity absent
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py -k "activity" -v`
Expected: FAIL — `TypeError: fetch_rows() got an unexpected keyword argument 'projection_id'` (and `AttributeError: ...activity`).

- [ ] **Step 3: Extend `decomposition_rows.py`**

In `DecompositionRow`, add a trailing field:

```python
@dataclass(frozen=True)
class DecompositionRow:
    molecule_id: UUID
    smiles: str | None
    registration_number: str
    name: str
    rgroups: dict[str, str]
    molecular_weight: float | None
    logp: float | None
    tpsa: float | None
    activity: float | None = None
```

In the `DecompositionRowReader` Protocol, add `projection_id` to `fetch_rows`:

```python
    async def fetch_rows(
        self,
        run_id: UUID,
        *,
        workspace_id: UUID,
        offset: int,
        limit: int,
        sort: list[DecompositionRowSort],
        projection_id: UUID | None = None,
    ) -> list[DecompositionRow]: ...
```

In `FetchDecompositionRowsInput`, add a trailing field:

```python
@dataclass(frozen=True)
class FetchDecompositionRowsInput:
    run_id: UUID
    workspace_id: UUID
    offset: int
    limit: int
    sort: list[DecompositionRowSort]
    projection_id: UUID | None = None
```

In `FetchDecompositionRows.execute`, pass `projection_id` through to `fetch_rows`:

```python
            rows = await self._reader.fetch_rows(
                payload.run_id,
                workspace_id=payload.workspace_id,
                offset=payload.offset,
                limit=payload.limit,
                sort=payload.sort,
                projection_id=payload.projection_id,
            )
```

- [ ] **Step 4: Extend `decomposition_row_reader.py`**

Add the import (next to the rgroup models import):

```python
from sqlalchemy import func, null, select  # add ``null`` to the existing import

from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_models import (  # noqa: E501
    SarActivityValueModel,
)
```

Replace the whole `fetch_rows` method with the activity-aware version (the `_scoped_join` and `count_rows` are unchanged):

```python
    async def fetch_rows(
        self,
        run_id: UUID,
        *,
        workspace_id: UUID,
        offset: int,
        limit: int,
        sort: list[DecompositionRowSort],
        projection_id: UUID | None = None,
    ) -> list[DecompositionRow]:
        # Activity is a LEFT JOIN to the projection's sparse values; absent ⇒
        # null (uncolored / unsortable for that row), exactly like the client did.
        activity_col = SarActivityValueModel.scalar if projection_id is not None else null()

        stmt = self._scoped_join(
            select(
                RGroupAssignmentModel.molecule_id,
                MoleculeModel.smiles,
                MoleculeModel.registration_number,
                MoleculeModel.name,
                RGroupAssignmentModel.rgroups,
                MoleculeModel.molecular_weight,
                MoleculeModel.logp,
                MoleculeModel.tpsa,
                activity_col.label("activity"),
            ),
            run_id,
            workspace_id,
        )
        if projection_id is not None:
            stmt = stmt.outerjoin(
                SarActivityValueModel,
                (SarActivityValueModel.projection_id == projection_id)
                & (SarActivityValueModel.molecule_id == RGroupAssignmentModel.molecule_id),
            )

        order_by = []
        for spec in sort:
            if spec.col == "activity":
                col = SarActivityValueModel.scalar if projection_id is not None else None
            else:
                col = _sort_column(spec.col)
            if col is None:
                continue  # unknown / inapplicable sort key — ignored (lenient)
            ordered = col.desc() if spec.direction == "desc" else col.asc()
            order_by.append(ordered.nulls_last())
        order_by.append(RGroupAssignmentModel.molecule_id)  # stable tiebreaker

        stmt = stmt.order_by(*order_by).offset(offset).limit(limit)
        result = await self._uow.session.execute(stmt)
        return [
            DecompositionRow(
                molecule_id=row[0],
                smiles=row[1],
                registration_number=row[2],
                name=row[3],
                rgroups=dict(row[4]),
                molecular_weight=row[5],
                logp=row[6],
                tpsa=row[7],
                activity=row[8],
            )
            for row in result.all()
        ]
```

- [ ] **Step 5: Run the reader tests to confirm they pass**

Run: `cd backend && uv run pytest tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py -v && uv run lint-imports`
Expected: all PASS (old + new cases); import-linter clean.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(sar): /rows activity extension (optional projection_id LEFT JOIN + sort)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/application/sar_analysis/decomposition_rows.py src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/decomposition_row_reader.py tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py
```

---

## Task 16: Interface — routes + deps (activity-projection · heatmap · rows projection_id)

**Files:**
- Modify: `src/cellar/interface/dependencies/_sar_analysis.py`
- Modify: `src/cellar/interface/routes/sar_analysis.py`
- Test: `tests/api/test_sar_activity_projection_routes.py` (new)

- [ ] **Step 1: Add the Deps** — in `_sar_analysis.py`, add imports + Deps (mirror the decomposition Deps):

```python
from cellar.application.sar_analysis.activity_heatmap import FetchActivityHeatmap
from cellar.application.sar_analysis.cancel_activity_projection import CancelActivityProjection
from cellar.application.sar_analysis.get_activity_projection import GetActivityProjection
from cellar.application.sar_analysis.start_activity_projection import StartActivityProjection
```

Add to `__all__`: `"StartActivityProjectionDep"`, `"GetActivityProjectionDep"`, `"CancelActivityProjectionDep"`, `"FetchActivityHeatmapDep"`. Then:

```python
StartActivityProjectionDep = Annotated[
    StartActivityProjection, Depends(_get_use_case(StartActivityProjection))
]
GetActivityProjectionDep = Annotated[
    GetActivityProjection, Depends(_get_use_case(GetActivityProjection))
]
CancelActivityProjectionDep = Annotated[
    CancelActivityProjection, Depends(_get_use_case(CancelActivityProjection))
]
FetchActivityHeatmapDep = Annotated[
    FetchActivityHeatmap, Depends(_get_use_case(FetchActivityHeatmap))
]
```

- [ ] **Step 2: Extend `routes/sar_analysis.py`** — add imports (top):

```python
from cellar.application.sar_analysis.activity_channel import ActivityChannelSpec
from cellar.application.sar_analysis.activity_heatmap import FetchActivityHeatmapInput
from cellar.application.sar_analysis.cancel_activity_projection import (
    CancelActivityProjectionInput,
)
from cellar.application.sar_analysis.get_activity_projection import GetActivityProjectionInput
from cellar.application.sar_analysis.start_activity_projection import (
    StartActivityProjectionInput,
)
from cellar.domain.sar_analysis.sar_activity_projection import (
    SarActivityProjection,
    SarActivityProjectionStatus,
)
from cellar.domain.screening_assay.run_scope import RunScope  # noqa: F401  (documents run_scopes wire)
from cellar.domain.shared.aggregation_types import QualifierHandling, SelectionRule
from cellar.domain.shared.hit_criterion import InterceptKey
from cellar.interface.dependencies._sar_analysis import (
    CancelActivityProjectionDep,
    FetchActivityHeatmapDep,
    GetActivityProjectionDep,
    StartActivityProjectionDep,
)
```

Add models + view helpers (after the decomposition models):

```python
class InterceptKeyModel(BaseModel):
    kind: Literal["ec", "ic"]
    level: float


class ActivityChannelRequest(BaseModel):
    column: str
    source: Literal["dr_curve", "readout_data"]
    selection_rule: SelectionRule = SelectionRule.LATEST_APPROVED_RUN
    qualifier_handling: QualifierHandling = QualifierHandling.EXCLUDE_QUALIFIED
    intercept_key: InterceptKeyModel | None = None
    run_scopes: dict[str, Any] | None = None
    protocol_id: UUID | None = None
    label: str = ""


class StartActivityProjectionRequest(BaseModel):
    molecule_ids: list[UUID] | None = None
    collection_id: UUID | None = None
    channel: ActivityChannelRequest


class ActivityProjectionResponse(BaseModel):
    projection_id: UUID
    status: str
    value_count: int
    error_message: str | None = None


class HeatmapRequest(BaseModel):
    axis_y: str
    axis_x: str
    projection_id: UUID


class HeatmapCellView(BaseModel):
    y: str
    x: str
    count: int
    best_scalar: float
    best_molecule_id: UUID
    best_molecule_label: str
    best_snapshot: dict[str, Any]


class HeatmapResponse(BaseModel):
    x_values: list[str]
    y_values: list[str]
    cells: list[HeatmapCellView]
    y_total: int
    x_total: int
    truncated: bool


def _projection_view(p: SarActivityProjection) -> ActivityProjectionResponse:
    return ActivityProjectionResponse(
        projection_id=p.id,
        status=p.status.value,
        value_count=p.value_count,
        error_message=p.error_message,
    )


def _to_channel(req: ActivityChannelRequest) -> ActivityChannelSpec:
    return ActivityChannelSpec(
        column=req.column,
        source=req.source,
        selection_rule=req.selection_rule,
        qualifier_handling=req.qualifier_handling,
        intercept_key=(
            InterceptKey(kind=req.intercept_key.kind, level=req.intercept_key.level)
            if req.intercept_key is not None
            else None
        ),
        run_scopes=req.run_scopes,
        protocol_id=req.protocol_id,
        label=req.label,
    )
```

Extend `DecompositionRowsRequest` with `projection_id` and `DecompositionRowView` with `activity` (both additive, defaulted):

```python
# in DecompositionRowsRequest, add:
    projection_id: UUID | None = None

# in DecompositionRowView, add a trailing field:
    activity: float | None = None
```

Update `_row_view` to carry activity:

```python
def _row_view(row: DecompositionRow) -> DecompositionRowView:
    return DecompositionRowView(
        molecule_id=row.molecule_id,
        smiles=row.smiles,
        registration_number=row.registration_number,
        name=row.name,
        rgroups=row.rgroups,
        mw=row.molecular_weight,
        clogp=row.logp,
        tpsa=row.tpsa,
        activity=row.activity,
    )
```

Update the `decomposition_rows` route to thread `projection_id`:

```python
    out = result_to_response(
        await uc.execute(
            FetchDecompositionRowsInput(
                run_id=run_id,
                workspace_id=auth.workspace_id,
                offset=payload.offset,
                limit=payload.limit,
                sort=sort,
                projection_id=payload.projection_id,
            )
        )
    )
```

Add the four new routes (after the decomposition routes):

```python
@router.post("/activity-projection", status_code=status.HTTP_200_OK)
async def start_activity_projection(
    payload: StartActivityProjectionRequest,
    response: Response,
    auth: AuthDep,
    uc: StartActivityProjectionDep,
) -> ActivityProjectionResponse:
    if (payload.molecule_ids is None) == (payload.collection_id is None):
        raise HTTPException(
            status_code=400,
            detail="exactly one of molecule_ids or collection_id must be set",
        )
    if not payload.channel.column.strip():
        raise HTTPException(status_code=400, detail="channel.column must not be empty")

    proj = await uc.execute(
        StartActivityProjectionInput(
            workspace_id=auth.workspace_id,
            requested_by=auth.user_id,
            collection_id=payload.collection_id,
            molecule_ids=payload.molecule_ids,
            channel=_to_channel(payload.channel),
            now=datetime.now(UTC),
        )
    )
    if proj.status != SarActivityProjectionStatus.READY:
        response.status_code = status.HTTP_202_ACCEPTED
    return _projection_view(proj)


@router.get("/activity-projection/jobs/{projection_id}")
async def get_activity_projection(
    projection_id: UUID,
    auth: AuthDep,
    uc: GetActivityProjectionDep,
) -> ActivityProjectionResponse:
    proj = result_to_response(
        await uc.execute(
            GetActivityProjectionInput(projection_id=projection_id, workspace_id=auth.workspace_id)
        )
    )
    return _projection_view(proj)


@router.post("/activity-projection/jobs/{projection_id}/cancel")
async def cancel_activity_projection(
    projection_id: UUID,
    auth: AuthDep,
    uc: CancelActivityProjectionDep,
) -> ActivityProjectionResponse:
    proj = result_to_response(
        await uc.execute(
            CancelActivityProjectionInput(
                projection_id=projection_id, workspace_id=auth.workspace_id, now=datetime.now(UTC)
            )
        )
    )
    return _projection_view(proj)


@router.post("/decomposition/{run_id}/heatmap")
async def decomposition_heatmap(
    run_id: UUID,
    payload: HeatmapRequest,
    auth: AuthDep,
    uc: FetchActivityHeatmapDep,
) -> HeatmapResponse:
    out = result_to_response(
        await uc.execute(
            FetchActivityHeatmapInput(
                run_id=run_id,
                projection_id=payload.projection_id,
                workspace_id=auth.workspace_id,
                axis_y=payload.axis_y,
                axis_x=payload.axis_x,
            )
        )
    )
    return HeatmapResponse(
        x_values=out.x_values,
        y_values=out.y_values,
        cells=[
            HeatmapCellView(
                y=c.y,
                x=c.x,
                count=c.count,
                best_scalar=c.best_scalar,
                best_molecule_id=c.best_molecule_id,
                best_molecule_label=c.best_molecule_label,
                best_snapshot=c.best_snapshot,
            )
            for c in out.cells
        ],
        y_total=out.y_total,
        x_total=out.x_total,
        truncated=out.truncated,
    )
```

- [ ] **Step 3: Write the API tests** (test the wiring; SQL internals are covered by the reader integration tests)

Create `tests/api/test_sar_activity_projection_routes.py`:

```python
"""API tests for the activity-projection endpoints + heatmap + rows activity.

Wiring-level: route validation, DI, an inline happy path through HTTP, 404s, and
a seeded heatmap/rows-activity happy path. The argmin/cap/join internals are
covered by the reader integration tests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.domain.sar_analysis.activity_projection_types import ActivityScalar
from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRun
from cellar.domain.sar_analysis.rgroup_types import RGroupAssignment
from cellar.domain.sar_analysis.sar_activity_projection import SarActivityProjection
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.rgroup_decomposition_run_repository import (  # noqa: E501
    SQLAlchemyRGroupDecompositionRunRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_repository import (  # noqa: E501
    SQLAlchemySarActivityProjectionRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

_NOW = datetime(2026, 6, 15, tzinfo=UTC)


def _channel(column="drc:" + str(uuid.uuid4())):
    return {"column": column, "source": "dr_curve"}


async def _seed_molecule(session, ws, org, reg):
    mid = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO molecules (id, workspace_id, registration_number, name, molecule_type, "
            "smiles, version, originating_org_id) "
            "VALUES (:id, :ws, :r, :r, 'small_molecule', 'Fc1ccccc1', 1, :org)"
        ),
        {"id": mid, "ws": ws, "r": reg, "org": org},
    )
    return mid


async def _seed_heatmap_fixture(api_app, ws):
    """run + 3 assignments (2 in one cell) + projection + 3 values. Returns (run_id, projection_id, potent_id)."""
    sf = api_app.state.container[async_sessionmaker]
    org = uuid.uuid4()
    async with sf() as session:
        await session.execute(
            text(
                "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
                "VALUES (:id, :ws, 'org-hm', 'internal', true, 1)"
            ),
            {"id": org, "ws": ws},
        )
        potent = await _seed_molecule(session, ws, org, "CV-POTENT")
        weak = await _seed_molecule(session, ws, org, "CV-WEAK")
        other = await _seed_molecule(session, ws, org, "CV-OTHER")
        await session.commit()

    uow = AsyncUnitOfWork(sf)
    async with uow:
        run = (
            RGroupDecompositionRun.create(
                workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
                core_smiles="c1ccccc1", core_hash="ch", now=_NOW,
            )
            .mark_running(_NOW)
            .mark_ready(rgroup_labels=["R1", "R2"], matched_count=3, unmatched_count=0, total_count=3, now=_NOW)
        )
        proj = (
            SarActivityProjection.create(
                workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
                channel_hash="ch", channel_spec={"column": "drc:x"}, now=_NOW,
            )
            .mark_running(_NOW)
            .mark_ready(value_count=3, now=_NOW)
        )
        await SQLAlchemyRGroupDecompositionRunRepository(uow).save(run)
        await SQLAlchemyRGroupDecompositionRunRepository(uow).write_assignments(run.id, [
            RGroupAssignment(molecule_id=potent, rgroups={"R1": "F", "R2": "Cl"}),
            RGroupAssignment(molecule_id=weak, rgroups={"R1": "F", "R2": "Cl"}),
            RGroupAssignment(molecule_id=other, rgroups={"R1": "Br", "R2": "Cl"}),
        ])
        pr = SQLAlchemySarActivityProjectionRepository(uow)
        await pr.save(proj)
        await pr.write_values(proj.id, [
            ActivityScalar(molecule_id=potent, scalar=0.1, unit="uM", qualifier=None, source="dose_response", snapshot={"value": 0.1}),
            ActivityScalar(molecule_id=weak, scalar=5.0, unit="uM", qualifier=None, source="dose_response", snapshot={"value": 5.0}),
            ActivityScalar(molecule_id=other, scalar=2.0, unit="uM", qualifier=None, source="dose_response", snapshot={"value": 2.0}),
        ])
        await uow.commit()
    return run.id, proj.id, potent


@pytest.mark.asyncio
async def test_projection_rejects_both_inputs(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/sar/activity-projection",
        json={"molecule_ids": [], "collection_id": str(uuid.uuid4()), "channel": _channel()},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_projection_rejects_empty_column(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/sar/activity-projection",
        json={"molecule_ids": [], "channel": {"column": "  ", "source": "dr_curve"}},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_projection_inline_empty_is_ready(client: AsyncClient) -> None:
    # No molecules -> ready with zero values (exercises HTTP -> DI -> enrich -> persist).
    res = await client.post(
        "/api/v1/sar/activity-projection",
        json={"molecule_ids": [], "channel": _channel()},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ready"
    assert body["value_count"] == 0
    assert uuid.UUID(body["projection_id"])
    # Poll returns ready.
    poll = await client.get(f"/api/v1/sar/activity-projection/jobs/{body['projection_id']}")
    assert poll.status_code == 200 and poll.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_projection_get_and_cancel_nonexistent_404(client: AsyncClient) -> None:
    assert (await client.get(f"/api/v1/sar/activity-projection/jobs/{uuid.uuid4()}")).status_code == 404
    assert (await client.post(f"/api/v1/sar/activity-projection/jobs/{uuid.uuid4()}/cancel")).status_code == 404


@pytest.mark.asyncio
async def test_heatmap_happy_path(client, api_app, workspace_id) -> None:
    run_id, projection_id, potent = await _seed_heatmap_fixture(api_app, workspace_id)
    res = await client.post(
        f"/api/v1/sar/decomposition/{run_id}/heatmap",
        json={"axis_y": "R1", "axis_x": "R2", "projection_id": str(projection_id)},
    )
    assert res.status_code == 200
    body = res.json()
    cells = {(c["y"], c["x"]): c for c in body["cells"]}
    assert cells[("F", "Cl")]["count"] == 2
    assert cells[("F", "Cl")]["best_scalar"] == pytest.approx(0.1)  # argmin
    assert cells[("F", "Cl")]["best_molecule_id"] == str(potent)
    assert body["truncated"] is False


@pytest.mark.asyncio
async def test_heatmap_nonexistent_run_404(client: AsyncClient) -> None:
    res = await client.post(
        f"/api/v1/sar/decomposition/{uuid.uuid4()}/heatmap",
        json={"axis_y": "R1", "axis_x": "R2", "projection_id": str(uuid.uuid4())},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_rows_carry_activity_when_projection_given(client, api_app, workspace_id) -> None:
    run_id, projection_id, potent = await _seed_heatmap_fixture(api_app, workspace_id)
    res = await client.post(
        f"/api/v1/sar/decomposition/{run_id}/rows",
        json={"offset": 0, "limit": 50, "projection_id": str(projection_id),
              "sort": [{"col": "activity", "dir": "asc"}]},
    )
    assert res.status_code == 200
    rows = res.json()["rows"]
    assert rows[0]["registration_number"] == "CV-POTENT"  # lowest activity first
    assert rows[0]["activity"] == pytest.approx(0.1)
```

- [ ] **Step 4: Run the API tests**

Run: `cd backend && uv run pytest tests/api/test_sar_activity_projection_routes.py -v && uv run lint-imports`
Expected: all PASS; import-linter clean.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(sar): activity-projection + heatmap routes + rows projection_id" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/interface/routes/sar_analysis.py src/cellar/interface/dependencies/_sar_analysis.py tests/api/test_sar_activity_projection_routes.py
```

---

## Task 17: End-to-end async path (Start → Null orch → Run → DB)

Wire the **real** Start, the real Null orchestrator, and the real RunActivityProjection (with a real `MoleculeActivityService`) together so a contract drift *between* two real components is caught. Mirrors `test_decomposition_async_e2e.py`. No screening data is seeded — the point is the async plumbing reaching READY, so `value_count == 0` is expected and correct.

**Files:**
- Test: `tests/integration/persistence/sar_analysis/test_activity_projection_async_e2e.py`

- [ ] **Step 1: Write the test**

Create `tests/integration/persistence/sar_analysis/test_activity_projection_async_e2e.py`:

```python
"""End-to-end async path against the real DB.

Start (> inline_threshold) -> real NullSarActivityProjectionOrchestrator -> real
RunActivityProjection (real MoleculeActivityService) -> Postgres -> projection
reaches READY. ``inline_threshold=1`` forces the async branch on a tiny set. No
screening data is seeded, so value_count is 0 — this test exercises the job
plumbing, not enrich correctness (that is unit-tested in test_activity_channel /
test_activity_enrichment).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from cellar.application.sar_analysis.activity_channel import ActivityChannelSpec
from cellar.application.sar_analysis.decomposition_members import DecompositionMemberStream
from cellar.application.sar_analysis.run_activity_projection import RunActivityProjection
from cellar.application.sar_analysis.start_activity_projection import (
    StartActivityProjection,
    StartActivityProjectionInput,
)
from cellar.application.screening.molecule_activity_service import MoleculeActivityService
from cellar.domain.sar_analysis.sar_activity_projection import SarActivityProjectionStatus
from cellar.domain.shared.aggregation_types import QualifierHandling, SelectionRule
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (  # noqa: E501
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.collection_repository import (  # noqa: E501
    SQLAlchemyCollectionRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_repository import (  # noqa: E501
    SQLAlchemySarActivityProjectionRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (  # noqa: E501
    SQLAlchemyDoseResponseCurveRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.readout_data_repository import (
    SQLAlchemyReadoutDataRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.run_repository import (
    SQLAlchemyRunRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from cellar.infrastructure.temporal.orchestrators.sar_activity_projection import (
    NullSarActivityProjectionOrchestrator,
)


async def _seed_molecules(session_factory, ws, n):
    org_id = uuid.uuid4()
    ids = [uuid.uuid4() for _ in range(n)]
    async with session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
                "VALUES (:id, :ws, 'org-e2e-ap', 'internal', true, 1)"
            ),
            {"id": org_id, "ws": ws},
        )
        for i, mid in enumerate(ids):
            await session.execute(
                text(
                    "INSERT INTO molecules (id, workspace_id, registration_number, name, "
                    "molecule_type, smiles, version, originating_org_id) VALUES "
                    "(:id, :ws, :r, :r, 'small_molecule', 'Fc1ccccc1', 1, :org)"
                ),
                {"id": mid, "ws": ws, "r": f"E2E-AP-{i}", "org": org_id},
            )
        await session.commit()
    return ids


def _members(uow):
    return DecompositionMemberStream(
        molecule_fetcher=SQLAlchemyMoleculeRepository(uow),
        collection_reader=SQLAlchemyCollectionRepository(uow),
    )


def _enricher(uow):
    return MoleculeActivityService(
        uow=uow,
        readout_repo=SQLAlchemyReadoutDataRepository(uow),
        curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
        protocol_repo=SQLAlchemyProtocolRepository(uow),
        run_repo=SQLAlchemyRunRepository(uow),
    )


def _channel():
    return ActivityChannelSpec(
        column="drc:" + str(uuid.uuid4()),
        source="dr_curve",
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.EXCLUDE_QUALIFIED,
    )


@pytest.mark.asyncio
async def test_async_projection_completes_via_null_orchestrator(session_factory):
    ws = uuid.uuid4()
    ids = await _seed_molecules(session_factory, ws, n=3)

    run_uow = AsyncUnitOfWork(session_factory)
    runner = RunActivityProjection(
        members=_members(run_uow),
        enricher=_enricher(run_uow),
        repository=SQLAlchemySarActivityProjectionRepository(run_uow),
        uow=run_uow,
    )
    orchestrator = NullSarActivityProjectionOrchestrator(runner)

    start_uow = AsyncUnitOfWork(session_factory)
    start = StartActivityProjection(
        members=_members(start_uow),
        enricher=_enricher(start_uow),
        repository=SQLAlchemySarActivityProjectionRepository(start_uow),
        orchestrator=orchestrator,
        uow=start_uow,
        inline_threshold=1,  # 3 members force the async (202) branch
    )

    proj = await start.execute(
        StartActivityProjectionInput(
            workspace_id=ws,
            requested_by=uuid.uuid4(),
            collection_id=None,
            molecule_ids=ids,
            channel=_channel(),
            now=datetime.now(UTC),
        )
    )
    assert proj.status == SarActivityProjectionStatus.PENDING  # scheduled, not inline

    assert orchestrator._tasks, "orchestrator should have scheduled a background run"
    await asyncio.gather(*list(orchestrator._tasks))

    verify_uow = AsyncUnitOfWork(session_factory)
    async with verify_uow:
        repo = SQLAlchemySarActivityProjectionRepository(verify_uow)
        final = await repo.find_by_id(proj.id, workspace_id=ws)
        n_values = await repo.count_values(proj.id, workspace_id=ws)

    assert final is not None
    assert final.status == SarActivityProjectionStatus.READY
    assert final.value_count == 0  # no screening data seeded -> sparse, empty
    assert n_values == 0
```

- [ ] **Step 2: Run it to confirm it passes**

Run: `cd backend && uv run pytest tests/integration/persistence/sar_analysis/test_activity_projection_async_e2e.py -v`
Expected: PASS (requires Docker). If it fails because the member stream + enricher cannot share the active session mid-stream, that is a real contract bug — fix `RunActivityProjection` (the stream must materialize each batch before `enrich_to_scalars` runs on the same session, which it does), not the test.

- [ ] **Step 3: Commit**

```bash
git commit -m "test(sar): end-to-end async activity-projection (Start->Null orch->Run->DB)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- tests/integration/persistence/sar_analysis/test_activity_projection_async_e2e.py
```

---

## Task 18: Full-suite verification + self-review

- [ ] **Step 1: Run the whole sar_analysis test surface**

Run:
```bash
cd backend && uv run pytest tests/unit/domain/sar_analysis tests/unit/application/sar_analysis tests/unit/infrastructure/temporal/test_sar_activity_projection_orchestrators.py tests/unit/infrastructure/di/test_sar_analysis_wiring.py tests/integration/persistence/sar_analysis tests/api/test_sar_analysis_routes.py tests/api/test_sar_activity_projection_routes.py -v
```
Expected: all PASS. (Integration + api require Docker.)

- [ ] **Step 2: Lint + import-linter + type check (if configured) + migration round-trip**

Run:
```bash
cd backend && uv run lint-imports && uv run ruff check src/cellar/ tests/ && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head
```
Expected: all clean; alembic round-trips; head is `058_sar_activity_projections`.

- [ ] **Step 3: Confirm the decomposition slice still passes (no regression from the `/rows` + reader edits)**

Run: `cd backend && uv run pytest tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py tests/api/test_sar_analysis_routes.py tests/integration/persistence/sar_analysis/test_decomposition_async_e2e.py -v`
Expected: all PASS — the activity extension is additive; existing decomposition behavior unchanged.

- [ ] **Step 4: Push the branch**

```bash
git push -u origin "$(git rev-parse --abbrev-ref HEAD)"
```

**Unit A is now complete.** Unit B (frontend atomic swap — `useActivityProjection`/`useHeatmapAggregation`/Infinite-Row-Model `DataGrid`) and Unit C (server-side save-collection, perf indexes, domain-model deviation note, copy pass, GitHub board) follow as their own plans — see the handoff §"Then Unit B" / §"Then Unit C".

---

## Self-review notes (author)

- **Spec coverage:** §3 Pair 2 (`sar_activity_projections` + `sar_activity_values`, migration 058) → Task 1; aggregate + repo → Tasks 2,6,7,8; activity compute + scalar port → Tasks 4,5,9,10; Start/Get/Cancel + Temporal + DI → Tasks 10,11,12,13; `/heatmap` (argmin + top-K) → Tasks 14,16; `/rows` activity extension → Tasks 15,16; activity-projection routes (200/202 + poll + cancel) → Task 16; e2e → Task 17. Unit B/C explicitly deferred (handoff staging decision).
- **Type consistency:** the orchestrator boundary uses `projection_id` as the workflow/runner arg name (`run(run_id=...)` on the runner, `schedule(projection_id=...)` on the orchestrator) — matching the decomposition slice's `run_id`/`schedule(run_id=...)` shape exactly; the activity runner's `run(run_id=...)` param IS the projection id (kept named `run_id` so the Null orchestrator's generic `run(run_id=...)` call is identical to decomposition's).
- **Keystone parity:** `pick_scalar` mirrors `colorSpecScalar` line-for-line; `channel_hash` excludes `label`; `snapshot` is `asdict(av)` JSON-safe — identical to the search grid's `activity_data` wire shape, so curve-expand works off-set.
- **No placeholders:** every step has complete code or an exact command + expected output.
