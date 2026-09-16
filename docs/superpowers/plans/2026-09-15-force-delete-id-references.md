# Force Delete Id-Only References Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make admin force delete (protocol, run, molecule) and Tier-1 hard delete account for every reference that has no FK. Each reference gets an explicit outcome: refuse, remove, clear or leave.

**Architecture:**
- A `CascadeRule` can express a reference as a plain column or as a SQL predicate (JSON, arrays, polymorphic links, state conditions).
- One exhaustive walk (`CascadeRunner.plan`) decides what a delete would do. Preview and execute both use it, so they can't disagree.
- Blockers come back as the Tier-1 409 payload.
- Set-null is audited, and ids bind as a single `uuid[]` parameter.
- A classification test keeps every id-bearing column accounted for.

**Tech Stack:** Python 3.13, SQLAlchemy 2.0 async (asyncpg), PostgreSQL 16, pytest + testcontainers, FastAPI/Pydantic v2; Next.js 16 / React 19, TanStack Query, vitest + Testing Library, orval.

**Spec:** `docs/superpowers/specs/2026-09-15-force-delete-id-references-design.md`

## Global Constraints

- Branch: `feat/force-delete-id-references`. Commit with explicit pathspecs (`git commit -m "…" -- <paths>`); the working tree has unrelated user changes (`frontend/next-env.d.ts`, `frontend/AGENTS.md`) that must never be committed.
- Commit trailer: `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`. Never add a `Claude-Session:` trailer.
- `docs/` is gitignored: add doc files with `git add -f`.
- Backend commands run from `backend/`. Unit tests: `uv run pytest tests/unit/<path> -q`. Integration and API tests need Docker: `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/<path> -q`.
- Backend lint: `uv run ruff check src/ <touched test paths>`, `uv run ruff format src/ <touched test paths>`, and `uv run lint-imports`.
- Frontend commands run from `frontend/`: `pnpm test`, `pnpm lint` (judge by exit code, not piped output), `pnpm exec tsc --noEmit`.
- pytest runs in asyncio auto mode: write `async def test_…` with no decorator.
- Every child table named by a new rule carries `workspace_id`; the runner scopes by it. No migration in this plan.
- Actions and display labels are copied verbatim from spec §4.
- No per-task review. There is one whole-branch review at the end (Task 8).

## File Structure

| File | Responsibility |
|---|---|
| `backend/src/cellar/infrastructure/cascade/rules.py` | `CascadeRule` (column or predicate), `any_id` / `any_id_text` / `uuid_array` binders |
| `backend/src/cellar/infrastructure/cascade/cascade_runner.py` | `plan` walk, `preview`, `execute` |
| `backend/src/cellar/infrastructure/cascade/inbound_refs.py` | Tier-1 blockers: FKs plus rules |
| `backend/src/cellar/infrastructure/cascade/rules_attachment.py` (new) | Attachment rules for protocols, runs, molecules, batches |
| `backend/src/cellar/infrastructure/cascade/rules_{research_organization,inventory,screening_assay,chemical_registration}.py` | Context-owned rules (spec §4) |
| `backend/src/cellar/application/admin/cascade_service.py` | `InboundReference`, `CascadePreviewResult`, `CascadeBlockedError`, service Protocol |
| `backend/src/cellar/application/admin/{cascade_preview,cascade_delete,admin_hard_delete}.py` | Use cases: preview result, 409 on blockers, `display_label` in the body |
| `backend/src/cellar/interface/routes/admin_delete.py` | `CascadePreviewResponse`, `BlockerPayload.display_label` |
| `backend/tests/integration/cascade/_rows.py` (new) | Raw-SQL row builders shared by the cascade tests |
| `backend/tests/integration/cascade/test_cascade_plan.py` (new) | Engine behaviour |
| `backend/tests/integration/cascade/test_rules_protocols_runs.py` (new) | Rules P1–P4, R1–R3 |
| `backend/tests/integration/cascade/test_rules_molecules_batches.py` (new) | Rules M1–M11, B1–B5, DR1 |
| `backend/tests/unit/cascade/test_fk_coverage.py` | Classification guard, force-delete FK check, stale keys |
| `frontend/src/shared/components/delete-blocker-list.tsx` (new) | One blocker/warning list for both admin dialogs |
| `frontend/src/shared/components/cascade-delete-dialog.tsx` | Show blockers and warnings, disable Confirm, handle a 409 |

---

### Task 1: `CascadeRule` expresses references with or without a column

**Files:**
- Modify: `backend/src/cellar/infrastructure/cascade/rules.py` (whole file)
- Create: `backend/tests/unit/infrastructure/cascade/test_rules.py`

**Interfaces:**
- Produces:
  - `CascadeRule(child_table: str, parent_table: str, action: CascadeAction, fk_column: str | None = None, match: Match | None = None, covers: tuple[str, ...] = (), label_field: str | None = None, display_label: str = "", recurse_into_entity: str | None = None)`
  - `CascadeRule.where(table: Table, parent_ids: Sequence[uuid.UUID]) -> ColumnElement[bool]`
  - `CascadeRule.references -> tuple[str, ...]`
  - `Match = Callable[[Table, Sequence[uuid.UUID]], ColumnElement[bool]]`
  - `uuid_array(ids) -> BindParameter`
  - `any_id(column, ids) -> ColumnElement[bool]`
  - `any_id_text(expr, ids) -> ColumnElement[bool]`
- Every existing rule and test builds `CascadeRule` with keyword arguments, so reordering the fields breaks no call site.

- [x] **Step 1: Write the failing test**

Create `backend/tests/unit/infrastructure/cascade/test_rules.py`:

```python
"""CascadeRule: how a reference is expressed, and what an ambiguous rule gets rejected for."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from cellar.infrastructure.cascade.rules import CascadeAction, CascadeRule, any_id

_child = sa.Table(
    "child",
    sa.MetaData(),
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("parent_id", sa.Uuid),
    sa.Column("kind", sa.String),
)


def test_a_column_rule_binds_any_number_of_ids_as_one_parameter() -> None:
    rule = CascadeRule(
        child_table="child",
        parent_table="parent",
        action=CascadeAction.CASCADE,
        fk_column="parent_id",
    )
    compiled = rule.where(_child, [uuid.uuid4() for _ in range(40_000)]).compile(
        dialect=postgresql.dialect()
    )
    assert "child.parent_id = ANY" in str(compiled)
    assert len(compiled.params) == 1
    assert rule.references == ("child.parent_id",)


def test_a_predicate_rule_uses_its_predicate_and_reports_what_it_covers() -> None:
    def match(table: sa.Table, ids: list[uuid.UUID]) -> sa.ColumnElement[bool]:
        return sa.and_(table.c.kind == "run", any_id(table.c.parent_id, ids))

    rule = CascadeRule(
        child_table="child",
        parent_table="runs",
        action=CascadeAction.CASCADE,
        match=match,
        covers=("child.parent_id",),
    )
    sql = str(rule.where(_child, [uuid.uuid4()]).compile(dialect=postgresql.dialect()))
    assert "child.kind" in sql
    assert rule.references == ("child.parent_id",)


def _first(table: sa.Table, ids: list[uuid.UUID]) -> sa.ColumnElement[bool]:
    return table.c.id == ids[0]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({}, "exactly one of fk_column and match"),
        (
            {"fk_column": "parent_id", "match": _first, "covers": ("child.parent_id",)},
            "exactly one of fk_column and match",
        ),
        ({"match": _first}, "must list what it covers"),
    ],
)
def test_an_ambiguous_rule_is_rejected(kwargs: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        CascadeRule(
            child_table="child", parent_table="parent", action=CascadeAction.BLOCK, **kwargs
        )


def test_set_null_needs_a_column_to_clear() -> None:
    with pytest.raises(ValueError, match="set_null needs an fk_column"):
        CascadeRule(
            child_table="child",
            parent_table="parent",
            action=CascadeAction.SET_NULL,
            match=_first,
            covers=("child.parent_id",),
        )
```

- [x] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/unit/infrastructure/cascade/test_rules.py -q`
Expected: FAIL. The import of `any_id` errors, and `CascadeRule` has no `match` field.

- [x] **Step 3: Replace `rules.py`**

```python
"""CascadeRule: one reference from a child table to a parent row.

A reference is either a plain column holding the parent id (``fk_column``,
with or without an FK constraint) or, where a column can't express it, a SQL
predicate (``match``). Predicates cover ids inside JSON or arrays, polymorphic
links, and conditions on the child's state. This is a persistence concept, so
it lives in infrastructure: renaming a table only touches rule files.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ARRAY, BindParameter, ColumnElement, String, Table, Uuid, any_, bindparam

from cellar.domain.shared.cascade.actions import CascadeAction  # re-export for convenience

__all__ = ["CascadeAction", "CascadeRule", "Match", "any_id", "any_id_text", "uuid_array"]

Match = Callable[[Table, Sequence[uuid.UUID]], ColumnElement[bool]]


def uuid_array(ids: Sequence[uuid.UUID]) -> BindParameter[Any]:
    """The ids as one ``uuid[]`` bind parameter.

    ``IN (...)`` binds one parameter per id, and asyncpg refuses a statement
    with more than 32,767 of them. A single HTS protocol has more wells than that.
    """
    return bindparam(None, list(ids), type_=ARRAY(Uuid(as_uuid=True)))


def any_id(column: ColumnElement[Any], ids: Sequence[uuid.UUID]) -> ColumnElement[bool]:
    """``column = ANY(:ids)``, with the ids bound as one array parameter."""
    return column == any_(uuid_array(ids))


def any_id_text(expr: ColumnElement[Any], ids: Sequence[uuid.UUID]) -> ColumnElement[bool]:
    """``any_id`` for ids stored as JSON strings.

    Compares as text, so a malformed value inside the JSON can't fail the
    whole statement on a uuid cast.
    """
    return expr == any_(bindparam(None, [str(i) for i in ids], type_=ARRAY(String())))


@dataclass(frozen=True)
class CascadeRule:
    """Rows of ``child_table`` that reference a ``parent_table`` row get ``action``
    when that parent is deleted.

    Owned by the module whose table holds the reference. Exactly one of
    ``fk_column`` (a column on ``child_table``) and ``match`` (a predicate) says
    how rows reference the parent. A ``match`` rule lists the ``"table.column"``
    references it accounts for in ``covers``, so the coverage test can see them.
    """

    child_table: str
    parent_table: str
    action: CascadeAction
    fk_column: str | None = None
    match: Match | None = None
    covers: tuple[str, ...] = ()
    label_field: str | None = None  # column on child_table used for named samples
    display_label: str = ""  # group label in previews and refusals, e.g. "Runs"
    recurse_into_entity: str | None = None  # also walk the child's own rules

    def __post_init__(self) -> None:
        if (self.fk_column is None) == (self.match is None):
            raise ValueError(f"{self.child_table}: set exactly one of fk_column and match")
        if self.match is not None and not self.covers:
            raise ValueError(f"{self.child_table}: a match rule must list what it covers")
        if self.action == CascadeAction.SET_NULL and self.fk_column is None:
            raise ValueError(f"{self.child_table}: set_null needs an fk_column to clear")

    def where(self, table: Table, parent_ids: Sequence[uuid.UUID]) -> ColumnElement[bool]:
        """Rows of ``table`` (this rule's child table) that reference any of ``parent_ids``."""
        if self.fk_column is not None:
            return any_id(table.c[self.fk_column], parent_ids)
        assert self.match is not None
        return self.match(table, parent_ids)

    @property
    def references(self) -> tuple[str, ...]:
        """The ``"table.column"`` references this rule accounts for."""
        if self.fk_column is not None:
            return (f"{self.child_table}.{self.fk_column}",)
        return self.covers
```

- [x] **Step 4: Run the cascade unit tests**

Run: `cd backend && uv run pytest tests/unit/infrastructure/cascade/ tests/unit/domain/shared/cascade/ tests/unit/cascade/ -q`
Expected: PASS. That covers the new tests plus `test_registry.py`, `test_screening_rules.py`, `test_cross_context_rules.py` and `test_fk_coverage.py`.

- [x] **Step 5: Lint and commit**

```bash
cd backend && uv run ruff check src/cellar/infrastructure/cascade/rules.py tests/unit/infrastructure/cascade/test_rules.py && uv run ruff format src/cellar/infrastructure/cascade/rules.py tests/unit/infrastructure/cascade/test_rules.py
cd .. && git add backend/src/cellar/infrastructure/cascade/rules.py backend/tests/unit/infrastructure/cascade/test_rules.py
git commit -m "feat(admin): cascade rules express references with or without a column

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -- backend/src/cellar/infrastructure/cascade/rules.py backend/tests/unit/infrastructure/cascade/test_rules.py
```

---

### Task 2: One plan walk behind preview and execute

**Files:**
- Modify: `backend/src/cellar/application/admin/cascade_service.py`
- Modify: `backend/src/cellar/infrastructure/cascade/cascade_runner.py` (whole file)
- Modify: `backend/src/cellar/infrastructure/cascade/cascade_service_impl.py:40-52`
- Modify: `backend/src/cellar/application/admin/cascade_preview.py`
- Modify: `backend/src/cellar/application/admin/cascade_delete.py`
- Modify: `backend/src/cellar/application/admin/admin_hard_delete.py:68-82`
- Modify: `backend/src/cellar/interface/routes/admin_delete.py`
- Modify: `backend/tests/integration/cascade/conftest.py`
- Create: `backend/tests/integration/cascade/_rows.py`
- Create: `backend/tests/integration/cascade/test_cascade_plan.py`
- Create: `backend/tests/unit/application/admin/test_cascade_delete_blocked.py`
- Modify: `backend/tests/integration/cascade/test_cascade_runner_preview.py:143-145`
- Modify: `backend/tests/api/test_admin_delete.py` (`test_cascade_preview_protocol`)

**Interfaces:**
- Consumes (Task 1): `CascadeRule.where`, `CascadeRule.references`, `any_id`.
- Produces:
  - `InboundReference(table, fk_column, entity_type, count, samples=[], truncated=False, display_label: str | None = None)`
  - `CascadePreviewResult(root: CascadeNode, blockers: list[InboundReference], warnings: list[InboundReference])`
  - `CascadeBlockedError(blockers: Sequence[InboundReference])`, with `.blockers: tuple[InboundReference, ...]`
  - `CascadeRunner.plan(*, parent_table, parent_id, workspace_id) -> CascadePlan`
  - `CascadeRunner.preview(...) -> CascadePreviewResult`
  - `CascadeRunner.execute(...) -> list[AuditEntry]`, which raises `CascadeBlockedError`
  - `CascadePreviewResponse` (route model)
  - Test helpers: the `_rows` module and the `extra_rules` fixture.
- **Removed:** `CascadeExecutionError`. Its only users are the runner, `cascade_service.py` and `cascade_delete.py`.

- [x] **Step 1: Add the `extra_rules` fixture**

Append to `backend/tests/integration/cascade/conftest.py`, and add `from collections.abc import Callable, Iterator` to its imports:

```python
@pytest.fixture
def extra_rules() -> Iterator[Callable[..., None]]:
    """Register cascade rules for one test; the registry is restored afterwards."""
    from cellar.infrastructure.cascade.registry import (
        _clear_for_test,
        all_rules,
        register_rules,
    )

    snapshot = all_rules()
    yield register_rules
    _clear_for_test()
    register_rules(*snapshot)
```

- [x] **Step 2: Create the row builders**

Create `backend/tests/integration/cascade/_rows.py`:

```python
"""Raw-SQL row builders for cascade integration tests.

Each helper inserts the columns its table requires and returns the new id.
Tests pass a fresh workspace id, so their rows never collide.
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

USER = uuid.UUID("bbbbbbbb-0000-0000-0000-00000000cafe")
RUN_DATE = date(2026, 9, 15)


async def _insert(session: AsyncSession, sql: str, **params: Any) -> uuid.UUID:
    params.setdefault("id", uuid.uuid4())
    await session.execute(sa.text(sql), params)
    return params["id"]


async def exists(session: AsyncSession, table: str, row_id: uuid.UUID) -> bool:
    count = await session.scalar(
        sa.text(f"SELECT count(*) FROM {table} WHERE id = :id"), {"id": row_id}
    )
    return count == 1


async def org(session: AsyncSession, ws: uuid.UUID) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
        "VALUES (:id, :ws, 'Org', 'internal', true, 1)",
        ws=ws,
    )


async def protocol(
    session: AsyncSession,
    ws: uuid.UUID,
    *,
    name: str = "Kinase assay",
    parent_protocol_id: uuid.UUID | None = None,
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO protocols (id, workspace_id, name, protocol_type, status, is_locked, "
        "dose_unit, pos_control_signal, version, protocol_version, created_by, "
        "parent_protocol_id) VALUES (:id, :ws, :name, 'biochemical', 'active', false, "
        "'uM', 'high', 1, 1, :user, :parent)",
        ws=ws,
        name=name,
        user=USER,
        parent=parent_protocol_id,
    )


async def readout_definition(session: AsyncSession, protocol_id: uuid.UUID) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO readout_definitions (id, protocol_id, name, data_type, aggregation, "
        "display_order) VALUES (:id, :proto, 'IC50', 'numeric', 'none', 0)",
        proto=protocol_id,
    )


async def run(session: AsyncSession, ws: uuid.UUID, protocol_id: uuid.UUID) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO runs (id, workspace_id, protocol_id, run_date, operator, status, "
        "is_locked, version) VALUES (:id, :ws, :proto, :d, :user, 'draft', false, 1)",
        ws=ws,
        proto=protocol_id,
        d=RUN_DATE,
        user=USER,
    )


async def plate(session: AsyncSession, run_id: uuid.UUID) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO plates (id, run_id, plate_number) VALUES (:id, :run, 1)",
        run=run_id,
    )


async def wells(
    session: AsyncSession, plate_id: uuid.UUID, count: int, *, batch_id: uuid.UUID | None = None
) -> None:
    await session.execute(
        sa.text(
            'INSERT INTO wells (id, plate_id, "row", "column", batch_id) '
            "SELECT gen_random_uuid(), :plate, 'A', g, CAST(:batch AS uuid) "
            "FROM generate_series(1, :n) AS g"
        ),
        {"plate": plate_id, "n": count, "batch": batch_id},
    )


async def readout_data(
    session: AsyncSession,
    ws: uuid.UUID,
    run_id: uuid.UUID,
    readout_definition_id: uuid.UUID,
    *,
    molecule_id: uuid.UUID | None = None,
    batch_id: uuid.UUID | None = None,
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO readout_data (id, workspace_id, run_id, readout_definition_id, "
        "molecule_id, batch_id, value_numeric) VALUES (:id, :ws, :run, :rd, :mol, :batch, 1.0)",
        ws=ws,
        run=run_id,
        rd=readout_definition_id,
        mol=molecule_id,
        batch=batch_id,
    )


async def curve(
    session: AsyncSession,
    ws: uuid.UUID,
    *,
    run_id: uuid.UUID,
    protocol_id: uuid.UUID,
    readout_definition_id: uuid.UUID,
    molecule_id: uuid.UUID,
    batch_id: uuid.UUID,
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO dose_response_curves (id, workspace_id, molecule_id, batch_id, "
        "protocol_id, run_id, readout_definition_id, curve_type, fitted_value, hill_slope, "
        "top, bottom, r_squared, num_points) VALUES (:id, :ws, :mol, :batch, :proto, :run, "
        ":rd, 'ic50', 1.0, 1.0, 100.0, 0.0, 0.99, 8)",
        ws=ws,
        mol=molecule_id,
        batch=batch_id,
        proto=protocol_id,
        run=run_id,
        rd=readout_definition_id,
    )


async def molecule(
    session: AsyncSession,
    ws: uuid.UUID,
    org_id: uuid.UUID,
    *,
    reg: str = "CC-000001",
    merged_into_id: uuid.UUID | None = None,
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO molecules (id, workspace_id, registration_number, name, molecule_type, "
        "originating_org_id, merged_into_id, version) "
        "VALUES (:id, :ws, :reg, :reg, 'small_molecule', :org, :merged, 1)",
        ws=ws,
        reg=reg,
        org=org_id,
        merged=merged_into_id,
    )


async def batch(
    session: AsyncSession, ws: uuid.UUID, molecule_id: uuid.UUID, *, number: str = "CC-000001-01"
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO batches (id, workspace_id, molecule_id, batch_number, amount_value, "
        "amount_unit, source, chemist, version) "
        "VALUES (:id, :ws, :mol, :num, 1.0, 'mg', 'synthesized', :user, 1)",
        ws=ws,
        mol=molecule_id,
        num=number,
        user=USER,
    )


async def campaign(
    session: AsyncSession,
    ws: uuid.UUID,
    *,
    name: str = "Kinase panel",
    seed_runs: list[tuple[uuid.UUID, uuid.UUID]] | None = None,
) -> uuid.UUID:
    """A draft campaign. Close it with ``set_campaign_status`` after adding rows:
    row-lock triggers reject writes to a closed campaign's results."""
    seeds = [{"run_id": str(r), "protocol_id": str(p)} for r, p in seed_runs or []]
    return await _insert(
        session,
        "INSERT INTO campaign (id, workspace_id, project_id, name, created_by, seed_runs) "
        "VALUES (:id, :ws, :proj, :name, :user, CAST(:seeds AS jsonb))",
        ws=ws,
        proj=uuid.uuid4(),
        name=name,
        user=USER,
        seeds=json.dumps(seeds),
    )


async def set_campaign_status(session: AsyncSession, campaign_id: uuid.UUID, status: str) -> None:
    await session.execute(
        sa.text("UPDATE campaign SET status = :status WHERE id = :id"),
        {"status": status, "id": campaign_id},
    )


async def channel(
    session: AsyncSession,
    campaign_id: uuid.UUID,
    protocol_id: uuid.UUID,
    readout_definition_id: uuid.UUID,
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO campaign_channel (id, campaign_id, label, protocol_id, "
        "readout_definition_id, source_kind, selection_rule, qualifier_handling) "
        "VALUES (:id, :cid, 'IC50', :proto, :rd, 'readout_data', 'latest_approved_run', "
        "'include_qualified')",
        cid=campaign_id,
        proto=protocol_id,
        rd=readout_definition_id,
    )


async def result(session: AsyncSession, campaign_id: uuid.UUID, molecule_id: uuid.UUID) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO campaign_result (id, campaign_id, molecule_id) VALUES (:id, :cid, :mol)",
        cid=campaign_id,
        mol=molecule_id,
    )


async def measurement(
    session: AsyncSession,
    result_id: uuid.UUID,
    channel_id: uuid.UUID,
    *,
    source_run_id: uuid.UUID | None = None,
    contributing_run_ids: list[uuid.UUID] | None = None,
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO campaign_measurement (id, result_id, channel_id, value_qualifier, unit, "
        "protocol_name_snapshot, protocol_version_snapshot, source_run_id, "
        "contributing_run_ids) VALUES (:id, :res, :ch, '=', 'uM', 'Kinase assay', 1, :run, "
        "CAST(:contributing AS uuid[]))",
        res=result_id,
        ch=channel_id,
        run=source_run_id,
        contributing=contributing_run_ids,
    )


async def compound_flag(
    session: AsyncSession, ws: uuid.UUID, *, protocol_id: uuid.UUID, molecule_id: uuid.UUID
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO compound_flags (id, workspace_id, molecule_id, protocol_id, flagged_by, "
        "flag_type, created_at) VALUES (:id, :ws, :mol, :proto, :user, 'pains', now())",
        ws=ws,
        mol=molecule_id,
        proto=protocol_id,
        user=USER,
    )


async def import_template(
    session: AsyncSession, ws: uuid.UUID, *, default_protocol_id: uuid.UUID
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO import_templates (id, workspace_id, name, column_mappings, created_by, "
        "default_protocol_id) VALUES (:id, :ws, 'CRO sheet', CAST('{}' AS jsonb), :user, :proto)",
        ws=ws,
        user=USER,
        proto=default_protocol_id,
    )


async def attachment(
    session: AsyncSession, ws: uuid.UUID, kind: str, owner_id: uuid.UUID
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO attachments (id, workspace_id, file_name, mime_type, file_size, "
        "storage_key, attachable_type, attachable_id, uploaded_by, version) "
        "VALUES (:id, :ws, 'plate.csv', 'text/csv', 10, 'files/plate.csv', :kind, :owner, "
        ":user, 1)",
        ws=ws,
        kind=kind,
        owner=owner_id,
        user=USER,
    )


async def sample_request(
    session: AsyncSession,
    ws: uuid.UUID,
    molecule_id: uuid.UUID,
    *,
    status: str,
    batch_id: uuid.UUID | None = None,
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO sample_requests (id, workspace_id, requester_id, molecule_id, batch_id, "
        "requested_amount_value, requested_amount_unit, purpose, priority, status, version) "
        "VALUES (:id, :ws, :user, :mol, :batch, 1.0, 'mg', 'Assay', 'normal', :status, 1)",
        ws=ws,
        user=USER,
        mol=molecule_id,
        batch=batch_id,
        status=status,
    )


async def synthesis_request(
    session: AsyncSession, ws: uuid.UUID, molecule_id: uuid.UUID, *, status: str
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO synthesis_requests (id, workspace_id, requester_id, molecule_id, "
        "requested_amount_value, requested_amount_unit, purpose, priority, status, version) "
        "VALUES (:id, :ws, :user, :mol, 5.0, 'mg', 'Scale-up', 'normal', :status, 1)",
        ws=ws,
        user=USER,
        mol=molecule_id,
        status=status,
    )


async def registered_plate(
    session: AsyncSession, ws: uuid.UUID, *, barcode: str, well_map: dict | None
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO registered_plates (id, workspace_id, barcode, plate_label, format, "
        "plate_type, registered_by, well_map, version) "
        "VALUES (:id, :ws, :bc, :bc, '384', 'compound', :user, CAST(:wm AS jsonb), 1)",
        ws=ws,
        bc=barcode,
        user=USER,
        wm=json.dumps(well_map),
    )


async def cdd_sync(session: AsyncSession, ws: uuid.UUID, molecule_id: uuid.UUID) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO cdd_molecule_sync (id, workspace_id, cdd_vault_id, cdd_molecule_id, "
        "molecule_id, last_synced_at, created_at, updated_at) "
        "VALUES (:id, :ws, 'vault-1', 42, :mol, now(), now(), now())",
        ws=ws,
        mol=molecule_id,
    )


async def synthesis_route(
    session: AsyncSession, ws: uuid.UUID, target_molecule_id: uuid.UUID
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO synthesis_routes (id, workspace_id, target_molecule_id, name, route_type, "
        "status, total_steps, source, created_by, version) "
        "VALUES (:id, :ws, :mol, 'Route A', 'linear', 'draft', 1, 'manual', :user, 1)",
        ws=ws,
        mol=target_molecule_id,
        user=USER,
    )


async def reaction_step(
    session: AsyncSession,
    route_id: uuid.UUID,
    *,
    product_molecule_id: uuid.UUID | None = None,
    batch_id: uuid.UUID | None = None,
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO reaction_steps (id, route_id, step_number, product_molecule_id, batch_id) "
        "VALUES (:id, :route, 1, :prod, :batch)",
        route=route_id,
        prod=product_molecule_id,
        batch=batch_id,
    )


async def disclosure_request(
    session: AsyncSession,
    ws: uuid.UUID,
    molecule_id: uuid.UUID,
    *,
    matched_molecule_id: uuid.UUID | None = None,
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO disclosure_requests (id, workspace_id, molecule_id, disclosed_smiles, "
        "requested_by, requested_at, matched_molecule_id, version) "
        "VALUES (:id, :ws, :mol, 'CCO', :user, now(), :matched, 1)",
        ws=ws,
        mol=molecule_id,
        user=USER,
        matched=matched_molecule_id,
    )


async def merge_event(
    session: AsyncSession,
    ws: uuid.UUID,
    *,
    source_molecule_id: uuid.UUID,
    target_molecule_id: uuid.UUID,
    disclosure_request_id: uuid.UUID | None = None,
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO merge_events (id, workspace_id, source_molecule_id, target_molecule_id, "
        "reason, merged_by, merged_at, snapshot, disclosure_request_id) "
        "VALUES (:id, :ws, :src, :tgt, 'manual_merge', :user, now(), CAST('{}' AS json), :dr)",
        ws=ws,
        src=source_molecule_id,
        tgt=target_molecule_id,
        user=USER,
        dr=disclosure_request_id,
    )
```

If an insert fails on a column this list doesn't set, compare against the NOT NULL columns in `information_schema.columns` for that table and add the missing ones. The spec lists the required columns under §0 verification; the dev DB is `chem-vault2-postgres-1`.

- [x] **Step 3: Write the failing engine tests**

Create `backend/tests/integration/cascade/test_cascade_plan.py`:

```python
"""CascadeRunner.plan: one exhaustive walk behind both preview and execute."""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from cellar.application.admin.cascade_service import CascadeBlockedError
from cellar.domain.audit_compliance.enums import AuditAction
from cellar.domain.shared.cascade.actions import CascadeAction
from cellar.infrastructure.cascade.cascade_runner import CascadeRunner
from cellar.infrastructure.cascade.rules import CascadeRule
from tests.integration.cascade import _rows

_READOUT_BLOCK = CascadeRule(
    child_table="readout_data",
    parent_table="runs",
    action=CascadeAction.BLOCK,
    fk_column="run_id",
    display_label="Test: readout rows",
)


async def _protocol_with_runs(session: AsyncSession, ws: uuid.UUID, runs: int) -> uuid.UUID:
    protocol = await _rows.protocol(session, ws)
    readout = await _rows.readout_definition(session, protocol)
    for _ in range(runs):
        run = await _rows.run(session, ws, protocol)
        await _rows.readout_data(session, ws, run, readout)
    return protocol


async def test_plan_counts_a_blocker_across_every_run_not_the_preview_sample(
    db_session: AsyncSession, extra_rules: Callable[..., None]
) -> None:
    ws = uuid.uuid4()
    protocol = await _protocol_with_runs(db_session, ws, runs=12)
    extra_rules(_READOUT_BLOCK)

    plan = await CascadeRunner(db_session).plan(
        parent_table="protocols", parent_id=protocol, workspace_id=ws
    )

    [blocker] = [b for b in plan.blockers if b.display_label == "Test: readout rows"]
    assert blocker.count == 12
    assert len(blocker.samples) == 5
    assert blocker.truncated


async def test_execute_refuses_with_every_blocker_and_changes_nothing(
    db_session: AsyncSession, extra_rules: Callable[..., None]
) -> None:
    ws = uuid.uuid4()
    protocol = await _protocol_with_runs(db_session, ws, runs=3)
    extra_rules(_READOUT_BLOCK)

    with pytest.raises(CascadeBlockedError) as refused:
        await CascadeRunner(db_session).execute(
            parent_table="protocols", parent_id=protocol, workspace_id=ws
        )

    [blocker] = [b for b in refused.value.blockers if b.display_label == "Test: readout rows"]
    assert blocker.count == 3
    assert await _rows.exists(db_session, "protocols", protocol)


async def test_warn_rules_are_listed_and_the_delete_goes_ahead(
    db_session: AsyncSession, extra_rules: Callable[..., None]
) -> None:
    ws = uuid.uuid4()
    protocol = await _protocol_with_runs(db_session, ws, runs=1)
    extra_rules(
        CascadeRule(
            child_table="readout_data",
            parent_table="runs",
            action=CascadeAction.WARN,
            fk_column="run_id",
            display_label="Test: readout rows",
        )
    )
    runner = CascadeRunner(db_session)

    preview = await runner.preview(parent_table="protocols", parent_id=protocol, workspace_id=ws)
    assert "Test: readout rows" in [w.display_label for w in preview.warnings]

    await runner.execute(parent_table="protocols", parent_id=protocol, workspace_id=ws)
    assert not await _rows.exists(db_session, "protocols", protocol)


async def test_preview_keeps_block_and_warn_rules_out_of_the_tree(
    db_session: AsyncSession, extra_rules: Callable[..., None]
) -> None:
    ws = uuid.uuid4()
    protocol = await _rows.protocol(db_session, ws)
    template = await _rows.import_template(db_session, ws, default_protocol_id=protocol)
    extra_rules(
        CascadeRule(
            child_table="import_templates",
            parent_table="protocols",
            action=CascadeAction.BLOCK,
            fk_column="default_protocol_id",
            label_field="name",
            display_label="Test: templates",
        )
    )

    preview = await CascadeRunner(db_session).preview(
        parent_table="protocols", parent_id=protocol, workspace_id=ws
    )

    assert all(child.action != CascadeAction.BLOCK for child in preview.root.children)
    [blocker] = [b for b in preview.blockers if b.display_label == "Test: templates"]
    assert blocker.samples == [{"id": str(template), "label": "CRO sheet"}]


async def test_set_null_is_audited_as_an_update(db_session: AsyncSession) -> None:
    ws = uuid.uuid4()
    parent = await _rows.protocol(db_session, ws)
    successor = await _rows.protocol(db_session, ws, name="Kinase assay v2", parent_protocol_id=parent)

    entries = await CascadeRunner(db_session).execute(
        parent_table="protocols", parent_id=parent, workspace_id=ws
    )

    [update] = [e for e in entries if e.action == AuditAction.UPDATE]
    assert (update.entity_type, update.entity_id, update.field_name) == (
        "protocol",
        successor,
        "parent_protocol_id",
    )
    assert (update.old_value, update.new_value) == (str(parent), None)


async def test_a_row_the_delete_removes_is_not_also_cleared(db_session: AsyncSession) -> None:
    ws = uuid.uuid4()
    org = await _rows.org(db_session, ws)
    molecule = await _rows.molecule(db_session, ws, org)
    request = await _rows.disclosure_request(db_session, ws, molecule, matched_molecule_id=molecule)

    entries = await CascadeRunner(db_session).execute(
        parent_table="molecules", parent_id=molecule, workspace_id=ws
    )

    assert [e.action for e in entries if e.entity_id == request] == [AuditAction.DELETE]


async def test_execute_deletes_more_rows_than_asyncpg_can_bind(db_session: AsyncSession) -> None:
    ws = uuid.uuid4()
    protocol = await _rows.protocol(db_session, ws)
    plate = await _rows.plate(db_session, await _rows.run(db_session, ws, protocol))
    await _rows.wells(db_session, plate, 33_000)

    await CascadeRunner(db_session).execute(
        parent_table="protocols", parent_id=protocol, workspace_id=ws
    )

    left = await db_session.scalar(
        sa.text("SELECT count(*) FROM wells WHERE plate_id = :plate"), {"plate": plate}
    )
    assert left == 0
```

Create `backend/tests/unit/application/admin/test_cascade_delete_blocked.py`:

```python
"""CascadeDelete turns a blocked plan into the Tier-1 refusal: a 409 naming every blocker."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from returns.result import Failure

from cellar.application.admin.admin_delete_registry import register_admin_delete
from cellar.application.admin.admin_hard_delete import BlockedByDependenciesError
from cellar.application.admin.cascade_delete import CascadeDelete, CascadeDeleteCommand
from cellar.application.admin.cascade_service import CascadeBlockedError, InboundReference


class _UoW:
    session = MagicMock()

    async def __aenter__(self) -> _UoW:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def commit(self) -> list:
        raise AssertionError("a refused delete must not commit")


async def test_a_blocked_plan_becomes_a_conflict_naming_every_blocker() -> None:
    register_admin_delete(entity_type="protocol", table="protocols", label_field="name")
    blocker = InboundReference(
        table="campaign",
        fk_column="campaign_channel.protocol_id, campaign_channel.readout_definition_id",
        entity_type="campaign",
        count=2,
        display_label="Campaigns with a channel on this protocol",
    )
    service = MagicMock()
    service.fetch_typed_name_label = AsyncMock(return_value="Kinase assay")
    service.execute = AsyncMock(side_effect=CascadeBlockedError([blocker]))
    audit = MagicMock()
    audit.record = AsyncMock()
    auth = MagicMock(workspace_id=uuid.uuid4(), user_id=uuid.uuid4(), workspace_role="admin")
    auth.is_admin = True
    auth.has_role = lambda role: True

    with patch("cellar.application.admin.cascade_delete.TIER2_ENTITY_TYPES", new={"protocol"}):
        result = await CascadeDelete(uow=_UoW(), audit=audit, cascade_service=service)(
            CascadeDeleteCommand(
                workspace_id=auth.workspace_id,
                entity_type="protocol",
                entity_id=uuid.uuid4(),
                typed_name="Kinase assay",
                reason="duplicate registration",
            ),
            auth=auth,
        )

    assert isinstance(result, Failure)
    error = result.failure()
    assert isinstance(error, BlockedByDependenciesError)
    assert error.body_extras()["blockers"][0]["display_label"] == (
        "Campaigns with a channel on this protocol"
    )
    audit.record.assert_not_called()
```

In `backend/tests/integration/cascade/test_cascade_runner_preview.py`, the preview now returns a result whose tree is `.root`. Change

```python
    tree = await runner.preview(
        parent_table="protocols", parent_id=protocol_id, workspace_id=WORKSPACE_ID
    )
```

to

```python
    tree = (
        await runner.preview(
            parent_table="protocols", parent_id=protocol_id, workspace_id=WORKSPACE_ID
        )
    ).root
```

In `backend/tests/api/test_admin_delete.py::TestCascadeTier2::test_cascade_preview_protocol`, add after `assert "children" in body`:

```python
        assert body["blockers"] == []
        assert body["warnings"] == []
```

- [x] **Step 4: Run the tests to verify they fail**

Run: `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/cascade/test_cascade_plan.py tests/unit/application/admin/test_cascade_delete_blocked.py -q`
Expected: FAIL. `CascadeBlockedError` can't be imported and `CascadeRunner` has no `plan`.

- [x] **Step 5: Replace the application types**

Replace `backend/src/cellar/application/admin/cascade_service.py`:

```python
"""Application-layer Protocol for cascade preview + execute.

Hides the SQLAlchemy session and the CascadeRunner concrete class from the
use case layer. Infrastructure provides ``UoWBackedCascadeService``.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from cellar.domain.audit_compliance.models import AuditEntry
from cellar.domain.shared.cascade import CascadeNode


@dataclass(frozen=True)
class InboundReference:
    """One group of rows still referencing the parent, found through an FK or a cascade rule."""

    table: str
    fk_column: str
    entity_type: str
    count: int
    samples: list[dict] = field(default_factory=list)
    truncated: bool = False
    display_label: str | None = None  # the rule's group label; None for a bare FK


class CascadeBlockedError(Exception):
    """A block rule matched, so the delete must not run. Carries every blocker."""

    def __init__(self, blockers: Sequence[InboundReference]) -> None:
        self.blockers = tuple(blockers)
        super().__init__(
            ", ".join(f"{b.count} {b.display_label or b.entity_type}" for b in self.blockers)
        )


@dataclass(frozen=True)
class CascadePreviewResult:
    """Tier-2 preview: a sampled tree of what goes, plus every blocker and warning."""

    root: CascadeNode
    blockers: list[InboundReference] = field(default_factory=list)
    warnings: list[InboundReference] = field(default_factory=list)


class CascadeService(Protocol):
    async def preview(
        self,
        *,
        workspace_id: uuid.UUID,
        parent_table: str,
        parent_id: uuid.UUID,
    ) -> CascadePreviewResult: ...

    async def execute(
        self,
        *,
        workspace_id: uuid.UUID,
        parent_table: str,
        parent_id: uuid.UUID,
    ) -> list[AuditEntry]:
        """Raises ``CascadeBlockedError`` when any block rule matches."""
        ...

    async def find_inbound_references(
        self,
        *,
        workspace_id: uuid.UUID,
        parent_table: str,
        parent_id: uuid.UUID,
    ) -> list[InboundReference]: ...

    async def fetch_typed_name_label(
        self,
        *,
        workspace_id: uuid.UUID,
        table: str,
        entity_id: uuid.UUID,
    ) -> str | None: ...
```

- [x] **Step 6: Replace the runner**

Replace `backend/src/cellar/infrastructure/cascade/cascade_runner.py`:

```python
"""CascadeRunner: Tier-2 preview and execute engine.

``plan`` walks every rule from the root over every matched row, not just the
preview's samples. It returns what the delete would do: rows to delete,
pointers to clear, and the block and warn rules that match. ``preview`` pairs
a sampled display tree with that plan. ``execute`` refuses when the plan has
blockers; otherwise it snapshots and applies the plan. Both go through
``plan``, so a preview can't pass a delete that execute refuses.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, Row, Table, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cellar.application.admin.cascade_service import (
    CascadeBlockedError,
    CascadePreviewResult,
    InboundReference,
)
from cellar.domain.audit_compliance.enums import AuditAction
from cellar.domain.audit_compliance.models import AuditEntry
from cellar.domain.shared.cascade.actions import CascadeAction
from cellar.domain.shared.cascade.nodes import CascadeNode
from cellar.infrastructure.cascade.label_fields import label_for_table
from cellar.infrastructure.cascade.registry import get_rules_for_parent
from cellar.infrastructure.cascade.rules import CascadeRule, any_id
from cellar.infrastructure.persistence.sqlalchemy.base import Base

__all__ = ["CascadeBlockedError", "CascadePlan", "CascadeRunner"]

SAMPLE_LIMIT = 5
_REPORTED = (CascadeAction.BLOCK, CascadeAction.WARN)


@dataclass
class CascadePlan:
    """What deleting one root row would do. Built by ``CascadeRunner.plan``."""

    # (table, ids), shallow-first. Deletes apply in reverse, so children go first.
    deletes: list[tuple[str, list[uuid.UUID]]] = field(default_factory=list)
    # Rows of id-less join tables, removed by predicate before anything else.
    link_deletes: list[tuple[str, ColumnElement[bool]]] = field(default_factory=list)
    # (table, column, [(row id, the id the column held)])
    nulls: list[tuple[str, str, list[tuple[uuid.UUID, uuid.UUID]]]] = field(default_factory=list)
    blockers: list[InboundReference] = field(default_factory=list)
    warnings: list[InboundReference] = field(default_factory=list)


@dataclass
class _Matches:
    """Distinct rows one block or warn rule matched, across the whole walk."""

    rule: CascadeRule
    ids: set[uuid.UUID] = field(default_factory=set)
    samples: list[dict] = field(default_factory=list)

    def reference(self) -> InboundReference:
        entity_type, _ = label_for_table(self.rule.child_table)
        return InboundReference(
            table=self.rule.child_table,
            fk_column=self.rule.fk_column or ", ".join(self.rule.covers),
            entity_type=entity_type,
            count=len(self.ids),
            samples=self.samples,
            truncated=len(self.ids) > len(self.samples),
            display_label=self.rule.display_label or None,
        )


def _scoped(table: Table, where: ColumnElement[bool], workspace_id: uuid.UUID) -> ColumnElement[bool]:
    if "workspace_id" in table.c:
        return where & (table.c["workspace_id"] == workspace_id)
    return where


def _label(row: Row, label_column: str | None) -> str | None:
    value = getattr(row, label_column) if label_column else None
    return None if value is None else str(value)


class CascadeRunner:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    async def preview(
        self, *, parent_table: str, parent_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> CascadePreviewResult:
        """The sampled tree of what goes, plus every blocker and warning from ``plan``."""
        root = await self._build_node_for_root(parent_table, parent_id, workspace_id)
        plan = await self.plan(
            parent_table=parent_table, parent_id=parent_id, workspace_id=workspace_id
        )
        return CascadePreviewResult(root=root, blockers=plan.blockers, warnings=plan.warnings)

    async def _build_node_for_root(
        self, table: str, id_: uuid.UUID, workspace_id: uuid.UUID
    ) -> CascadeNode:
        entity_type, _label_col = label_for_table(table)
        sa_table = Base.metadata.tables[table]
        root_label = await self._fetch_label(sa_table, id_, workspace_id)
        root = CascadeNode(
            entity_type=entity_type,
            table=table,
            display_label=entity_type,
            count=1,
            samples=[{"id": str(id_), "label": root_label}],
            truncated=False,
            action=CascadeAction.CASCADE,
            children=[],
        )
        await self._populate_children(root, parent_id=id_, workspace_id=workspace_id)
        return root

    async def _populate_children(
        self, node: CascadeNode, *, parent_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> None:
        for rule in get_rules_for_parent(node.table):
            if rule.action in _REPORTED:
                continue  # reported exhaustively by plan(), not per sampled branch
            child_table = Base.metadata.tables[rule.child_table]
            where = _scoped(child_table, rule.where(child_table, [parent_id]), workspace_id)
            count = await self._count(child_table, where)
            if count == 0:
                continue
            samples = await self._fetch_samples(child_table, where, rule.label_field)
            child_node = CascadeNode(
                entity_type=label_for_table(rule.child_table)[0],
                table=rule.child_table,
                display_label=rule.display_label or rule.child_table,
                count=count,
                samples=samples,
                truncated=count > len(samples),
                action=rule.action,
                children=[],
            )
            node.children.append(child_node)

            if rule.action == CascadeAction.CASCADE and rule.recurse_into_entity:
                # Each sampled child row becomes a recursion seed (display only).
                for s in samples:
                    sub = CascadeNode(
                        entity_type=child_node.entity_type,
                        table=rule.child_table,
                        display_label=s.get("label") or child_node.entity_type,
                        count=1,
                        samples=[s],
                        truncated=False,
                        action=CascadeAction.CASCADE,
                        children=[],
                    )
                    await self._populate_children(
                        sub, parent_id=uuid.UUID(s["id"]), workspace_id=workspace_id
                    )
                    child_node.children.append(sub)

    async def _count(self, table: Table, where: ColumnElement[bool]) -> int:
        stmt = select(func.count()).select_from(table).where(where)
        return int((await self._session.execute(stmt)).scalar_one())

    async def _fetch_samples(
        self, table: Table, where: ColumnElement[bool], label_column: str | None
    ) -> list[dict]:
        # Association tables may have no id column: count only.
        if "id" not in table.c:
            return []
        label = label_column if label_column and label_column in table.c else None
        cols = [table.c["id"], table.c[label]] if label else [table.c["id"]]
        rows = (await self._session.execute(select(*cols).where(where).limit(SAMPLE_LIMIT))).all()
        return [{"id": str(row.id), "label": _label(row, label)} for row in rows]

    async def _fetch_label(
        self, table: Table, id_: uuid.UUID, workspace_id: uuid.UUID
    ) -> str | None:
        _et, label_col = label_for_table(table.name)
        if not label_col or label_col not in table.c:
            return None
        stmt = select(table.c[label_col]).where(_scoped(table, table.c.id == id_, workspace_id))
        return (await self._session.execute(stmt)).scalar_one_or_none()

    # ------------------------------------------------------------------
    # Plan
    # ------------------------------------------------------------------

    async def plan(
        self, *, parent_table: str, parent_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> CascadePlan:
        """Walk every rule over every matched row; change nothing."""
        plan = CascadePlan()
        matches: dict[CascadeRule, _Matches] = {}
        walked: dict[str, set[uuid.UUID]] = {parent_table: {parent_id}}
        await self._walk(parent_table, [parent_id], workspace_id, plan, matches, walked)

        deleted = {(parent_table, parent_id)} | {
            (table, row_id) for table, ids in plan.deletes for row_id in ids
        }
        plan.nulls = [
            (table, column, kept)
            for table, column, rows in plan.nulls
            if (kept := [(row_id, old) for row_id, old in rows if (table, row_id) not in deleted])
        ]
        for found in matches.values():
            target = plan.blockers if found.rule.action == CascadeAction.BLOCK else plan.warnings
            target.append(found.reference())
        return plan

    async def _walk(
        self,
        table: str,
        parent_ids: list[uuid.UUID],
        workspace_id: uuid.UUID,
        plan: CascadePlan,
        matches: dict[CascadeRule, _Matches],
        walked: dict[str, set[uuid.UUID]],
    ) -> None:
        for rule in get_rules_for_parent(table):
            child = Base.metadata.tables[rule.child_table]
            where = _scoped(child, rule.where(child, parent_ids), workspace_id)

            if rule.action in _REPORTED:
                await self._match(rule, child, where, matches)
                continue

            if "id" not in child.c:
                # Join rows carry no business data; they go by predicate, unaudited.
                if rule.action == CascadeAction.CASCADE:
                    plan.link_deletes.append((rule.child_table, where))
                continue

            if rule.action == CascadeAction.SET_NULL:
                assert rule.fk_column is not None  # CascadeRule guarantees it
                column = child.c[rule.fk_column]
                rows = (await self._session.execute(select(child.c.id, column).where(where))).all()
                if rows:
                    plan.nulls.append((rule.child_table, rule.fk_column, [(r[0], r[1]) for r in rows]))
                continue

            ids = [r[0] for r in (await self._session.execute(select(child.c.id).where(where))).all()]
            if not ids:
                continue
            # A row reached twice (e.g. readout data under its definition and its
            # run) is listed twice: dropping the second copy would reorder deletes
            # and break FKs. Snapshots dedupe instead.
            plan.deletes.append((rule.child_table, ids))
            if rule.recurse_into_entity:
                seen = walked.setdefault(rule.child_table, set())
                fresh = [row_id for row_id in ids if row_id not in seen]
                seen.update(fresh)
                if fresh:
                    await self._walk(rule.child_table, fresh, workspace_id, plan, matches, walked)

    async def _match(
        self,
        rule: CascadeRule,
        child: Table,
        where: ColumnElement[bool],
        matches: dict[CascadeRule, _Matches],
    ) -> None:
        label = rule.label_field if rule.label_field and rule.label_field in child.c else None
        cols = [child.c.id, child.c[label]] if label else [child.c.id]
        rows = (await self._session.execute(select(*cols).where(where))).all()
        if not rows:
            return
        found = matches.setdefault(rule, _Matches(rule))
        for row in rows:
            if row.id in found.ids:
                continue
            found.ids.add(row.id)
            if len(found.samples) < SAMPLE_LIMIT:
                found.samples.append({"id": str(row.id), "label": _label(row, label)})

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    async def execute(
        self, *, parent_table: str, parent_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> list[AuditEntry]:
        """Apply the plan, or raise ``CascadeBlockedError`` when any block rule matches.

        Returns the entries for the caller's AuditOperation: a DELETE with a full
        snapshot for every removed row, and an UPDATE for every cleared pointer.
        """
        plan = await self.plan(
            parent_table=parent_table, parent_id=parent_id, workspace_id=workspace_id
        )
        if plan.blockers:
            raise CascadeBlockedError(plan.blockers)

        now = datetime.now(UTC)
        entries = await self._snapshot_deletes(
            [(parent_table, [parent_id]), *plan.deletes], workspace_id, now
        )
        for table, column, rows in plan.nulls:
            entity_type, _ = label_for_table(table)
            entries.extend(
                AuditEntry(
                    entity_type=entity_type,
                    entity_id=row_id,
                    field_name=column,
                    action=AuditAction.UPDATE,
                    old_value=str(old),
                    new_value=None,
                    timestamp=now,
                )
                for row_id, old in rows
            )

        for table, where in plan.link_deletes:
            await self._session.execute(delete(Base.metadata.tables[table]).where(where))
        for table, column, rows in plan.nulls:
            sa_table = Base.metadata.tables[table]
            await self._session.execute(
                update(sa_table)
                .where(any_id(sa_table.c.id, [row_id for row_id, _ in rows]))
                .values({column: None})
            )
        for table, ids in reversed(plan.deletes):
            sa_table = Base.metadata.tables[table]
            await self._session.execute(delete(sa_table).where(any_id(sa_table.c.id, ids)))

        root = Base.metadata.tables[parent_table]
        await self._session.execute(
            delete(root).where(_scoped(root, root.c.id == parent_id, workspace_id))
        )
        return entries

    async def _snapshot_deletes(
        self,
        deletes: list[tuple[str, list[uuid.UUID]]],
        workspace_id: uuid.UUID,
        now: datetime,
    ) -> list[AuditEntry]:
        entries: list[AuditEntry] = []
        done: set[tuple[str, uuid.UUID]] = set()
        for table_name, ids in deletes:
            fresh = [row_id for row_id in ids if (table_name, row_id) not in done]
            if not fresh:
                continue
            done.update((table_name, row_id) for row_id in fresh)
            sa_table = Base.metadata.tables[table_name]
            where = _scoped(sa_table, any_id(sa_table.c.id, fresh), workspace_id)
            rows = (await self._session.execute(sa_table.select().where(where))).mappings().all()
            entity_type, _ = label_for_table(table_name)
            entries.extend(
                AuditEntry(
                    entity_type=entity_type,
                    entity_id=row["id"],
                    field_name="*",
                    action=AuditAction.DELETE,
                    old_value=json.dumps(dict(row), default=str, sort_keys=True),
                    new_value=None,
                    timestamp=now,
                )
                for row in rows
            )
        return entries
```

- [x] **Step 7: Wire the service, use cases and route**

In `backend/src/cellar/infrastructure/cascade/cascade_service_impl.py`:
- Import `CascadePreviewResult` alongside `CascadeService` and `InboundReference` from `cellar.application.admin.cascade_service`.
- Drop the unused `CascadeNode` import.
- Change `preview`'s return annotation to `-> CascadePreviewResult`. Its body already returns `runner.preview(...)`.

Replace the body of `backend/src/cellar/application/admin/cascade_preview.py` from the imports down:

```python
# application/admin/cascade_preview.py
from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.admin.admin_delete_registry import get_entry
from cellar.application.admin.cascade_service import CascadePreviewResult, CascadeService
from cellar.application.admin.tier2_entities import TIER2_ENTITY_TYPES
from cellar.application.auth import AuthContext, require_admin, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import (
    DomainError,
    NotFoundError,
)


@dataclass(frozen=True, kw_only=True)
class CascadePreviewQuery(Command):
    workspace_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID


class CascadePreview:
    def __init__(self, uow: UnitOfWork, cascade_service: CascadeService) -> None:
        self._uow = uow
        self._cascade_service = cascade_service

    async def __call__(
        self,
        input: CascadePreviewQuery,
        auth: AuthContext | None = None,
    ) -> Result[CascadePreviewResult, DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)
        if input.entity_type not in TIER2_ENTITY_TYPES:
            return Failure(NotFoundError("entity_type", input.entity_type))
        entry = get_entry(input.entity_type)
        if entry is None:
            return Failure(NotFoundError("entity_type", input.entity_type))

        async with self._uow:
            result = await self._cascade_service.preview(
                parent_table=entry.table,
                parent_id=input.entity_id,
                workspace_id=input.workspace_id,
            )
            return Success(result)
```

In `backend/src/cellar/application/admin/cascade_delete.py`:
- Replace the `cascade_service` import block with the lines below.
- Replace the `except CascadeExecutionError as e: return Failure(ValidationError(str(e)))` block. `ValidationError` stays imported, because the reason and typed-name checks still use it.

```python
from cellar.application.admin.admin_hard_delete import BlockedByDependenciesError
from cellar.application.admin.cascade_service import (
    CascadeBlockedError,
    CascadeService,
)
```

```python
            except CascadeBlockedError as blocked:
                # Same 409 body as a Tier-1 refusal, naming every blocker.
                return Failure(BlockedByDependenciesError(blocked.blockers))
```

In `backend/src/cellar/application/admin/admin_hard_delete.py`, `BlockedByDependenciesError.body_extras` gains the label. The per-blocker dict becomes:

```python
                {
                    "table": r.table,
                    "entity_type": r.entity_type,
                    "fk_column": r.fk_column,
                    "count": r.count,
                    "samples": r.samples,
                    "truncated": r.truncated,
                    "display_label": r.display_label,
                }
```

In `backend/src/cellar/interface/routes/admin_delete.py`:
1. Add `from cellar.application.admin.cascade_service import CascadePreviewResult, InboundReference`.
2. Replace the `BlockerPayload` class:

```python
class BlockerPayload(BaseModel):
    table: str
    entity_type: str
    fk_column: str
    count: int
    samples: list[dict]
    truncated: bool
    display_label: str | None = None

    @classmethod
    def from_reference(cls, r: InboundReference) -> BlockerPayload:
        return cls(
            table=r.table,
            entity_type=r.entity_type,
            fk_column=r.fk_column,
            count=r.count,
            samples=r.samples,
            truncated=r.truncated,
            display_label=r.display_label,
        )
```

3. After `CascadeNodeResponse.model_rebuild()`, add:

```python
class CascadePreviewResponse(CascadeNodeResponse):
    """The preview tree's root, plus what would refuse the delete (blockers)
    and what it leaves changed but not removed (warnings)."""

    blockers: list[BlockerPayload] = []
    warnings: list[BlockerPayload] = []

    @classmethod
    def from_result(cls, result: CascadePreviewResult) -> CascadePreviewResponse:
        root = CascadeNodeResponse.from_domain(result.root)
        return cls(
            **root.model_dump(),
            blockers=[BlockerPayload.from_reference(b) for b in result.blockers],
            warnings=[BlockerPayload.from_reference(w) for w in result.warnings],
        )
```

4. In `cascade_preview`, use `response_model=CascadePreviewResponse` and the return annotation `-> CascadePreviewResponse`, and end with:

```python
    return CascadePreviewResponse.from_result(result_to_response(res))
```

5. Give the `cascade_delete` decorator `responses={409: {"model": BlockedByDependenciesResponse}}`.

- [x] **Step 8: Run the tests to verify they pass**

Run:
```bash
cd backend && uv run pytest tests/unit/application/admin/ tests/unit/infrastructure/cascade/ tests/unit/cascade/ -q
DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/cascade/ tests/api/test_admin_delete.py -q
```
Expected: PASS, including every pre-existing cascade test. `test_execute_deletes_more_rows_than_asyncpg_can_bind` takes a few seconds.

- [x] **Step 9: Lint and commit**

```bash
cd backend && uv run ruff check src/ tests/integration/cascade tests/unit/application/admin tests/api/test_admin_delete.py && uv run ruff format src/cellar/infrastructure/cascade src/cellar/application/admin src/cellar/interface/routes/admin_delete.py tests/integration/cascade tests/unit/application/admin tests/api/test_admin_delete.py && uv run lint-imports
cd .. && git add backend/src/cellar/application/admin/cascade_service.py backend/src/cellar/infrastructure/cascade/cascade_runner.py backend/src/cellar/infrastructure/cascade/cascade_service_impl.py backend/src/cellar/application/admin/cascade_preview.py backend/src/cellar/application/admin/cascade_delete.py backend/src/cellar/application/admin/admin_hard_delete.py backend/src/cellar/interface/routes/admin_delete.py backend/tests/integration/cascade/conftest.py backend/tests/integration/cascade/_rows.py backend/tests/integration/cascade/test_cascade_plan.py backend/tests/integration/cascade/test_cascade_runner_preview.py backend/tests/unit/application/admin/test_cascade_delete_blocked.py backend/tests/api/test_admin_delete.py
git commit -m "feat(admin): one exhaustive plan walk behind force-delete preview and execute

Preview lists every blocker and warning, not just those under the first
five sampled children. Execute refuses with the Tier-1 409 body. Set-null
updates are audited, and ids bind as one uuid[] parameter, so deletes past
asyncpg's 32,767-parameter cap work.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -- backend/src/cellar/application/admin/cascade_service.py backend/src/cellar/infrastructure/cascade/cascade_runner.py backend/src/cellar/infrastructure/cascade/cascade_service_impl.py backend/src/cellar/application/admin/cascade_preview.py backend/src/cellar/application/admin/cascade_delete.py backend/src/cellar/application/admin/admin_hard_delete.py backend/src/cellar/interface/routes/admin_delete.py backend/tests/integration/cascade/conftest.py backend/tests/integration/cascade/_rows.py backend/tests/integration/cascade/test_cascade_plan.py backend/tests/integration/cascade/test_cascade_runner_preview.py backend/tests/unit/application/admin/test_cascade_delete_blocked.py backend/tests/api/test_admin_delete.py
```

---

### Task 3: Tier-1 hard delete also refuses on rule references

**Files:**
- Modify: `backend/src/cellar/infrastructure/cascade/inbound_refs.py` (whole file)
- Test: `backend/tests/integration/cascade/test_inbound_refs.py` (append one test)

**Interfaces:**
- Consumes: `CascadeRule.where` / `.references` / `.fk_column` (Task 1), `InboundReference.display_label` (Task 2), `_rows` and `extra_rules` (Task 2).
- Produces: `find_inbound_references(...)`, whose signature is unchanged. Its result now also holds one `InboundReference` per matching rule registered for the parent, whatever the rule's action (spec D7). Rules on a real FK to the parent are skipped, because the FK walk already counts them.

- [x] **Step 1: Write the failing test**

Append to `backend/tests/integration/cascade/test_inbound_refs.py`, and add the imports it needs: `from collections.abc import Callable`, `from cellar.domain.shared.cascade.actions import CascadeAction`, `from cellar.infrastructure.cascade.rules import CascadeRule` and `from tests.integration.cascade import _rows`.

```python
async def test_a_rule_reference_blocks_tier1_whatever_its_action(
    db_session: AsyncSession, extra_rules: Callable[..., None]
) -> None:
    ws = uuid.uuid4()
    protocol = await _rows.protocol(db_session, ws)
    await _rows.compound_flag(db_session, ws, protocol_id=protocol, molecule_id=uuid.uuid4())
    await _rows.run(db_session, ws, protocol)
    extra_rules(
        CascadeRule(
            child_table="compound_flags",
            parent_table="protocols",
            action=CascadeAction.WARN,
            fk_column="protocol_id",
            display_label="Test: flags",
        )
    )

    refs = await find_inbound_references(
        db_session, parent_table="protocols", parent_id=protocol, workspace_id=ws
    )

    [flags] = [r for r in refs if r.display_label == "Test: flags"]
    assert (flags.table, flags.fk_column, flags.count) == ("compound_flags", "protocol_id", 1)
    # runs.protocol_id is a real FK: the FK walk counts it once, never again as a rule.
    assert [r.table for r in refs].count("runs") == 1
```

- [x] **Step 2: Run it to verify it fails**

Run: `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/cascade/test_inbound_refs.py -q`
Expected: FAIL, with `ValueError: not enough values to unpack` (no rule blocker).

- [x] **Step 3: Replace `inbound_refs.py`**

```python
"""Tier-1 RESTRICT blockers: every row still referencing (table, id).

Two sources, both workspace-scoped:
- every SQLAlchemy ForeignKey pointing at ``<parent_table>.id``;
- every cascade rule registered for the parent whose reference isn't one of
  those FKs (id-only columns, JSON, polymorphic links), whatever its action,
  because a Tier-1 delete removes nothing but the row itself.

Association/join tables that have no ``id`` column are count-only.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ColumnElement, Table, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cellar.application.admin.cascade_service import InboundReference
from cellar.infrastructure.cascade.label_fields import label_for_table
from cellar.infrastructure.cascade.registry import get_rules_for_parent
from cellar.infrastructure.cascade.rules import CascadeRule
from cellar.infrastructure.persistence.sqlalchemy.base import Base

__all__ = ["InboundReference", "find_inbound_references"]


async def find_inbound_references(
    session: AsyncSession,
    *,
    parent_table: str,
    parent_id: uuid.UUID,
    workspace_id: uuid.UUID,
    sample_limit: int = 5,
) -> list[InboundReference]:
    """Return every group of rows referencing (parent_table, parent_id)."""
    references: list[InboundReference] = []

    for table in Base.metadata.tables.values():
        if table.name == parent_table:
            continue
        for fk in _foreign_keys_pointing_to(table, parent_table):
            column = fk.parent.name
            ref = await _reference(
                session,
                table,
                table.c[column] == parent_id,
                workspace_id,
                sample_limit,
                fk_column=column,
                label_column=label_for_table(table.name)[1],
            )
            if ref is not None:
                references.append(ref)

    for rule in get_rules_for_parent(parent_table):
        if _is_fk_to(rule, parent_table):
            continue  # counted by the FK walk above
        table = Base.metadata.tables[rule.child_table]
        ref = await _reference(
            session,
            table,
            rule.where(table, [parent_id]),
            workspace_id,
            sample_limit,
            fk_column=rule.fk_column or ", ".join(rule.covers),
            label_column=rule.label_field,
            display_label=rule.display_label or None,
        )
        if ref is not None:
            references.append(ref)

    return references


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _foreign_keys_pointing_to(table: Table, parent_table: str):
    """Yield ForeignKey objects on ``table`` that point at ``<parent_table>.id``."""
    for col in table.columns:
        for fk in col.foreign_keys:
            target_table, _, target_col = fk.target_fullname.partition(".")
            if target_table == parent_table and target_col == "id":
                yield fk


def _is_fk_to(rule: CascadeRule, parent_table: str) -> bool:
    if rule.fk_column is None:
        return False
    column = Base.metadata.tables[rule.child_table].c[rule.fk_column]
    return any(fk.target_fullname == f"{parent_table}.id" for fk in column.foreign_keys)


async def _reference(
    session: AsyncSession,
    table: Table,
    where: ColumnElement[bool],
    workspace_id: uuid.UUID,
    sample_limit: int,
    *,
    fk_column: str,
    label_column: str | None,
    display_label: str | None = None,
) -> InboundReference | None:
    if "workspace_id" in table.c:
        where = where & (table.c["workspace_id"] == workspace_id)
    count = int((await session.execute(select(func.count()).select_from(table).where(where))).scalar_one())
    if count == 0:
        return None

    samples: list[dict] = []
    if "id" in table.c:  # association tables are count-only
        label = label_column if label_column and label_column in table.c else None
        cols = [table.c["id"], table.c[label]] if label else [table.c["id"]]
        rows = (await session.execute(select(*cols).where(where).limit(sample_limit))).all()
        samples = [
            {
                "id": str(row[0]),
                "label": None if label is None or row[1] is None else str(row[1]),
            }
            for row in rows
        ]

    entity_type, _ = label_for_table(table.name)
    return InboundReference(
        table=table.name,
        fk_column=fk_column,
        entity_type=entity_type,
        count=count,
        samples=samples,
        truncated=count > len(samples),
        display_label=display_label,
    )
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/cascade/ tests/api/test_admin_delete.py -q`
Expected: PASS (the new test plus the existing inbound-ref, workspace-isolation and API tests).

- [x] **Step 5: Lint and commit**

```bash
cd backend && uv run ruff check src/cellar/infrastructure/cascade/inbound_refs.py tests/integration/cascade/test_inbound_refs.py && uv run ruff format src/cellar/infrastructure/cascade/inbound_refs.py tests/integration/cascade/test_inbound_refs.py
cd .. && git add backend/src/cellar/infrastructure/cascade/inbound_refs.py backend/tests/integration/cascade/test_inbound_refs.py
git commit -m "feat(admin): Tier-1 hard delete refuses on cascade-rule references too

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -- backend/src/cellar/infrastructure/cascade/inbound_refs.py backend/tests/integration/cascade/test_inbound_refs.py
```

---

### Task 4: Rules for what references protocols and runs

**Files:**
- Create: `backend/src/cellar/infrastructure/cascade/rules_attachment.py` (P4, R3, and M9 and B3, which Task 5 tests)
- Modify: `backend/src/cellar/infrastructure/di/_attachment.py` (import the rule module in `register_attachment`)
- Modify: `backend/src/cellar/infrastructure/cascade/rules_research_organization.py` (P1, R1, R2, and M2, which Task 5 tests)
- Modify: `backend/src/cellar/infrastructure/cascade/rules_inventory.py` (P2)
- Modify: `backend/src/cellar/infrastructure/cascade/rules_screening_assay.py` (P3)
- Modify: `backend/tests/integration/cascade/conftest.py` and `backend/tests/unit/cascade/test_fk_coverage.py` (add `rules_attachment` to `_CASCADE_MODULES`)
- Create: `backend/tests/integration/cascade/test_rules_protocols_runs.py`
- Modify: `backend/tests/api/test_admin_delete.py` (blocked cascade delete returns 409)

**Interfaces:**
- Consumes: `CascadeRule`, `Match`, `any_id`, `any_id_text`, `uuid_array` (Task 1); `CascadeRunner.plan/preview/execute`, `CascadeBlockedError` (Task 2); `_rows` (Task 2).
- Produces: registered rules with these exact display labels, which Task 7's frontend test and Task 6's guard test rely on:
  - "Campaigns with a channel on this protocol"
  - "Plate import templates defaulting to this protocol"
  - "Compound flags"
  - "Attachments (files stay in storage)"
  - "Closed or superseded campaigns citing this run"
  - "Draft campaigns using this run (their cells re-resolve without it on the next refresh)"
  - "Campaigns with a row for this molecule"

- [x] **Step 1: Write the failing tests**

Create `backend/tests/integration/cascade/test_rules_protocols_runs.py`:

```python
"""Force-delete rules for what references protocols and runs without an FK."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from cellar.application.admin.cascade_service import CascadeBlockedError, InboundReference
from cellar.infrastructure.cascade.cascade_runner import CascadeRunner
from tests.integration.cascade import _rows

_DRAFT_WARNING = (
    "Draft campaigns using this run (their cells re-resolve without it on the next refresh)"
)


def _labels(refs: list[InboundReference] | tuple[InboundReference, ...]) -> dict:
    return {r.display_label: [s["label"] for s in r.samples] for r in refs}


async def test_a_campaign_channel_on_the_protocol_blocks(db_session: AsyncSession) -> None:
    ws = uuid.uuid4()
    protocol = await _rows.protocol(db_session, ws)
    readout = await _rows.readout_definition(db_session, protocol)
    campaign = await _rows.campaign(db_session, ws, name="Kinase panel")
    await _rows.channel(db_session, campaign, protocol, readout)
    runner = CascadeRunner(db_session)

    preview = await runner.preview(parent_table="protocols", parent_id=protocol, workspace_id=ws)
    assert _labels(preview.blockers)["Campaigns with a channel on this protocol"] == ["Kinase panel"]

    with pytest.raises(CascadeBlockedError):
        await runner.execute(parent_table="protocols", parent_id=protocol, workspace_id=ws)
    assert await _rows.exists(db_session, "protocols", protocol)


async def test_a_channel_naming_only_one_of_its_readouts_still_blocks(
    db_session: AsyncSession,
) -> None:
    ws = uuid.uuid4()
    protocol = await _rows.protocol(db_session, ws)
    readout = await _rows.readout_definition(db_session, protocol)
    counter_screen = await _rows.protocol(db_session, ws, name="Counter-screen")
    campaign = await _rows.campaign(db_session, ws)
    await _rows.channel(db_session, campaign, counter_screen, readout)

    plan = await CascadeRunner(db_session).plan(
        parent_table="protocols", parent_id=protocol, workspace_id=ws
    )

    assert "Campaigns with a channel on this protocol" in _labels(plan.blockers)


async def test_an_import_template_defaulting_to_the_protocol_blocks(
    db_session: AsyncSession,
) -> None:
    ws = uuid.uuid4()
    protocol = await _rows.protocol(db_session, ws)
    await _rows.import_template(db_session, ws, default_protocol_id=protocol)

    plan = await CascadeRunner(db_session).plan(
        parent_table="protocols", parent_id=protocol, workspace_id=ws
    )

    assert _labels(plan.blockers) == {
        "Plate import templates defaulting to this protocol": ["CRO sheet"]
    }


async def test_flags_and_attachments_go_with_the_protocol_and_its_runs(
    db_session: AsyncSession,
) -> None:
    ws = uuid.uuid4()
    protocol = await _rows.protocol(db_session, ws)
    run = await _rows.run(db_session, ws, protocol)
    flag = await _rows.compound_flag(db_session, ws, protocol_id=protocol, molecule_id=uuid.uuid4())
    protocol_file = await _rows.attachment(db_session, ws, "protocol", protocol)
    run_file = await _rows.attachment(db_session, ws, "run", run)
    # Same id, different owner type: not this protocol's file.
    unrelated_file = await _rows.attachment(db_session, ws, "molecule", protocol)

    entries = await CascadeRunner(db_session).execute(
        parent_table="protocols", parent_id=protocol, workspace_id=ws
    )

    deleted = {(e.entity_type, e.entity_id) for e in entries}
    assert {("compound_flag", flag), ("attachment", protocol_file), ("attachment", run_file)} <= deleted
    assert not await _rows.exists(db_session, "attachments", run_file)
    assert await _rows.exists(db_session, "attachments", unrelated_file)


@pytest.mark.parametrize("citation", ["seed run", "source run", "contributing run"])
async def test_a_closed_campaign_citing_the_run_blocks(
    db_session: AsyncSession, citation: str
) -> None:
    ws = uuid.uuid4()
    protocol = await _rows.protocol(db_session, ws)
    run = await _rows.run(db_session, ws, protocol)
    seeds = [(run, protocol)] if citation == "seed run" else []
    campaign = await _rows.campaign(db_session, ws, name="Closed panel", seed_runs=seeds)
    if citation != "seed run":
        # A channel on another protocol, so only the run citation can match.
        channel = await _rows.channel(db_session, campaign, uuid.uuid4(), uuid.uuid4())
        result = await _rows.result(db_session, campaign, uuid.uuid4())
        await _rows.measurement(
            db_session,
            result,
            channel,
            source_run_id=run if citation == "source run" else None,
            contributing_run_ids=[run] if citation == "contributing run" else None,
        )
    await _rows.set_campaign_status(db_session, campaign, "closed")

    with pytest.raises(CascadeBlockedError) as refused:
        await CascadeRunner(db_session).execute(parent_table="runs", parent_id=run, workspace_id=ws)

    assert _labels(refused.value.blockers) == {
        "Closed or superseded campaigns citing this run": ["Closed panel"]
    }


async def test_a_draft_seeded_from_the_run_warns_and_keeps_its_seed_list(
    db_session: AsyncSession,
) -> None:
    ws = uuid.uuid4()
    protocol = await _rows.protocol(db_session, ws)
    run = await _rows.run(db_session, ws, protocol)
    campaign = await _rows.campaign(db_session, ws, name="Draft panel", seed_runs=[(run, protocol)])
    runner = CascadeRunner(db_session)

    preview = await runner.preview(parent_table="runs", parent_id=run, workspace_id=ws)
    assert preview.blockers == []
    assert _labels(preview.warnings) == {_DRAFT_WARNING: ["Draft panel"]}

    await runner.execute(parent_table="runs", parent_id=run, workspace_id=ws)

    assert not await _rows.exists(db_session, "runs", run)
    seeds = await db_session.scalar(
        sa.text("SELECT seed_runs FROM campaign WHERE id = :id"), {"id": campaign}
    )
    assert seeds == [{"run_id": str(run), "protocol_id": str(protocol)}]
```

Append to `backend/tests/api/test_admin_delete.py::TestCascadeTier2`:

```python
    async def test_cascade_delete_blocked_returns_every_blocker(
        self, client: AsyncClient, api_app: FastAPI, workspace_id: uuid.UUID
    ) -> None:
        """A block rule refuses the cascade with the Tier-1 409 body."""
        protocol_id = uuid.uuid4()
        proto_name = f"T14-Blocked-{protocol_id.hex[:6]}"
        await _raw_insert_protocol(api_app, protocol_id, proto_name, workspace_id)
        async with await _get_session(api_app) as session:
            await session.execute(
                sa.text(
                    "INSERT INTO import_templates (id, workspace_id, name, column_mappings, "
                    "created_by, default_protocol_id) "
                    "VALUES (:id, :ws, 'CRO sheet', CAST('{}' AS jsonb), :user, :proto)"
                ),
                {
                    "id": uuid.uuid4(),
                    "ws": workspace_id,
                    "user": uuid.uuid4(),
                    "proto": protocol_id,
                },
            )
            await session.commit()

        resp = await client.request(
            "DELETE",
            f"/api/v1/admin/protocol/{protocol_id}/cascade",
            json={"typed_name": proto_name, "reason": "duplicate registration"},
        )

        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body["error"] == "delete_blocked_by_dependencies"
        assert [b["display_label"] for b in body["blockers"]] == [
            "Plate import templates defaulting to this protocol"
        ]
```

Append to `backend/tests/api/test_admin_delete.py::TestAdminHardDelete`:

```python
    async def test_a_rule_reference_blocks_tier1_hard_delete(
        self, client: AsyncClient, api_app: FastAPI, workspace_id: uuid.UUID
    ) -> None:
        """A compound flag has no FK to its protocol, but still refuses a Tier-1 delete."""
        protocol_id = uuid.uuid4()
        await _raw_insert_protocol(api_app, protocol_id, f"T1-Flagged-{protocol_id.hex[:6]}", workspace_id)
        async with await _get_session(api_app) as session:
            await session.execute(
                sa.text(
                    "INSERT INTO compound_flags (id, workspace_id, molecule_id, protocol_id, "
                    "flagged_by, flag_type, created_at) "
                    "VALUES (:id, :ws, :mol, :proto, :user, 'pains', now())"
                ),
                {
                    "id": uuid.uuid4(),
                    "ws": workspace_id,
                    "mol": uuid.uuid4(),
                    "proto": protocol_id,
                    "user": uuid.uuid4(),
                },
            )
            await session.commit()

        resp = await _admin_delete(client, "protocol", str(protocol_id), "duplicate registration")

        assert resp.status_code == 409, resp.text
        [blocker] = resp.json()["blockers"]
        assert (blocker["table"], blocker["display_label"], blocker["count"]) == (
            "compound_flags",
            "Compound flags",
            1,
        )
```

- [x] **Step 2: Run them to verify they fail**

Run: `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/cascade/test_rules_protocols_runs.py "tests/api/test_admin_delete.py::TestCascadeTier2::test_cascade_delete_blocked_returns_every_blocker" "tests/api/test_admin_delete.py::TestAdminHardDelete::test_a_rule_reference_blocks_tier1_hard_delete" -q`
Expected: FAIL. With no rules registered there are no blockers or warnings: the cascade delete returns 204 and the Tier-1 delete returns 204.

- [x] **Step 3: Add the attachment rules**

Create `backend/src/cellar/infrastructure/cascade/rules_attachment.py`:

```python
"""Cascade rules for file attachments.

``attachments`` points at its owner polymorphically (attachable_type,
attachable_id) with no FK. Rows go with a force-deleted owner. The stored
files stay: each row's audit snapshot keeps its storage_key.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import ColumnElement, Table, and_

from cellar.domain.attachment.enums import AttachableType
from cellar.domain.shared.cascade.actions import CascadeAction as A
from cellar.infrastructure.cascade.registry import register_rules
from cellar.infrastructure.cascade.rules import CascadeRule, Match, any_id


def _owned_by(kind: AttachableType) -> Match:
    def match(attachments: Table, owner_ids: Sequence[uuid.UUID]) -> ColumnElement[bool]:
        return and_(
            attachments.c.attachable_type == kind.value,
            any_id(attachments.c.attachable_id, owner_ids),
        )

    return match


def _attachments_of(kind: AttachableType, parent_table: str) -> CascadeRule:
    return CascadeRule(
        child_table="attachments",
        parent_table=parent_table,
        action=A.CASCADE,
        match=_owned_by(kind),
        covers=("attachments.attachable_id",),
        label_field="file_name",
        display_label="Attachments (files stay in storage)",
    )


register_rules(
    _attachments_of(AttachableType.PROTOCOL, "protocols"),
    _attachments_of(AttachableType.RUN, "runs"),
    _attachments_of(AttachableType.MOLECULE, "molecules"),
    _attachments_of(AttachableType.BATCH, "batches"),
)
```

In `backend/src/cellar/infrastructure/di/_attachment.py`, make the first lines of `register_attachment` match the other contexts:

```python
def register_attachment(container: Container) -> None:
    # Force cascade rules to register at DI bootstrap.
    import cellar.infrastructure.cascade.rules_attachment  # noqa: F401

```

Add `"cellar.infrastructure.cascade.rules_attachment",` to `_CASCADE_MODULES` in both `backend/tests/integration/cascade/conftest.py` and `backend/tests/unit/cascade/test_fk_coverage.py`.

- [x] **Step 4: Add the campaign rules**

In `backend/src/cellar/infrastructure/cascade/rules_research_organization.py`:
- Append to the module docstring: `Campaign rules (spec 2026-09-15) reference screening data by id without an FK; they are expressed as match predicates.`
- Replace the import block with:

```python
from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import ColumnElement, Table, and_, cast, column, exists, func, literal, or_, select
from sqlalchemy.dialects.postgresql import JSONB, JSONPATH

from cellar.domain.research_organization.enums import CampaignStatus
from cellar.domain.shared.cascade.actions import CascadeAction as A
from cellar.infrastructure.cascade.registry import register_rules
from cellar.infrastructure.cascade.rules import CascadeRule, Match, any_id, any_id_text, uuid_array
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CampaignChannelModel,
    CampaignMeasurementModel,
    CampaignResultModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    ReadoutDefinitionModel,
)


def _campaigns_with_a_channel_on(
    campaign: Table, protocol_ids: Sequence[uuid.UUID]
) -> ColumnElement[bool]:
    """A channel names the protocol, or one of the protocol's readout definitions."""
    channels = CampaignChannelModel.__table__
    readouts = ReadoutDefinitionModel.__table__
    return exists().where(
        channels.c.campaign_id == campaign.c.id,
        or_(
            any_id(channels.c.protocol_id, protocol_ids),
            channels.c.readout_definition_id.in_(
                select(readouts.c.id).where(any_id(readouts.c.protocol_id, protocol_ids))
            ),
        ),
    )


def _campaigns_citing_runs(*, draft: bool) -> Match:
    """A seed run, or a cell's source or contributing run, is one of the runs."""

    def match(campaign: Table, run_ids: Sequence[uuid.UUID]) -> ColumnElement[bool]:
        results = CampaignResultModel.__table__
        cells = CampaignMeasurementModel.__table__
        # lax: a non-array value yields no rows instead of an error.
        seeds = (
            func.jsonb_path_query(campaign.c.seed_runs, cast("lax $[*]", JSONPATH))
            .table_valued(column("value", JSONB))
            .render_derived(name="seed")
        )
        seeded = exists(
            select(literal(1))
            .select_from(seeds)
            .where(any_id_text(seeds.c.value["run_id"].astext, run_ids))
        )
        sourced = exists().where(
            results.c.campaign_id == campaign.c.id,
            cells.c.result_id == results.c.id,
            or_(
                any_id(cells.c.source_run_id, run_ids),
                cells.c.contributing_run_ids.overlap(uuid_array(run_ids)),
            ),
        )
        is_draft = campaign.c.status == CampaignStatus.DRAFT.value
        return and_(is_draft if draft else ~is_draft, or_(seeded, sourced))

    return match


def _campaigns_with_a_row_for(
    campaign: Table, molecule_ids: Sequence[uuid.UUID]
) -> ColumnElement[bool]:
    results = CampaignResultModel.__table__
    return exists().where(
        results.c.campaign_id == campaign.c.id,
        any_id(results.c.molecule_id, molecule_ids),
    )


_RUN_CITATIONS = (
    "campaign.seed_runs",
    "campaign_measurement.source_run_id",
    "campaign_measurement.contributing_run_ids",
)
```

Append these rules inside the existing `register_rules(...)` call, after the saved-search rule:

```python
    # -------------------------------------------------------------------------
    # Campaigns citing force-deleted screening data (ids without an FK)
    # -------------------------------------------------------------------------
    # A channel names its protocol and readout by id. Block in every state: a
    # draft's user can delete the channel; a closed campaign must be reopened.
    CascadeRule(
        child_table="campaign",
        parent_table="protocols",
        action=A.BLOCK,
        match=_campaigns_with_a_channel_on,
        covers=("campaign_channel.protocol_id", "campaign_channel.readout_definition_id"),
        label_field="name",
        display_label="Campaigns with a channel on this protocol",
    ),
    # Closed and superseded campaigns are frozen results. Their row-lock
    # triggers would also reject any change inside the delete.
    CascadeRule(
        child_table="campaign",
        parent_table="runs",
        action=A.BLOCK,
        match=_campaigns_citing_runs(draft=False),
        covers=_RUN_CITATIONS,
        label_field="name",
        display_label="Closed or superseded campaigns citing this run",
    ),
    # A draft re-resolves without the run on its next refresh, and no operation
    # removes a seed run, so warn rather than block. Never prune: dropping a
    # protocol's last seed run would widen its channels to every run.
    CascadeRule(
        child_table="campaign",
        parent_table="runs",
        action=A.WARN,
        match=_campaigns_citing_runs(draft=True),
        covers=_RUN_CITATIONS,
        label_field="name",
        display_label=(
            "Draft campaigns using this run "
            "(their cells re-resolve without it on the next refresh)"
        ),
    ),
    # A result row is the molecule. Block in every state: a draft's user can
    # remove the row; a closed campaign must be reopened.
    CascadeRule(
        child_table="campaign",
        parent_table="molecules",
        action=A.BLOCK,
        match=_campaigns_with_a_row_for,
        covers=("campaign_result.molecule_id",),
        label_field="name",
        display_label="Campaigns with a row for this molecule",
    ),
```

- [x] **Step 5: Add the import-template and compound-flag rules**

Append inside `register_rules(...)` in `backend/src/cellar/infrastructure/cascade/rules_inventory.py`:

```python
    # -------------------------------------------------------------------------
    # Plate import template default protocol (no FK)
    # -------------------------------------------------------------------------
    # ImportTemplateModel.default_protocol_id. The template's readout mappings
    # belong to that protocol, so refuse rather than leave a template that
    # imports into nothing. The user deletes the template.
    CascadeRule(
        child_table="import_templates",
        parent_table="protocols",
        action=A.BLOCK,
        fk_column="default_protocol_id",
        label_field="name",
        display_label="Plate import templates defaulting to this protocol",
    ),
```

Append inside `register_rules(...)` in `backend/src/cellar/infrastructure/cascade/rules_screening_assay.py`:

```python
    # -------------------------------------------------------------------------
    # Compound flags (no FK)
    # -------------------------------------------------------------------------
    # CompoundFlagModel.protocol_id: a user's flag on a compound in a protocol,
    # meaningless once the protocol is gone.
    CascadeRule(
        child_table="compound_flags",
        parent_table="protocols",
        action=A.CASCADE,
        fk_column="protocol_id",
        display_label="Compound flags",
    ),
```

- [x] **Step 6: Run the tests to verify they pass**

Run:
```bash
cd backend && uv run pytest tests/unit/cascade/ tests/unit/infrastructure/cascade/ -q
DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/cascade/ tests/api/test_admin_delete.py tests/integration/test_protocol_find_usages.py -q
```
Expected: PASS.

- [x] **Step 7: Lint and commit**

```bash
cd backend && uv run ruff check src/cellar/infrastructure tests/integration/cascade tests/unit/cascade tests/api/test_admin_delete.py && uv run ruff format src/cellar/infrastructure/cascade src/cellar/infrastructure/di/_attachment.py tests/integration/cascade tests/unit/cascade tests/api/test_admin_delete.py && uv run lint-imports
cd .. && git add backend/src/cellar/infrastructure/cascade/rules_attachment.py backend/src/cellar/infrastructure/di/_attachment.py backend/src/cellar/infrastructure/cascade/rules_research_organization.py backend/src/cellar/infrastructure/cascade/rules_inventory.py backend/src/cellar/infrastructure/cascade/rules_screening_assay.py backend/tests/integration/cascade/conftest.py backend/tests/unit/cascade/test_fk_coverage.py backend/tests/integration/cascade/test_rules_protocols_runs.py backend/tests/api/test_admin_delete.py
git commit -m "feat(admin): force delete refuses on campaigns and import templates, removes flags and attachments

Protocols and runs: campaign channels, closed campaigns' seed and source runs
and plate import template defaults block. Draft campaigns warn. Compound flags
and attachment rows go with the protocol or run.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -- backend/src/cellar/infrastructure/cascade/rules_attachment.py backend/src/cellar/infrastructure/di/_attachment.py backend/src/cellar/infrastructure/cascade/rules_research_organization.py backend/src/cellar/infrastructure/cascade/rules_inventory.py backend/src/cellar/infrastructure/cascade/rules_screening_assay.py backend/tests/integration/cascade/conftest.py backend/tests/unit/cascade/test_fk_coverage.py backend/tests/integration/cascade/test_rules_protocols_runs.py backend/tests/api/test_admin_delete.py
```

---

### Task 5: Rules for what references molecules and their batches

**Files:**
- Modify: `backend/src/cellar/infrastructure/cascade/rules_screening_assay.py` (M1, M7, B1)
- Modify: `backend/src/cellar/infrastructure/cascade/rules_inventory.py` (M3–M6, B2, B4)
- Modify: `backend/src/cellar/infrastructure/cascade/rules_chemical_registration.py` (M8, M10, M11, B5, DR1, and recursion into disclosure requests)
- Create: `backend/tests/integration/cascade/test_rules_molecules_batches.py`

M2 (campaign rows) and M9/B3 (attachments) were registered in Task 4; this task tests them.

**Interfaces:**
- Consumes: Tasks 1, 2 and 4 (the `_rows` builders, runner, `CascadeBlockedError`, and the M2/M9/B3 rules).
- Produces: registered rules with these exact display labels:
  - "Runs with data for this molecule"
  - "Runs with data for this molecule's batches"
  - "Open synthesis requests (cancel or fulfil them first)"
  - "Finished synthesis requests"
  - "Open sample requests (cancel them first)"
  - "Finished sample requests"
  - "Inventory plates holding these batches"
  - "Sample requests (preferred batch cleared)"
  - "Compound flags"
  - "Merged registrations (tombstones)"
  - "Reaction steps (product link cleared)"
  - "Reaction steps (batch link cleared)"
  - "CDD sync records (a later CDD sync may re-import this molecule)"
  - "Merge events (disclosure link cleared)"

- [x] **Step 1: Write the failing tests**

Create `backend/tests/integration/cascade/test_rules_molecules_batches.py`:

```python
"""Force-delete rules for what references molecules and their batches without an FK."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from cellar.domain.audit_compliance.enums import AuditAction
from cellar.infrastructure.cascade.cascade_runner import CascadePlan, CascadeRunner
from tests.integration.cascade import _rows


def _labels(plan: CascadePlan) -> dict:
    return {r.display_label: [s["label"] for s in r.samples] for r in plan.blockers}


async def _plan(session: AsyncSession, ws: uuid.UUID, molecule: uuid.UUID) -> CascadePlan:
    return await CascadeRunner(session).plan(
        parent_table="molecules", parent_id=molecule, workspace_id=ws
    )


async def _registered(session: AsyncSession, ws: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """A molecule with one batch."""
    org = await _rows.org(session, ws)
    molecule = await _rows.molecule(session, ws, org)
    return molecule, await _rows.batch(session, ws, molecule)


async def _assay(session: AsyncSession, ws: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """A protocol, its readout definition, and one run."""
    protocol = await _rows.protocol(session, ws)
    readout = await _rows.readout_definition(session, protocol)
    return protocol, readout, await _rows.run(session, ws, protocol)


async def test_readout_rows_for_the_molecule_block(db_session: AsyncSession) -> None:
    ws = uuid.uuid4()
    molecule, _batch = await _registered(db_session, ws)
    _protocol, readout, run = await _assay(db_session, ws)
    await _rows.readout_data(db_session, ws, run, readout, molecule_id=molecule)

    assert _labels(await _plan(db_session, ws, molecule)) == {
        "Runs with data for this molecule": ["2026-09-15"]
    }


async def test_a_curve_blocks_through_the_molecule_and_its_batch(db_session: AsyncSession) -> None:
    ws = uuid.uuid4()
    molecule, batch = await _registered(db_session, ws)
    protocol, readout, run = await _assay(db_session, ws)
    await _rows.curve(
        db_session,
        ws,
        run_id=run,
        protocol_id=protocol,
        readout_definition_id=readout,
        molecule_id=molecule,
        batch_id=batch,
    )

    assert set(_labels(await _plan(db_session, ws, molecule))) == {
        "Runs with data for this molecule",
        "Runs with data for this molecule's batches",
    }


async def test_a_well_holding_its_batch_blocks(db_session: AsyncSession) -> None:
    ws = uuid.uuid4()
    molecule, batch = await _registered(db_session, ws)
    _protocol, _readout, run = await _assay(db_session, ws)
    await _rows.wells(db_session, await _rows.plate(db_session, run), 1, batch_id=batch)

    assert _labels(await _plan(db_session, ws, molecule)) == {
        "Runs with data for this molecule's batches": ["2026-09-15"]
    }


async def test_a_campaign_row_for_the_molecule_blocks(db_session: AsyncSession) -> None:
    ws = uuid.uuid4()
    molecule, _batch = await _registered(db_session, ws)
    campaign = await _rows.campaign(db_session, ws, name="Hit follow-up")
    await _rows.result(db_session, campaign, molecule)

    assert _labels(await _plan(db_session, ws, molecule)) == {
        "Campaigns with a row for this molecule": ["Hit follow-up"]
    }


@pytest.mark.parametrize(
    ("table", "open_status", "finished_status"),
    [("sample_requests", "approved", "fulfilled"), ("synthesis_requests", "in_progress", "failed")],
)
async def test_open_requests_block_and_finished_ones_go_with_the_molecule(
    db_session: AsyncSession, table: str, open_status: str, finished_status: str
) -> None:
    ws = uuid.uuid4()
    molecule, _batch = await _registered(db_session, ws)
    add = _rows.sample_request if table == "sample_requests" else _rows.synthesis_request
    open_request = await add(db_session, ws, molecule, status=open_status)
    finished_request = await add(db_session, ws, molecule, status=finished_status)
    runner = CascadeRunner(db_session)

    [blocker] = (await runner.plan(parent_table="molecules", parent_id=molecule, workspace_id=ws)).blockers
    assert (blocker.table, blocker.count, blocker.samples[0]["id"]) == (table, 1, str(open_request))

    await db_session.execute(
        sa.text(f"UPDATE {table} SET status = :status WHERE id = :id"),
        {"status": finished_status, "id": open_request},
    )
    await runner.execute(parent_table="molecules", parent_id=molecule, workspace_id=ws)
    assert not await _rows.exists(db_session, table, open_request)
    assert not await _rows.exists(db_session, table, finished_request)


async def test_a_plate_well_map_holding_its_batch_blocks(db_session: AsyncSession) -> None:
    ws = uuid.uuid4()
    molecule, batch = await _registered(db_session, ws)
    await _rows.registered_plate(
        db_session, ws, barcode="PL-0001", well_map={"A1": {"batch_id": str(batch)}}
    )
    # A JSON null well map, like every legacy tracker plate, must not break the query.
    await _rows.registered_plate(db_session, ws, barcode="PL-0002", well_map=None)

    assert _labels(await _plan(db_session, ws, molecule)) == {
        "Inventory plates holding these batches": ["PL-0001"]
    }


async def test_tombstones_sync_rows_flags_and_files_go_with_the_molecule(
    db_session: AsyncSession,
) -> None:
    ws = uuid.uuid4()
    org = await _rows.org(db_session, ws)
    molecule = await _rows.molecule(db_session, ws, org, reg="CC-000001")
    tombstone = await _rows.molecule(db_session, ws, org, reg="CC-000002", merged_into_id=molecule)
    batch = await _rows.batch(db_session, ws, molecule)
    sync = await _rows.cdd_sync(db_session, ws, molecule)
    flag = await _rows.compound_flag(db_session, ws, protocol_id=uuid.uuid4(), molecule_id=molecule)
    molecule_file = await _rows.attachment(db_session, ws, "molecule", molecule)
    batch_file = await _rows.attachment(db_session, ws, "batch", batch)

    entries = await CascadeRunner(db_session).execute(
        parent_table="molecules", parent_id=molecule, workspace_id=ws
    )

    assert {molecule, tombstone, batch, sync, flag, molecule_file, batch_file} <= {
        e.entity_id for e in entries
    }
    for table, row in (
        ("molecules", tombstone),
        ("cdd_molecule_sync", sync),
        ("attachments", batch_file),
    ):
        assert not await _rows.exists(db_session, table, row)


async def test_links_from_records_that_stay_are_cleared_and_audited(
    db_session: AsyncSession,
) -> None:
    ws = uuid.uuid4()
    org = await _rows.org(db_session, ws)
    molecule = await _rows.molecule(db_session, ws, org, reg="CC-000001")
    batch = await _rows.batch(db_session, ws, molecule)
    other = await _rows.molecule(db_session, ws, org, reg="CC-000009")
    step = await _rows.reaction_step(
        db_session,
        await _rows.synthesis_route(db_session, ws, other),
        product_molecule_id=molecule,
        batch_id=batch,
    )
    request = await _rows.sample_request(db_session, ws, other, status="fulfilled", batch_id=batch)
    merge = await _rows.merge_event(
        db_session,
        ws,
        source_molecule_id=other,
        target_molecule_id=await _rows.molecule(db_session, ws, org, reg="CC-000010"),
        disclosure_request_id=await _rows.disclosure_request(db_session, ws, molecule),
    )

    entries = await CascadeRunner(db_session).execute(
        parent_table="molecules", parent_id=molecule, workspace_id=ws
    )

    assert {(e.entity_id, e.field_name) for e in entries if e.action == AuditAction.UPDATE} == {
        (step, "product_molecule_id"),
        (step, "batch_id"),
        (request, "batch_id"),
        (merge, "disclosure_request_id"),
    }
    row = (
        await db_session.execute(
            sa.text("SELECT product_molecule_id, batch_id FROM reaction_steps WHERE id = :id"),
            {"id": step},
        )
    ).one()
    assert tuple(row) == (None, None)
```

- [x] **Step 2: Run them to verify they fail**

Run: `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/cascade/test_rules_molecules_batches.py -q`
Expected: FAIL. Only `test_a_campaign_row_for_the_molecule_blocks` passes, because Task 4 registered M2. The rest fail: either there are no blockers, or the delete raises `IntegrityError` on `cdd_molecule_sync` / `merge_events.disclosure_request_id`.

- [x] **Step 3: Add the screening rules**

In `backend/src/cellar/infrastructure/cascade/rules_screening_assay.py`:
- In the module docstring, replace `Rules are derived from the actual ForeignKey declarations in` with `Rules cover FK references (see`, ending that sentence with `) and id-only references without an FK (compound flags, and measurements naming a molecule or batch).`
- Replace the import block with:

```python
from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import ColumnElement, Table, exists, or_

from cellar.domain.shared.cascade.actions import CascadeAction as A
from cellar.infrastructure.cascade.registry import register_rules
from cellar.infrastructure.cascade.rules import CascadeRule, any_id
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    DoseResponseCurveModel,
    PlateModel,
    ReadoutDataModel,
    WellModel,
)


def _runs_with_data_for_molecules(
    runs: Table, molecule_ids: Sequence[uuid.UUID]
) -> ColumnElement[bool]:
    readouts = ReadoutDataModel.__table__
    curves = DoseResponseCurveModel.__table__
    return or_(
        exists().where(readouts.c.run_id == runs.c.id, any_id(readouts.c.molecule_id, molecule_ids)),
        exists().where(curves.c.run_id == runs.c.id, any_id(curves.c.molecule_id, molecule_ids)),
    )


def _runs_with_data_for_batches(runs: Table, batch_ids: Sequence[uuid.UUID]) -> ColumnElement[bool]:
    readouts = ReadoutDataModel.__table__
    curves = DoseResponseCurveModel.__table__
    plates = PlateModel.__table__
    wells = WellModel.__table__
    return or_(
        exists().where(readouts.c.run_id == runs.c.id, any_id(readouts.c.batch_id, batch_ids)),
        exists().where(curves.c.run_id == runs.c.id, any_id(curves.c.batch_id, batch_ids)),
        exists().where(
            plates.c.run_id == runs.c.id,
            wells.c.plate_id == plates.c.id,
            any_id(wells.c.batch_id, batch_ids),
        ),
    )
```

Append inside `register_rules(...)`, after the compound-flag rule from Task 4:

```python
    # CompoundFlagModel.molecule_id (no FK): the flag means nothing without its compound.
    CascadeRule(
        child_table="compound_flags",
        parent_table="molecules",
        action=A.CASCADE,
        fk_column="molecule_id",
        display_label="Compound flags",
    ),
    # -------------------------------------------------------------------------
    # Runs holding measurements for a force-deleted molecule or batch (no FK)
    # -------------------------------------------------------------------------
    # readout_data.molecule_id and dose_response_curves.molecule_id. Deleting a
    # compound must not pull data out of runs, and a refit would re-create its
    # curves anyway. Merge the molecule, or force-delete the runs first.
    CascadeRule(
        child_table="runs",
        parent_table="molecules",
        action=A.BLOCK,
        match=_runs_with_data_for_molecules,
        covers=("readout_data.molecule_id", "dose_response_curves.molecule_id"),
        label_field="run_date",
        display_label="Runs with data for this molecule",
    ),
    # Wells store only the batch, so a deleted batch leaves a plate map with no
    # compound identity at all.
    CascadeRule(
        child_table="runs",
        parent_table="batches",
        action=A.BLOCK,
        match=_runs_with_data_for_batches,
        covers=("wells.batch_id", "readout_data.batch_id", "dose_response_curves.batch_id"),
        label_field="run_date",
        display_label="Runs with data for this molecule's batches",
    ),
```

- [x] **Step 4: Add the inventory rules**

In `backend/src/cellar/infrastructure/cascade/rules_inventory.py`:
- Delete the docstring line `- sample_requests.molecule_id: plain UUID, no FK constraint; no cascade rule.`
- Replace the import block with:

```python
from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import ColumnElement, Table, and_, cast, column, exists, func, literal, select
from sqlalchemy.dialects.postgresql import JSONB, JSONPATH

from cellar.domain.inventory.enums import SampleRequestStatus, SynthesisRequestStatus
from cellar.domain.shared.cascade.actions import CascadeAction as A
from cellar.infrastructure.cascade.registry import register_rules
from cellar.infrastructure.cascade.rules import CascadeRule, Match, any_id, any_id_text

_SYNTHESIS_FINISHED = (
    SynthesisRequestStatus.FULFILLED,
    SynthesisRequestStatus.REJECTED,
    SynthesisRequestStatus.CANCELLED,
    SynthesisRequestStatus.FAILED,
)
_SAMPLE_FINISHED = (
    SampleRequestStatus.FULFILLED,
    SampleRequestStatus.REJECTED,
    SampleRequestStatus.CANCELLED,
)


def _requests_for(finished_statuses: Sequence[str], *, finished: bool) -> Match:
    """Requests for the molecules, in (or, for open ones, not in) a finished status.

    "Not finished" is the fail-safe reading: a status added later counts as open.
    """
    values = [str(s) for s in finished_statuses]

    def match(requests: Table, molecule_ids: Sequence[uuid.UUID]) -> ColumnElement[bool]:
        in_state = requests.c.status.in_(values) if finished else requests.c.status.not_in(values)
        return and_(any_id(requests.c.molecule_id, molecule_ids), in_state)

    return match


def _plates_holding_batches(plates: Table, batch_ids: Sequence[uuid.UUID]) -> ColumnElement[bool]:
    """well_map is {"A1": {"batch_id": "<uuid>", ...}}, or JSON null on legacy plates.

    lax: a null or non-object map yields no rows instead of an error.
    """
    wells = (
        func.jsonb_path_query(plates.c.well_map, cast("lax $.*", JSONPATH))
        .table_valued(column("value", JSONB))
        .render_derived(name="well")
    )
    return exists(
        select(literal(1))
        .select_from(wells)
        .where(any_id_text(wells.c.value["batch_id"].astext, batch_ids))
    )
```

Append inside `register_rules(...)`:

```python
    # -------------------------------------------------------------------------
    # Requests for a force-deleted molecule (molecule_id, no FK)
    # -------------------------------------------------------------------------
    # Open requests are live work: refuse, as merge does. Finished ones mean
    # nothing without the compound: remove them.
    CascadeRule(
        child_table="synthesis_requests",
        parent_table="molecules",
        action=A.BLOCK,
        match=_requests_for(_SYNTHESIS_FINISHED, finished=False),
        covers=("synthesis_requests.molecule_id",),
        label_field="purpose",
        display_label="Open synthesis requests (cancel or fulfil them first)",
    ),
    CascadeRule(
        child_table="synthesis_requests",
        parent_table="molecules",
        action=A.CASCADE,
        match=_requests_for(_SYNTHESIS_FINISHED, finished=True),
        covers=("synthesis_requests.molecule_id",),
        label_field="purpose",
        display_label="Finished synthesis requests",
    ),
    CascadeRule(
        child_table="sample_requests",
        parent_table="molecules",
        action=A.BLOCK,
        match=_requests_for(_SAMPLE_FINISHED, finished=False),
        covers=("sample_requests.molecule_id",),
        label_field="purpose",
        display_label="Open sample requests (cancel them first)",
    ),
    CascadeRule(
        child_table="sample_requests",
        parent_table="molecules",
        action=A.CASCADE,
        match=_requests_for(_SAMPLE_FINISHED, finished=True),
        covers=("sample_requests.molecule_id",),
        label_field="purpose",
        display_label="Finished sample requests",
    ),
    # -------------------------------------------------------------------------
    # Batch references without an FK
    # -------------------------------------------------------------------------
    # A physical plate still holds the compound. Removing its batch would also
    # fail every later well edit with "Batch not found".
    CascadeRule(
        child_table="registered_plates",
        parent_table="batches",
        action=A.BLOCK,
        match=_plates_holding_batches,
        covers=("registered_plates.well_map",),
        label_field="barcode",
        display_label="Inventory plates holding these batches",
    ),
    # SampleRequestModel.batch_id: an optional preferred batch.
    CascadeRule(
        child_table="sample_requests",
        parent_table="batches",
        action=A.SET_NULL,
        fk_column="batch_id",
        label_field="purpose",
        display_label="Sample requests (preferred batch cleared)",
    ),
```

- [x] **Step 5: Add the chemical-registration rules**

In `backend/src/cellar/infrastructure/cascade/rules_chemical_registration.py`:
1. Delete the docstring lines `- compound_flags.molecule_id: plain UUID, no FK constraint; rule removed.` and `- bulk_registration_items.molecule_id: plain UUID, no FK constraint; rule removed.`
2. Add `recurse_into_entity="disclosure_request",` to the existing `disclosure_requests` / `molecule_id` CASCADE rule, so its merge-event rule gets walked.
3. Append inside `register_rules(...)`:

```python
    # -------------------------------------------------------------------------
    # References without a handled FK
    # -------------------------------------------------------------------------
    # MoleculeModel.merged_into_id (no FK): tombstones merged into this molecule
    # are invisible aliases of it, so they go too, walked as molecules.
    CascadeRule(
        child_table="molecules",
        parent_table="molecules",
        action=A.CASCADE,
        fk_column="merged_into_id",
        label_field="registration_number",
        display_label="Merged registrations (tombstones)",
        recurse_into_entity="molecule",
    ),
    # ReactionStepModel.product_molecule_id / .batch_id (no FK): a step on
    # another molecule's route that made or used this compound keeps its step.
    CascadeRule(
        child_table="reaction_steps",
        parent_table="molecules",
        action=A.SET_NULL,
        fk_column="product_molecule_id",
        display_label="Reaction steps (product link cleared)",
    ),
    CascadeRule(
        child_table="reaction_steps",
        parent_table="batches",
        action=A.SET_NULL,
        fk_column="batch_id",
        display_label="Reaction steps (batch link cleared)",
    ),
    # CddMoleculeSyncModel.molecule_id → molecules (FK, no ondelete). The CDD vault
    # stays the source: dropping the ledger row lets a later sync re-import the
    # molecule. Without this rule the delete fails on the FK.
    CascadeRule(
        child_table="cdd_molecule_sync",
        parent_table="molecules",
        action=A.CASCADE,
        fk_column="molecule_id",
        display_label="CDD sync records (a later CDD sync may re-import this molecule)",
    ),
    # MergeEventModel.disclosure_request_id → disclosure_requests (FK, nullable, no
    # ondelete): another molecule's merge event keeps its record, minus the link.
    CascadeRule(
        child_table="merge_events",
        parent_table="disclosure_requests",
        action=A.SET_NULL,
        fk_column="disclosure_request_id",
        display_label="Merge events (disclosure link cleared)",
    ),
```

- [x] **Step 6: Run the tests to verify they pass**

Run:
```bash
cd backend && uv run pytest tests/unit/cascade/ tests/unit/infrastructure/cascade/ tests/unit/domain/shared/cascade/ -q
DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/cascade/ tests/api/test_admin_delete.py -q
```
Expected: PASS.

- [x] **Step 7: Lint and commit**

```bash
cd backend && uv run ruff check src/cellar/infrastructure/cascade tests/integration/cascade && uv run ruff format src/cellar/infrastructure/cascade tests/integration/cascade && uv run lint-imports
cd .. && git add backend/src/cellar/infrastructure/cascade/rules_screening_assay.py backend/src/cellar/infrastructure/cascade/rules_inventory.py backend/src/cellar/infrastructure/cascade/rules_chemical_registration.py backend/tests/integration/cascade/test_rules_molecules_batches.py
git commit -m "feat(admin): molecule force delete refuses while its data or open work remains

Screening data, open requests and plate well maps naming the molecule or its
batches block the delete. Merged tombstones, finished requests and CDD sync
rows go with it; the sync rows used to fail the delete on their FK. Reaction
steps and preferred batches lose the link, and so does another molecule's merge
event pointing at a deleted disclosure request.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -- backend/src/cellar/infrastructure/cascade/rules_screening_assay.py backend/src/cellar/infrastructure/cascade/rules_inventory.py backend/src/cellar/infrastructure/cascade/rules_chemical_registration.py backend/tests/integration/cascade/test_rules_molecules_batches.py
```

---

### Task 6: Guard tests keep every reference accounted for

**Files:**
- Modify: `backend/tests/unit/cascade/test_fk_coverage.py`

**Interfaces:**
- Consumes: `CascadeRule.references` / `.fk_column` (Task 1), every rule registered in Tasks 4–5, `TIER2_ENTITY_TYPES`, `table_for_entity_type`.
- Produces: three new tests.
  - `test_every_id_only_reference_is_classified`
  - `test_every_fk_into_a_force_deleted_table_is_handled`
  - `test_classification_names_real_columns`

- [x] **Step 1: Load every model, and load rules through one helper**

At the top of `backend/tests/unit/cascade/test_fk_coverage.py`, replace everything from `import importlib` through the `from cellar.infrastructure.cascade.registry import …` line with the block below. That span holds the explicit `import cellar.infrastructure.persistence.sqlalchemy.…` model imports and the existing `Base` and registry imports.

```python
import importlib
import pkgutil
import sys
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import ARRAY, JSON, Uuid

import cellar.infrastructure.persistence.sqlalchemy as _persistence
from cellar.application.admin.tier2_entities import TIER2_ENTITY_TYPES
from cellar.domain.shared.cascade.actions import CascadeAction
from cellar.infrastructure.cascade.label_fields import table_for_entity_type
from cellar.infrastructure.cascade.registry import (
    _clear_for_test as _clear_cascade_registry,
    all_rules,
    get_rules_for_parent,
)
from cellar.infrastructure.persistence.sqlalchemy.base import Base

# Import every persistence module so Base.metadata holds every table. A hand-kept
# list lets a new model's columns escape the checks below.
for _module in pkgutil.walk_packages(_persistence.__path__, _persistence.__name__ + "."):
    importlib.import_module(_module.name)
```

After `_CASCADE_MODULES`, add:

```python
@contextmanager
def _rules_loaded() -> Iterator[None]:
    """Register every rule module fresh; afterwards evict them and clear the registry.

    Eviction lets later tests that import a rule module get a fresh
    registration instead of a cached no-op.
    """
    _clear_cascade_registry()
    for name in _CASCADE_MODULES:
        sys.modules.pop(name, None)
    for name in _CASCADE_MODULES:
        importlib.import_module(name)
    try:
        yield
    finally:
        _clear_cascade_registry()
        for name in _CASCADE_MODULES:
            sys.modules.pop(name, None)
```

Rewrite the top of `test_every_fk_is_categorized` to use it. Its steps 1–3 (evict, import, collect, evict) become:

```python
def test_every_fk_is_categorized():
    with _rules_loaded():
        all_fks = _collect_all_fks()
        tier2_keys = _collect_tier2_rule_keys()
```

The rest of the function (the `uncovered` / `unsafe_self_refs` loop and its asserts) stays unchanged, dedented out of the `with`.

- [x] **Step 2: Remove stale and now-covered `IGNORED_FKS` entries**

Delete these entries together with their comment blocks:
- `("batches", "storage_location_id", "storage_locations")` and its "Batches → storage_locations" comment block, because `batches` has no such column. The `samples.location_id` and `registered_plates.storage_location_id` entries stay.
- `("registered_plates", "run_id", "runs")` and its comment block, because the column doesn't exist.
- `("protocols", "target_id", "targets")` and its comment block, because `protocols` now links targets through `protocol_targets`.
- `("cdd_molecule_syncs", "molecule_id", "molecules")` and its comment block. It's misspelled, and rule M11 covers the FK now.
- `("merge_events", "disclosure_request_id", "disclosure_requests")` and its comment block. Rule DR1 covers it, and the comment's claim that the nullable FK won't block was wrong: the FK is NO ACTION.

- [x] **Step 3: Add the classification table and the new tests**

Append to the end of `backend/tests/unit/cascade/test_fk_coverage.py`:

```python
# ---------------------------------------------------------------------------
# Id-only references: every uuid column without an FK, and every JSON column,
# says what a force delete does to it: a rule covers it, or it is listed here
# with the reason dangling is acceptable.
# ---------------------------------------------------------------------------

_NOT_REFERENCES = {"id", "workspace_id", "created_by", "updated_by"}

_USER = "Duar user id, not a Cellar row"
_ORG = "organization id; organizations are never force-deleted"
_AUDIT = "append-only audit trail; it must outlive what it describes"
_NO_IDS = "JSON holding no Cellar ids (values, settings, labels)"
_BY_NAME = "JSON naming definitions by name, not id"
_SNAPSHOT = "snapshot carrying its own labels"
_HISTORY = "record of what happened; the id stays as provenance"
_NEVER_WRITTEN = "never written"
_MEMBERSHIP_CACHE = "cache keyed on membership; misses and recomputes once members change"
_SAR_PROJECTION = "SAR projection cache; its staleness is docs/backlog/sar-activity-projection-cache-no-data-version.md"
_FILTER = "a filter on a missing id matches nothing; pruning it would widen results"
_TIER1_ONLY = "parent is Tier-1 only; see docs/backlog/tier1-only-parents-id-references.md"

LEFT_ALONE: dict[str, str] = {
    "attachments.uploaded_by": _USER,
    "audit_operations.user_id": _USER,
    "batch_identifiers.registered_by": _USER,
    "batch_tags.assigned_by": _USER,
    "batches.chemist": _USER,
    "bulk_disclosures.submitted_by": _USER,
    "bulk_registrations.submitted_by": _USER,
    "campaign.closed_by": _USER,
    "campaign_stage_override.overridden_by": _USER,
    "campaign_tags.assigned_by": _USER,
    "cdd_molecule_imports.submitted_by": _USER,
    "cdd_plate_imports.submitted_by": _USER,
    "collection_tags.assigned_by": _USER,
    "compound_flags.flagged_by": _USER,
    "disclosure_requests.requested_by": _USER,
    "electronic_signatures.user_id": _USER,
    "export_jobs.requested_by": _USER,
    "favorites.user_id": _USER,
    "merge_events.merged_by": _USER,
    "molecule_identifiers.registered_by": _USER,
    "molecule_tags.assigned_by": _USER,
    "molecules.disclosed_by": _USER,
    "plate_comments.author_id": _USER,
    "plate_loans.approved_by": _USER,
    "plate_loans.requested_by": _USER,
    "project_members.user_id": _USER,
    "project_tags.assigned_by": _USER,
    "projects.archived_by": _USER,
    "protocol_tags.assigned_by": _USER,
    "protocols.locked_by": _USER,
    "registered_plate_tags.assigned_by": _USER,
    "registered_plates.registered_by": _USER,
    "rgroup_decomposition_runs.requested_by": _USER,
    "run_tags.assigned_by": _USER,
    "runs.hit_criteria_set_by": _USER,
    "runs.locked_by": _USER,
    "runs.operator": _USER,
    "sample_requests.assigned_to": _USER,
    "sample_requests.requester_id": _USER,
    "sar_activity_projections.requested_by": _USER,
    "scaffold_tree_jobs.requested_by": _USER,
    "shipments.sender_id": _USER,
    "synthesis_requests.approved_by": _USER,
    "synthesis_requests.assigned_to": _USER,
    "synthesis_requests.requester_id": _USER,
    "umap_jobs.requested_by": _USER,
    "user_preferences.user_id": _USER,
    "batches.supplier_org_id": _ORG,
    "bulk_disclosures.partner_org_id": _ORG,
    "disclosure_requests.disclosing_org_id": _ORG,
    "kiosk_devices.org_id": _ORG,
    "org_plate_policies.org_id": _ORG,
    "plate_groups.owner_org_id": _ORG,
    "plate_loans.borrower_org_id": _ORG,
    "plate_loans.owner_org_id": _ORG,
    "registered_plates.owner_org_id": _ORG,
    "runs.performed_at_org_id": _ORG,
    "shipments.destination_org_id": _ORG,
    "synthesis_requests.assigned_org_id": _ORG,
    "audit_entries.entity_id": _AUDIT,
    "audit_operations.entity_id": _AUDIT,
    "batches.custom_fields": _NO_IDS,
    "campaign_channel.intercept_key": _NO_IDS,
    "campaign_channel.qc_filter": _NO_IDS,
    "cdd_molecule_imports.filter_criteria": _NO_IDS,
    "collection_import_templates.column_mapping": _NO_IDS,
    "condition_definitions.pick_list_values": _NO_IDS,
    "custom_field_definitions.default_value": _NO_IDS,
    "custom_field_definitions.pick_list_values": _NO_IDS,
    "data_sources.config": _NO_IDS,
    "data_sources.entity_mappings": _NO_IDS,
    "dose_response_curves.excluded_points": _NO_IDS,
    "dose_response_curves.fit_quality_warnings": _NO_IDS,
    "dose_response_curves.intercept_values": _NO_IDS,
    "dose_response_curves.raw_data": _NO_IDS,
    "molecules.custom_fields": _NO_IDS,
    "ontology_slot_definitions.ontology_sources": _NO_IDS,
    "plate_templates.template_map": _NO_IDS,
    "plates.plate_map": _NO_IDS,
    "protocol_forms.condition_templates": _NO_IDS,
    "protocol_forms.ontology_defaults": _NO_IDS,
    "protocol_forms.readout_templates": _NO_IDS,
    "protocols.fingerprint": _NO_IDS,
    "reaction_steps.condition_additional": _NO_IDS,
    "readout_definitions.pick_list_values": _NO_IDS,
    "rgroup_assignments.rgroups": _NO_IDS,
    "rgroup_decomposition_runs.rgroup_labels": _NO_IDS,
    "umap_jobs.picker_params": _NO_IDS,
    "user_preferences.preferences": _NO_IDS,
    "workspace_settings.audit_reason_policy": _NO_IDS,
    "workspace_settings.custom_field_definitions": _NO_IDS,
    "workspace_settings.formulation_number_scheme": _NO_IDS,
    "workspace_settings.registration_rules": _NO_IDS,
    "dose_response_curves.dose_response_config_snapshot": _BY_NAME,
    "protocols.ontology_annotations": _BY_NAME,
    "protocols.recommended_hit_criteria": _BY_NAME,
    "readout_definitions.dose_response_config": _BY_NAME,
    "readout_definitions.normalizations": _BY_NAME,
    "run_import_templates.column_mapping": _BY_NAME,
    "runs.conditions": _BY_NAME,
    "runs.hit_criteria": _BY_NAME,
    "campaign.source_protocols": _SNAPSHOT,
    "campaign_measurement.curve_snapshot": _SNAPSHOT,
    "campaign_result.added_from": _SNAPSHOT,
    "merge_events.snapshot": _SNAPSHOT,
    "bulk_registration_items.batch_id": _HISTORY,
    "bulk_registration_items.molecule_id": _HISTORY,
    "sample_requests.fulfilled_sample_id": _HISTORY,
    "shipment_items.item_id": _HISTORY,
    "synthesis_requests.fulfilled_batch_id": _HISTORY,
    "batches.synthesis_request_id": _NEVER_WRITTEN,
    "batches.synthesis_route_id": _NEVER_WRITTEN,
    "batches.synthesis_step_id": _NEVER_WRITTEN,
    "campaign_result.representative_batch_id": _NEVER_WRITTEN,
    "plates.parent_plate_id": _NEVER_WRITTEN,
    "plates.template_id": _NEVER_WRITTEN,
    "synthesis_requests.bulk_request_id": _NEVER_WRITTEN,
    "rgroup_assignments.molecule_id": _MEMBERSHIP_CACHE,
    "scaffold_tree_jobs.result_json": _MEMBERSHIP_CACHE,
    "umap_jobs.result_json": _MEMBERSHIP_CACHE,
    "sar_activity_projections.channel_spec": _SAR_PROJECTION,
    "sar_activity_values.molecule_id": _SAR_PROJECTION,
    "sar_activity_values.snapshot": _SAR_PROJECTION,
    "export_jobs.query_snapshot": _FILTER,
    "saved_searches.columns": _FILTER,
    "saved_searches.query": _FILTER,
    "campaign.project_id": _TIER1_ONLY,
    "collection_import_templates.used_in_collections": _TIER1_ONLY,
    "favorites.entity_id": _TIER1_ONLY,
    "protocols.control_layouts": _TIER1_ONLY,
    "registered_plates.project_id": _TIER1_ONLY,
    "registered_plates.template_id": _TIER1_ONLY,
    "registration_forms.field_overrides": _TIER1_ONLY,
    "synthesis_requests.parent_request_id": _TIER1_ONLY,
    "synthesis_requests.project_id": _TIER1_ONLY,
    "campaign.superseded_by_campaign_id": "campaigns can't be deleted",
    "campaign.supersedes_campaign_id": "campaigns can't be deleted",
    "campaign_measurement.source_curve_id": "provenance that every refit already replaces; the cell keeps curve_snapshot",
    "campaign_measurement.source_readout_id": "provenance that every recompute already replaces; the cell keeps its value",
    "campaign_stage.criteria": "channel ids inside the same campaign",
    "cdd_plate_sync.plate_id": "inventory plates aren't force-deleted; see docs/backlog/non-admin-deletes-leave-id-references.md",
    "collections.derived_from_campaign_id": "campaigns can't be deleted",
    "import_templates.column_mappings": "readout ids of the template's default protocol, whose delete that template blocks",
    "plate_comments.target_id": "inventory plates, groups and loans aren't force-deleted; see docs/backlog/non-admin-deletes-leave-id-references.md",
    "plate_loan_items.plate_id": "loan history outlives the plate by design",
    "reaction_steps.eln_entry_id": "ELN entries don't exist yet",
    "reaction_steps.preceding_step_ids": "step ids inside one route, deleted with it",
    "reaction_steps.reagents": "not rendered; unchecked reagent ids are docs/backlog/writers-accept-unchecked-ids.md",
    "readout_data.well_id": "always deleted together with its wells",
    "runs.eln_entry_id": "ELN entries don't exist yet",
    "runs.qc_metrics": "keyed by the run's own plates, deleted with it",
    "synthesis_requests.proposed_route_id": "a route for the request's own molecule, whose requests block or go first",
}


def _id_bearing_columns() -> Iterator[str]:
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if col.name in _NOT_REFERENCES or col.foreign_keys:
                continue
            kind = col.type
            holds_ids = (
                isinstance(kind, Uuid)
                or (isinstance(kind, ARRAY) and isinstance(kind.item_type, Uuid))
                or isinstance(kind, JSON)
            )
            if holds_ids:
                yield f"{table.name}.{col.name}"


def test_every_id_only_reference_is_classified():
    with _rules_loaded():
        covered = {ref for rule in all_rules() for ref in rule.references}
    unclassified = sorted(
        c for c in _id_bearing_columns() if c not in covered and c not in LEFT_ALONE
    )
    assert not unclassified, (
        "These columns can hold another row's id with no FK. Say what a force "
        "delete does to them:\n"
        + "\n".join(f"  {c}" for c in unclassified)
        + "\n\nResolution: cover the column with a CascadeRule (fk_column, or match "
        "plus covers), or add it to LEFT_ALONE with the reason dangling is acceptable."
    )


_FORCE_DELETE_ROOTS = sorted(table_for_entity_type(et) for et in TIER2_ENTITY_TYPES)


def _force_delete_reach(root: str) -> tuple[set[str], set[str]]:
    """Tables a force delete of ``root`` removes rows from, and the tables whose rules it walks."""
    removed, walked, stack = {root}, {root}, [root]
    while stack:
        for rule in get_rules_for_parent(stack.pop()):
            if rule.action != CascadeAction.CASCADE:
                continue
            removed.add(rule.child_table)
            if rule.recurse_into_entity and rule.child_table not in walked:
                walked.add(rule.child_table)
                stack.append(rule.child_table)
    return removed, walked


def test_every_fk_into_a_force_deleted_table_is_handled():
    problems: list[str] = []
    with _rules_loaded():
        for root in _FORCE_DELETE_ROOTS:
            removed, walked = _force_delete_reach(root)
            handled = {
                (r.child_table, r.fk_column, r.parent_table)
                for table in walked
                for r in get_rules_for_parent(table)
                if r.fk_column is not None
            }
            for child, col, parent in sorted(_collect_all_fks()):
                if (
                    parent in removed
                    and (child, col, parent) not in handled
                    and not _has_db_ondelete_handling(child, col)
                ):
                    problems.append(f"  {root}: {child}.{col} -> {parent}")
    assert not problems, (
        "A force delete removes rows these FKs point at, and nothing clears or "
        "removes the referencing rows first, so the delete fails on the constraint:\n"
        + "\n".join(problems)
        + "\n\nResolution: add a CascadeRule on the parent (and recurse into that parent "
        "if a rule deletes it), or give the FK an ondelete of CASCADE or SET NULL."
    )


def test_classification_names_real_columns():
    columns = {f"{t.name}.{c.name}" for t in Base.metadata.tables.values() for c in t.columns}
    named = {*LEFT_ALONE, *(f"{child}.{col}" for child, col, _ in IGNORED_FKS)}
    stale = sorted(named - columns)
    assert not stale, "Entries naming columns that don't exist:\n" + "\n".join(
        f"  {s}" for s in stale
    )
```

- [x] **Step 4: Run the guard tests**

Run: `cd backend && uv run pytest tests/unit/cascade/test_fk_coverage.py -q`
Expected: 4 passed.

The classification table was generated against the models at `13eb5c17` and cross-checked against the rules from Tasks 4–5. If a column is reported, it's a column added since then: classify it, don't loosen the test.

Check that the guard actually bites: temporarily comment out the M11 rule in `rules_chemical_registration.py`, run the file, and confirm `test_every_fk_into_a_force_deleted_table_is_handled` fails naming `molecules: cdd_molecule_sync.molecule_id -> molecules`. Then restore the rule.

- [x] **Step 5: Run the whole unit suite**

Run: `cd backend && uv run pytest tests/unit -q`
Expected: PASS. Rule-registry tests are sensitive to import order, and `_rules_loaded` restores the evict-after behaviour they rely on.

- [x] **Step 6: Lint and commit**

```bash
cd backend && uv run ruff check tests/unit/cascade/test_fk_coverage.py && uv run ruff format tests/unit/cascade/test_fk_coverage.py
cd .. && git add backend/tests/unit/cascade/test_fk_coverage.py
git commit -m "test(admin): guard that every id reference says what a force delete does to it

Every uuid column without an FK and every JSON column is either covered by a
cascade rule or listed with a reason. Every FK into a table a force delete
removes needs a rule or an ondelete. Stale entries fail too, which caught
four IGNORED_FKS entries for columns that no longer exist.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -- backend/tests/unit/cascade/test_fk_coverage.py
```

---

### Task 7: The force-delete dialog shows blockers and warnings and stops a blocked delete

**Files:**
- Regenerate: `frontend/src/shared/lib/api/model/` and `frontend/src/shared/lib/api/admin/admin.ts` (orval)
- Create: `frontend/src/shared/components/delete-blocker-list.tsx`
- Modify: `frontend/src/shared/components/admin-delete-button.tsx` (use the shared list)
- Modify: `frontend/src/shared/components/cascade-delete-dialog.tsx`
- Modify: `frontend/src/shared/hooks/use-cascade-preview.ts`
- Modify: `frontend/src/shared/hooks/use-cascade-delete.ts`
- Create: `frontend/src/shared/components/cascade-delete-dialog.test.tsx`
- Modify: `frontend/src/shared/hooks/use-cascade-delete.test.tsx`

**Interfaces:**
- Consumes: `POST /api/v1/admin/{entity_type}/{entity_id}/cascade-preview` → `CascadePreviewResponse` (Task 2), whose `blockers` and `warnings` are `BlockerPayload[]` with `display_label: string | null`; the 409 body from a blocked `DELETE …/cascade`; `getDeleteBlockedError` (existing, `use-admin-delete.ts`).
- Produces: `DeleteBlockerList({ items }: { items: BlockerPayload[] })`.

- [x] **Step 1: Regenerate the API types**

The dev backend must be up on `:8000` and reloaded with Tasks 2–5; it runs from this checkout with `--reload`. Check `curl -s localhost:8000/version`. If it isn't running, start it with the repo's `make` target, so the root `.env` exports the Sentinel service key.

```bash
cd frontend && pnpm generate:api
# orval rewrites every file's OpenAPI version stamp. Keep only real changes:
for f in $(git diff --name-only -- src/shared/lib/api); do
  if [ -z "$(git diff -U0 -- "$f" | grep '^[+-]' | grep -v '^[+-][+-]' | grep -vi 'version')" ]; then
    git checkout -- "$f"
  fi
done
git status --short -- src/shared/lib/api
```
Expected, roughly:
- modified `model/blockerPayload.ts` (`display_label`), `model/index.ts` and `admin/admin.ts` (preview returns `CascadePreviewResponse`);
- new `model/cascadePreviewResponse.ts`, plus its generated samples/children item types if orval emits them.

- [x] **Step 2: Write the failing tests**

Create `frontend/src/shared/components/cascade-delete-dialog.test.tsx`:

```tsx
import { ApiError } from "@/shared/lib/api/custom-instance";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const refetch = vi.fn();
const mutateAsync = vi.fn();
let previewData: unknown;

vi.mock("@/shared/hooks/use-cascade-preview", () => ({
  useCascadePreview: () => ({
    data: previewData,
    isLoading: false,
    isSuccess: true,
    isError: false,
    refetch,
  }),
}));
vi.mock("@/shared/hooks/use-cascade-delete", () => ({
  useCascadeDelete: () => ({ mutateAsync, isPending: false }),
}));

import { CascadeDeleteDialog } from "./cascade-delete-dialog";

const root = {
  entity_type: "run",
  table: "runs",
  display_label: "run",
  count: 1,
  samples: [],
  truncated: false,
  action: "cascade",
  children: [],
};
const closedCampaign = {
  table: "campaign",
  entity_type: "campaign",
  fk_column: "campaign.seed_runs",
  count: 1,
  samples: [{ id: "c-1", label: "Kinase panel" }],
  truncated: false,
  display_label: "Closed or superseded campaigns citing this run",
};

function confirmWith(name: string) {
  fireEvent.change(screen.getByLabelText(/to confirm/i), { target: { value: name } });
  fireEvent.change(screen.getByPlaceholderText(/reason for deletion/i), {
    target: { value: "botched import" },
  });
}

function renderDialog() {
  render(
    <CascadeDeleteDialog
      entityType="run"
      entityId="r-1"
      entityLabel="Run 2026-09-15"
      open
      onOpenChange={vi.fn()}
    />,
  );
}

describe("CascadeDeleteDialog", () => {
  beforeEach(() => {
    refetch.mockReset();
    mutateAsync.mockReset();
  });

  it("lists blockers and keeps Force delete disabled while any exist", () => {
    previewData = { ...root, blockers: [closedCampaign], warnings: [] };
    renderDialog();
    confirmWith("Run 2026-09-15");

    expect(screen.getByText(/closed or superseded campaigns citing this run/i)).toBeInTheDocument();
    expect(screen.getByText(/kinase panel/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Force delete" })).toBeDisabled();
  });

  it("lists warnings without blocking the delete", () => {
    previewData = {
      ...root,
      blockers: [],
      warnings: [{ ...closedCampaign, display_label: "Draft campaigns using this run" }],
    };
    renderDialog();
    confirmWith("Run 2026-09-15");

    expect(screen.getByText(/draft campaigns using this run/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Force delete" })).toBeEnabled();
  });

  it("shows the blockers a refused delete returns and refreshes the preview", async () => {
    previewData = { ...root, blockers: [], warnings: [] };
    mutateAsync.mockRejectedValue(
      new ApiError("API error: 409", 409, {
        error: "delete_blocked_by_dependencies",
        blockers: [closedCampaign],
      }),
    );
    renderDialog();
    confirmWith("Run 2026-09-15");

    fireEvent.click(screen.getByRole("button", { name: "Force delete" }));

    expect(await screen.findByText(/kinase panel/i)).toBeInTheDocument();
    expect(refetch).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Force delete" })).toBeDisabled();
  });
});
```

Append to the `describe("useCascadeDelete")` block in `frontend/src/shared/hooks/use-cascade-delete.test.tsx`:

```tsx
  it("stays silent on a blocked delete; the dialog lists the blockers", async () => {
    mockCascade.mockRejectedValue(
      new ApiError("API error: 409", 409, {
        error: "delete_blocked_by_dependencies",
        blockers: [],
      }),
    );
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useCascadeDelete(), { wrapper });

    result.current.mutate({
      entityType: "run",
      entityId: "r-1",
      typedName: "Run 2026-09-15",
      reason: "botched import",
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(mockShowError).not.toHaveBeenCalled();
  });
```

- [x] **Step 3: Run them to verify they fail**

Run: `cd frontend && pnpm exec vitest run src/shared/components/cascade-delete-dialog.test.tsx src/shared/hooks/use-cascade-delete.test.tsx`
Expected: FAIL. No blocker text is rendered, the button is enabled, and a toast fires on the blocked delete.

- [x] **Step 4: Add the shared blocker list**

Create `frontend/src/shared/components/delete-blocker-list.tsx`:

```tsx
import type { BlockerPayload } from "@/shared/lib/api/model";

function sampleText(sample: Record<string, unknown>): string {
  return (sample.label as string | null | undefined) ?? (sample.id as string);
}

/** Groups of rows that stop a delete (or that it will change): one line per group. */
export function DeleteBlockerList({ items }: { items: BlockerPayload[] }) {
  return (
    <ul className="list-disc pl-5">
      {items.map((b) => (
        <li key={`${b.table}:${b.fk_column}:${b.display_label ?? ""}`}>
          {b.display_label ? (
            <>
              {b.display_label} ({b.count})
            </>
          ) : (
            <>
              {b.count} {b.entity_type}
              {b.count !== 1 ? "s" : ""}
            </>
          )}
          {b.samples.length > 0 && (
            <span className="text-muted-foreground">
              :{" "}
              {b.samples.map((s) => sampleText(s as Record<string, unknown>)).join(", ")}
              {b.truncated ? ", …" : ""}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}
```

In `frontend/src/shared/components/admin-delete-button.tsx`, import `DeleteBlockerList` from `@/shared/components/delete-blocker-list`. Replace the whole `<ul className="list-disc pl-5">…</ul>` inside the `blockers ?` branch with:

```tsx
            <DeleteBlockerList items={blockers} />
```

- [x] **Step 5: Update the hooks**

`frontend/src/shared/hooks/use-cascade-preview.ts`:

```ts
"use client";

import { cascadePreviewApiV1AdminEntityTypeEntityIdCascadePreviewPost as cascadePreview } from "@/shared/lib/api/admin/admin";
import type { CascadePreviewResponse } from "@/shared/lib/api/model";
import { useQuery } from "@tanstack/react-query";

export function useCascadePreview(entityType: string, entityId: string, enabled = true) {
  return useQuery<CascadePreviewResponse>({
    queryKey: ["cascade-preview", entityType, entityId],
    queryFn: () => cascadePreview(entityType, entityId),
    enabled,
  });
}
```

In `frontend/src/shared/hooks/use-cascade-delete.ts`:
- Add `import { getDeleteBlockedError } from "@/shared/hooks/use-admin-delete";`.
- Change `onError` to:

```ts
    onError: (err: unknown) => {
      // The dialog lists the blockers of a refused delete; a toast would only repeat them.
      if (getDeleteBlockedError(err)) return;
      showError(err instanceof Error ? err.message : "Failed");
    },
```

- [x] **Step 6: Update the dialog**

Replace `frontend/src/shared/components/cascade-delete-dialog.tsx`:

```tsx
"use client";

import { DeleteBlockerList } from "@/shared/components/delete-blocker-list";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/shared/components/ui/alert-dialog";
import { Button, buttonVariants } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Textarea } from "@/shared/components/ui/textarea";
import { getDeleteBlockedError } from "@/shared/hooks/use-admin-delete";
import { useCascadeDelete } from "@/shared/hooks/use-cascade-delete";
import { useCascadePreview } from "@/shared/hooks/use-cascade-preview";
import type { BlockerPayload, CascadeNodeResponse } from "@/shared/lib/api/model";
import { AlertTriangle } from "lucide-react";
import { useState } from "react";

export interface CascadeDeleteDialogProps {
  entityType: string;
  entityId: string;
  entityLabel: string;
  onDeleted?: () => void;
  /** Controlled open state. When provided, the built-in red trigger button is
   *  NOT rendered — drive the dialog from your own control (e.g. a menu item).
   *  Omit both for the default self-triggering button behavior. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

function NodeView({
  node,
  depth = 0,
}: {
  node: CascadeNodeResponse;
  depth?: number;
}) {
  const indent = depth * 16;
  const actionColor = node.action === "set_null" ? "text-amber-600" : "";

  const sampleLabels = node.samples
    .map((s) => (s as Record<string, unknown>).label)
    .filter((l): l is string => typeof l === "string" && l.length > 0);

  return (
    <div style={{ paddingLeft: indent }} className="text-sm">
      <span className={actionColor}>
        [{node.action}] {node.display_label}: {node.count}
      </span>
      {sampleLabels.length > 0 && (
        <span className="text-muted-foreground ml-2 text-xs">
          ({sampleLabels.join(", ")}
          {node.truncated ? ", …" : ""})
        </span>
      )}
      {(node.children ?? []).map((c, i) => (
        <NodeView key={`${c.table}-${i}`} node={c} depth={depth + 1} />
      ))}
    </div>
  );
}

export function CascadeDeleteDialog({
  entityType,
  entityId,
  entityLabel,
  onDeleted,
  open: controlledOpen,
  onOpenChange,
}: CascadeDeleteDialogProps) {
  const [internalOpen, setInternalOpen] = useState(false);
  const isControlled = controlledOpen !== undefined;
  const open = isControlled ? controlledOpen : internalOpen;
  const [typed, setTyped] = useState("");
  const [reason, setReason] = useState("");
  // Blockers returned by a delete that a new reference beat after the preview.
  const [refused, setRefused] = useState<BlockerPayload[] | null>(null);
  const setOpen = (next: boolean) => {
    if (!isControlled) setInternalOpen(next);
    if (!next) setRefused(null);
    onOpenChange?.(next);
  };

  const preview = useCascadePreview(entityType, entityId, open);
  const m = useCascadeDelete({
    onSuccess: () => {
      setOpen(false);
      onDeleted?.();
    },
  });

  const blockers = refused ?? preview.data?.blockers ?? [];
  const warnings = preview.data?.warnings ?? [];
  const canSubmit =
    preview.isSuccess &&
    blockers.length === 0 &&
    typed === entityLabel &&
    reason.trim().length > 0;

  async function onConfirm() {
    setRefused(null);
    try {
      await m.mutateAsync({ entityType, entityId, typedName: typed, reason });
    } catch (err: unknown) {
      const blocked = getDeleteBlockedError(err);
      if (blocked) {
        setRefused(blocked.blockers);
        void preview.refetch();
      }
    }
  }

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      {!isControlled && (
        <AlertDialogTrigger asChild>
          <Button variant="destructive" size="sm">
            <AlertTriangle className="mr-1 h-4 w-4" />
            Force delete (cascade)
          </Button>
        </AlertDialogTrigger>
      )}
      <AlertDialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <AlertDialogHeader>
          <AlertDialogTitle>
            Force delete {entityType}: {entityLabel}
          </AlertDialogTitle>
          <AlertDialogDescription>
            Hard delete. All dependent rows will be removed or unlinked as shown. This cannot be
            undone.
          </AlertDialogDescription>
        </AlertDialogHeader>

        {preview.isLoading && <p>Computing impact…</p>}
        {preview.isError && (
          <p className="text-sm text-destructive">
            Couldn't compute what this delete affects. Close the dialog and try again.
          </p>
        )}

        {blockers.length > 0 && (
          <div className="space-y-1 text-sm">
            <p className="font-semibold text-destructive">
              Can't force delete while these still use it:
            </p>
            <DeleteBlockerList items={blockers} />
            <p className="text-muted-foreground text-xs">
              Resolve them first, then open this dialog again.
            </p>
          </div>
        )}

        {warnings.length > 0 && (
          <div className="space-y-1 text-sm">
            <p className="font-medium">Also affected, not blocking:</p>
            <DeleteBlockerList items={warnings} />
          </div>
        )}

        {preview.data && <NodeView node={preview.data} />}

        <div className="space-y-2 pt-2">
          <label htmlFor="cascade-delete-typed-name" className="text-sm font-medium">
            Type <code className="bg-muted px-1 rounded">{entityLabel}</code> to confirm:
          </label>
          <Input
            id="cascade-delete-typed-name"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
          />
          <Textarea
            id="cascade-delete-reason"
            placeholder="Reason for deletion (required)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={500}
          />
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            className={buttonVariants({ variant: "destructive" })}
            disabled={!canSubmit || m.isPending}
            onClick={(e) => {
              e.preventDefault();
              void onConfirm();
            }}
          >
            {m.isPending ? "Deleting…" : "Force delete"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
```

- [x] **Step 7: Run the frontend checks**

Run:
```bash
cd frontend && pnpm exec vitest run src/shared/components/cascade-delete-dialog.test.tsx src/shared/hooks/use-cascade-delete.test.tsx src/shared/hooks/use-admin-delete.test.tsx
pnpm exec tsc --noEmit
pnpm lint; echo "lint exit=$?"
```
Expected: tests PASS, `tsc` prints nothing, and `lint exit=0`. If biome reports formatting, run `pnpm exec biome check --write <the touched files>` on those paths only, never `--unsafe`, then re-run.

- [x] **Step 8: Commit**

```bash
cd .. && git add frontend/src/shared/components/delete-blocker-list.tsx frontend/src/shared/components/admin-delete-button.tsx frontend/src/shared/components/cascade-delete-dialog.tsx frontend/src/shared/components/cascade-delete-dialog.test.tsx frontend/src/shared/hooks/use-cascade-preview.ts frontend/src/shared/hooks/use-cascade-delete.ts frontend/src/shared/hooks/use-cascade-delete.test.tsx frontend/src/shared/lib/api
git commit -m "feat(admin): force-delete dialog lists what blocks or changes, and won't submit a blocked delete

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -- frontend/src/shared/components/delete-blocker-list.tsx frontend/src/shared/components/admin-delete-button.tsx frontend/src/shared/components/cascade-delete-dialog.tsx frontend/src/shared/components/cascade-delete-dialog.test.tsx frontend/src/shared/hooks/use-cascade-preview.ts frontend/src/shared/hooks/use-cascade-delete.ts frontend/src/shared/hooks/use-cascade-delete.test.tsx frontend/src/shared/lib/api
```

Check `git show --stat HEAD` lists only real API type changes under `src/shared/lib/api`, with no version-stamp-only files.

---

### Task 8: Verify the branch, review it once, and open the PR

**Files:**
- Modify: `docs/backlog/admin-force-delete-protocol-dangling-refs.md` (status line)
- Modify: `docs/superpowers/plans/2026-09-15-force-delete-id-references.md` (tick the boxes)

- [x] **Step 1: Run the full suites**

```bash
cd backend && uv run ruff check src/ && uv run ruff format --check src/ && uv run lint-imports
uv run pytest tests/unit -q
DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration -q
DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api/test_admin_delete.py -q
cd ../frontend && pnpm test && pnpm exec tsc --noEmit && pnpm lint; echo "lint exit=$?"
```
Expected: everything passes. Compare any failure against `docs/backlog/pre-existing-test-failures.md` and `docs/backlog/preexisting-test-lint-failures-main.md`. Failures already on `main` get noted in the PR, not fixed here. Anything new is this branch's problem.

- [x] **Step 2: Check it in the running app**

The dev stack is on `:8000`/`:3000`. Using the `verify` skill's recipe:
1. On a protocol with a campaign channel in the dev workspace, open **Admin → Force delete (cascade)…**. The dialog lists "Campaigns with a channel on this protocol" and **Force delete** stays disabled after typing the name and reason.
2. On a run seeding only draft campaigns, the warning shows and the button enables. Close without deleting.

Don't delete real dev data to test this.

- [x] **Step 3: One whole-branch review**

Use superpowers:requesting-code-review for the whole branch against `main` (`git diff main...HEAD`), with the spec as the requirement. Fix what it finds with focused tests, then re-run Step 1 for the touched area.

- [x] **Step 4: Mark the handoff done and push**

In `docs/backlog/admin-force-delete-protocol-dangling-refs.md`, replace the status paragraph with:

```markdown
**Status:** implemented on `feat/force-delete-id-references` (2026-09-15). Design:
`docs/superpowers/specs/2026-09-15-force-delete-id-references-design.md`; plan:
`docs/superpowers/plans/2026-09-15-force-delete-id-references.md`. The handoff below is kept for context.
```

```bash
cd .. && git add -f docs/backlog/admin-force-delete-protocol-dangling-refs.md docs/superpowers/plans/2026-09-15-force-delete-id-references.md docs/superpowers/specs/2026-09-15-force-delete-id-references-design.md
git commit -m "docs(admin): force-delete id references implemented; plan and spec updates

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -- docs/backlog/admin-force-delete-protocol-dangling-refs.md docs/superpowers/plans/2026-09-15-force-delete-id-references.md docs/superpowers/specs/2026-09-15-force-delete-id-references-design.md
git push -u origin feat/force-delete-id-references
```

- [x] **Step 5: Open the PR**

Use the `panda-sas` gh account (`gh auth switch --user panda-sas` if another account is active). The body covers:
- what force delete now does per reference (the spec §4 tables, summarised);
- the bugs fixed on the way: CDD-synced molecules 409, preview missing blockers, unaudited set-null, the asyncpg bind cap, and the stale `IGNORED_FKS` entries;
- test evidence from Step 1;
- that daikon is unaffected (admin endpoints only) and no migration is needed;
- the parked backlog files.

End the body with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`. Never add a Claude-Session line.

```bash
gh pr create --base main --head feat/force-delete-id-references --title "feat(admin): force delete accounts for references without an FK" --body-file <body file written to the scratchpad>
```
