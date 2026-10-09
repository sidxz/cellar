# Protocol Create Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A chemist creates a protocol by picking a category first and answering only what that category needs; Type, assay format and starter readouts come from forms tied to categories; siblings get their discriminators in the same save; units are stored one way.

**Architecture:** Protocol Forms gain `category_id` and `assay_format_from_target`; the create command carries the `form_id` it started from so the backend (sole owner of the target-type → BAO mapping) fills the assay format. Units are canonicalized by rule in the domain value constructors every writer already goes through. The create dialog is split into small components around pure, tested form-apply helpers.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2 async, Alembic, dry-python/returns, pytest; Next.js 16, React 19, TanStack Query, react-hook-form + zod, shadcn/ui, vitest, orval.

**Spec:** `docs/superpowers/specs/2026-10-08-protocol-create-flow-design.md`

**Branch:** create `feat/protocol-create-flow` from `feat/protocol-auto-naming` (which is unmerged and carries the naming work this builds on).

## Global Constraints

- Generated names never contain `·`, an em dash or an en dash; units may contain `·` (they are not names).
- Every route or DTO change regenerates orval in the same task: from `frontend/`, backend up on :8000, `pnpm generate:api`; then revert files whose only change is the `OpenAPI spec version` line (`git diff --stat`, `git checkout -- <file>` for those). orval never prunes `model/index.ts`.
- Never hand-roll a TypeScript interface that mirrors a backend DTO; alias the generated type.
- DDD layers: domain imports nothing from application/infrastructure/interface. New use cases get DI (`infrastructure/di/_*.py`), a `…Dep` (`interface/dependencies/_*.py`, added to `__all__`), and a route.
- Commits: `git commit -m "…" -- <paths>` (explicit paths; never sweep in `.gitignore`, `Makefile`, `frontend/next-env.d.ts`, `frontend/AGENTS.md`), message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; no Claude-Session trailer.
- Backend tests: `cd backend && uv run pytest <path> -q -p no:warnings`. Integration/API tests need `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock`. Known pre-existing failure: `tests/unit/application/export/renderers/test_pdf_renderer.py::test_pdf_renders_a_small_report` (missing system libs).
- Frontend: `cd frontend && pnpm exec vitest run <path>`; `pnpm lint` (check exit code), `pnpm exec tsc --noEmit -p .`. Use `biome check --write` only (never `--unsafe`).
- BAO assay-format term ids (verified in BioPortal): biochemical format `BAO_0000217`, organism-based format `BAO_0000218`, cell based format `BAO_0000219`, protein complex format `BAO_0000223`, protein format `BAO_0000224`, nucleic acid format `BAO_0000225`, tissue-based format `BAO_0000221`, microsome format `BAO_0000251`, single protein format `BAO_0000357`, cell-free format `BAO_0000366`, small-molecule physicochemical format `BAO_0000100`, plasma format `BAO_0020003`. Term id = `http://www.bioassayontology.org/bao#<code>`, `ontology_source` = `"BAO"`.

## Review Focus

1. A workspace that already has two or more `is_default` forms (never enforced before): the migration keeps the most recently updated one and does not fail on the new unique index. Test in Task 4.
2. Editing a shipped dose-response form in Admin → Protocol Forms must keep its `dose_response_config`, pick lists and formulas (today the admin page drops fields it does not show). Test in Task 14.
3. Deleting a category whose form is the default while a generic default form exists: no unique-index violation; the forms become generic, non-default. Test in Task 4.
4. Unit text that is not a spelling variant stays exactly as typed: `U/mL`, `% remaining`, `10-6 cm/s`, `mm` (millimetre) vs `mM`, `log10 CFU`. Test in Task 1.
5. A sibling that was published or locked between preview and save: the create fails with the sibling named and nothing is saved. Test in Task 8.

---

### Task 1: Unit spelling rules in the domain

**Files:**
- Create: `backend/src/cellar/domain/shared/units.py`
- Modify: `backend/src/cellar/domain/screening_assay/protocol.py` (ReadoutDefinition `self.unit = unit` ~line 258, ConditionDefinition `self.unit = unit` ~line 308)
- Modify: `backend/src/cellar/domain/workspace_config/protocol_form.py` (`ProtocolFormReadout`, `ProtocolFormCondition`)
- Test: `backend/tests/unit/domain/shared/test_units.py`

**Interfaces:**
- Produces: `canonical_unit(text: str | None) -> str | None`; `UnitSuggestion(unit: str, group: str)`; `COMMON_UNITS: tuple[UnitSuggestion, ...]`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/domain/shared/test_units.py
"""Units are stored one way: spelling variants of the same unit collapse; nothing else changes."""

import uuid

import pytest

from cellar.domain.screening_assay.enums import ConditionDataType, ReadoutDataType
from cellar.domain.screening_assay.protocol import ConditionDefinition, ReadoutDefinition
from cellar.domain.shared.units import COMMON_UNITS, canonical_unit
from cellar.domain.workspace_config.protocol_form import (
    ProtocolFormCondition,
    ProtocolFormReadout,
)

MICRO = "µ"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("uM", f"{MICRO}M"),
        ("μM", f"{MICRO}M"),  # Greek mu
        ("mcg/mL", f"{MICRO}g/mL"),
        ("ug/ml", f"{MICRO}g/mL"),
        ("uL/min/mg", f"{MICRO}L/min/mg"),
        ("ml", "mL"),
        ("dl", "dL"),
        ("umol/L", f"{MICRO}M"),
        ("nmol/L", "nM"),
        ("mol/L", "M"),
        ("mg/Kg", "mg/kg"),
        ("hr", "h"),
        ("Hours", "h"),
        ("mins", "min"),
        ("seconds", "s"),
        ("days", "d"),
        ("percent", "%"),
        ("deg C", "°C"),
        ("ng*h/mL", "ng·h/mL"),
        ("ng.h/mL", "ng·h/mL"),
        ("  µM  ", f"{MICRO}M"),
    ],
)
def test_spelling_variants_collapse(raw, expected):
    assert canonical_unit(raw) == expected


@pytest.mark.parametrize(
    "unchanged",
    ["U/mL", "% remaining", "10-6 cm/s", "mm", "mM", "M", "mP", "log10 CFU", "RFU", "OD600",
     "mL/min/g liver", "fold", "Da", "1.5 h"],
)
def test_anything_else_is_left_as_typed(unchanged):
    assert canonical_unit(unchanged) == unchanged


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_blank_is_none(blank):
    assert canonical_unit(blank) is None


def test_every_suggestion_is_already_canonical():
    for s in COMMON_UNITS:
        assert canonical_unit(s.unit) == s.unit


def test_readout_and_condition_definitions_store_the_canonical_spelling():
    pid = uuid.uuid4()
    rd = ReadoutDefinition(protocol_id=pid, name="IC50", data_type=ReadoutDataType.NUMERIC, unit="uM")
    cd = ConditionDefinition(protocol_id=pid, name="Dose", data_type=ConditionDataType.NUMERIC, unit="mg/Kg")
    assert rd.unit == f"{MICRO}M" and cd.unit == "mg/kg"


def test_form_templates_store_the_canonical_spelling():
    assert ProtocolFormReadout(name="MIC", data_type="numeric", unit="ug/ml").unit == f"{MICRO}g/mL"
    assert ProtocolFormCondition(name="Time", data_type="numeric", unit="hrs").unit == "h"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/domain/shared/test_units.py -q -p no:warnings`
Expected: FAIL with `ModuleNotFoundError: No module named 'cellar.domain.shared.units'`.

- [ ] **Step 3: Implement the rules**

```python
# backend/src/cellar/domain/shared/units.py
"""Units on readouts, conditions and form templates: one spelling per unit, by rule.

``canonical_unit`` rewrites spelling variants of the same unit (uM, μM, umol/L → µM) and
leaves everything else exactly as typed, so any unit normalizes consistently without a list
and nothing ever converts between different units.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MICRO = "µ"  # micro sign: the canonical spelling
_MICRO_PREFIXED = re.compile(r"^(?:u|μ|µ|mc)(mol|M|g|L|l|m|s)$")
_LITRE = re.compile(r"^([pnµmdck]?)l$")
_WORDS = {
    "hr": "h", "hrs": "h", "hour": "h", "hours": "h",
    "mins": "min", "minute": "min", "minutes": "min",
    "sec": "s", "secs": "s", "second": "s", "seconds": "s",
    "day": "d", "days": "d",
    "percent": "%", "pct": "%",
}
_DEGREES = re.compile(r"^(?:deg\s*C|degC|°c)$", re.IGNORECASE)
# '/' and '·' separate tokens and are kept; '*' or a '.' between letters is a product sign.
_SEPARATOR = re.compile(r"(/|·|\*|(?<=[A-Za-zµ%])\.(?=[A-Za-zµ]))")
_MOLAR = re.compile(r"(?<![A-Za-z])([pnµm]?)mol/L(?![A-Za-z])")


def _token(token: str) -> str:
    t = " ".join(token.split())
    if t.lower() in _WORDS:
        return _WORDS[t.lower()]
    if _DEGREES.match(t):
        return "°C"
    if t == "Kg":
        return "kg"
    m = _MICRO_PREFIXED.match(t)
    if m:
        t = MICRO + m.group(1)
    m = _LITRE.match(t)
    if m:
        t = m.group(1) + "L"
    return t


def canonical_unit(text: str | None) -> str | None:
    if text is None or not text.strip():
        return None
    parts = _SEPARATOR.split(text.strip())
    out: list[str] = []
    for part in parts:
        if part in ("*", "."):
            out.append("·")
        elif part in ("/", "·"):
            out.append(part)
        else:
            out.append(_token(part))
    return _MOLAR.sub(lambda m: m.group(1) + "M", "".join(out))


@dataclass(frozen=True)
class UnitSuggestion:
    unit: str
    group: str


def _group(group: str, *units: str) -> tuple[UnitSuggestion, ...]:
    return tuple(UnitSuggestion(u, group) for u in units)


COMMON_UNITS: tuple[UnitSuggestion, ...] = (
    *_group("Concentration", f"{MICRO}M", "nM", "mM", "pM", "M"),
    *_group("Mass concentration", f"{MICRO}g/mL", "ng/mL", "mg/mL"),
    *_group("Dose", "mg/kg"),
    *_group("Percent and ratio", "%", "fold", "fraction"),
    *_group("Counts", "log10 CFU", "CFU/mL"),
    *_group("Time", "h", "min", "s", "d"),
    *_group("Clearance", f"{MICRO}L/min/mg", "mL/min/kg"),
    *_group("Permeability", "10-6 cm/s"),
    *_group("Exposure", "ng·h/mL"),
    *_group("Signal", "RFU", "RLU", "AU", "mP", "OD600", "counts"),
    *_group("Temperature", "°C"),
    *_group("Mass", "Da"),
)
```

Then route every stored unit through it:

```python
# backend/src/cellar/domain/screening_assay/protocol.py
# add to imports:
from cellar.domain.shared.units import canonical_unit
# ReadoutDefinition.__init__: replace `self.unit = unit` with
        self.unit = canonical_unit(unit)
# ConditionDefinition.__init__: replace `self.unit = unit` with
        self.unit = canonical_unit(unit)
```

```python
# backend/src/cellar/domain/workspace_config/protocol_form.py
# add to imports:
from cellar.domain.shared.units import canonical_unit
# inside ProtocolFormReadout and inside ProtocolFormCondition, add:
    def __post_init__(self) -> None:
        object.__setattr__(self, "unit", canonical_unit(self.unit))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/domain/shared/test_units.py tests/unit/domain -q -p no:warnings`
Expected: PASS (all domain tests still green).

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(units): one spelling per unit on readouts, conditions and form templates

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar/domain/shared/units.py backend/src/cellar/domain/screening_assay/protocol.py backend/src/cellar/domain/workspace_config/protocol_form.py backend/tests/unit/domain/shared/test_units.py
```

---

### Task 2: Unit suggestions endpoint

**Files:**
- Create: `backend/src/cellar/application/screening/list_units.py`
- Create: `backend/src/cellar/interface/routes/units.py`
- Modify: `backend/src/cellar/infrastructure/di/_screening.py` (define `ListUnits`)
- Modify: `backend/src/cellar/interface/dependencies/_screening.py` (`ListUnitsDep`, `__all__`)
- Modify: `backend/src/cellar/interface/app.py` (include router next to `protocol_forms_router`)
- Test: `backend/tests/api/test_units.py`
- Regenerate: `frontend/src/shared/lib/api/model/` (orval)

**Interfaces:**
- Consumes: `COMMON_UNITS`, `UnitSuggestion` (Task 1).
- Produces: `GET /api/v1/units` → `list[UnitSuggestionResponse{unit: str, group: str}]`; orval type `UnitSuggestionResponse`.

- [ ] **Step 1: Write the failing API test**

```python
# backend/tests/api/test_units.py
"""The unit picker's suggestions."""


async def test_lists_common_units_grouped(client):
    r = await client.get("/api/v1/units")
    assert r.status_code == 200, r.text
    body = r.json()
    assert {"unit": "µM", "group": "Concentration"} in body
    assert {"unit": "mg/kg", "group": "Dose"} in body
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api/test_units.py -q -p no:warnings`
Expected: FAIL with 404.

- [ ] **Step 3: Implement the query, DI, dependency and route**

```python
# backend/src/cellar/application/screening/list_units.py
"""Common units for the unit picker. Free text stays allowed; this is only a suggestion list."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.domain.shared.errors import DomainError
from cellar.domain.shared.units import COMMON_UNITS, UnitSuggestion


@dataclass(frozen=True, kw_only=True)
class ListUnitsQuery(Query):
    workspace_id: uuid.UUID


class ListUnits:
    async def __call__(
        self, input: ListUnitsQuery, auth: AuthContext | None = None
    ) -> Result[list[UnitSuggestion], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        return Success(list(COMMON_UNITS))
```

```python
# backend/src/cellar/infrastructure/di/_screening.py — inside the registration function:
from cellar.application.screening.list_units import ListUnits
    container.define(ListUnits, lambda c: ListUnits())
```

```python
# backend/src/cellar/interface/dependencies/_screening.py
from cellar.application.screening.list_units import ListUnits
ListUnitsDep = Annotated[ListUnits, Depends(_get_use_case(ListUnits))]
# and add "ListUnitsDep" to __all__
```

```python
# backend/src/cellar/interface/routes/units.py
"""Unit suggestions for readout and condition units."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.screening.list_units import ListUnitsQuery
from cellar.interface.dependencies import AuthDep, ListUnitsDep
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/units", tags=["units"])


class UnitSuggestionResponse(BaseModel):
    unit: str
    group: str


@router.get("", response_model=list[UnitSuggestionResponse])
async def list_units(auth: AuthDep, use_case: ListUnitsDep) -> list[UnitSuggestionResponse]:
    units = result_to_response(await use_case(ListUnitsQuery(workspace_id=auth.workspace_id), auth=auth))
    return [UnitSuggestionResponse(unit=u.unit, group=u.group) for u in units]
```

```python
# backend/src/cellar/interface/app.py — beside the protocol_forms router:
    from cellar.interface.routes.units import router as units_router
    app.include_router(units_router)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api/test_units.py -q -p no:warnings`
Expected: PASS.

- [ ] **Step 5: Regenerate orval and commit**

```bash
cd frontend && pnpm generate:api && git diff --stat   # revert version-stamp-only files; git add new generated files under frontend/src/shared/lib/api
git commit -m "feat(units): unit suggestions endpoint

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar/application/screening/list_units.py backend/src/cellar/interface/routes/units.py backend/src/cellar/infrastructure/di/_screening.py backend/src/cellar/interface/dependencies/_screening.py backend/src/cellar/interface/app.py backend/tests/api/test_units.py frontend/src/shared/lib/api
```

---

### Task 3: Rewrite stored unit spellings

**Files:**
- Create: `backend/alembic/versions/088_canonical_units.py`
- Test: `backend/tests/integration/test_canonical_units_migration.py`

**Interfaces:**
- Consumes: `canonical_unit` (Task 1). Produces: migration revision `088_canonical_units` (down_revision `087_campaign_name_snapshot_width`).

- [ ] **Step 1: Write the failing test**

The rewrite lives in one sync helper that the migration calls with `op.get_bind()` and the test calls through `run_sync`. Legacy spellings are planted with raw SQL because the domain now canonicalizes on write.

```python
# backend/tests/integration/test_canonical_units_migration.py
"""Stored unit spellings are rewritten once; anything that is not a variant stays."""

import uuid

from sqlalchemy import text

from cellar.domain.screening_assay.enums import ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from cellar.infrastructure.persistence.unit_rewrite import rewrite_stored_units


async def test_rewrites_variants_and_leaves_the_rest(session_factory, workspace_id, user_id):
    pid = uuid.uuid4()
    protocol = Protocol.create(
        workspace_id=workspace_id,
        name="p",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=user_id,
        readout_definitions=[
            ReadoutDefinition(protocol_id=pid, name=n, data_type=ReadoutDataType.NUMERIC)
            for n in ("a", "b", "c")
        ],
    )
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await SQLAlchemyProtocolRepository(uow).save(protocol)
        await uow.commit()
    async with session_factory() as s:
        for name, legacy in (("a", "uM"), ("b", "U/mL"), ("c", "ug/ml")):
            await s.execute(
                text("update readout_definitions set unit=:u where protocol_id=:p and name=:n"),
                {"u": legacy, "p": protocol.id, "n": name},
            )
        await s.run_sync(lambda sync: rewrite_stored_units(sync.connection()))
        await s.commit()
        rows = await s.execute(
            text("select name, unit from readout_definitions where protocol_id=:p"),
            {"p": protocol.id},
        )
        units = dict(rows.all())
    assert units == {"a": "\u00b5M", "b": "U/mL", "c": "\u00b5g/mL"}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/test_canonical_units_migration.py -q -p no:warnings`
Expected: FAIL with `ModuleNotFoundError: cellar.infrastructure.persistence.unit_rewrite`.

- [ ] **Step 3: Implement the helper and the migration**

```python
# backend/src/cellar/infrastructure/persistence/unit_rewrite.py
"""One-off rewrite of stored unit spellings (migration 088). Sync: Alembic runs sync."""

from __future__ import annotations

import json

from sqlalchemy import Connection, text

from cellar.domain.shared.units import canonical_unit


def _template_units(items: list | None) -> tuple[list | None, bool]:
    if not items:
        return items, False
    out, changed = [], False
    for item in items:
        new = canonical_unit(item.get("unit"))
        if new != item.get("unit"):
            item, changed = {**item, "unit": new}, True
        out.append(item)
    return out, changed


def rewrite_stored_units(conn: Connection) -> None:
    for table in ("readout_definitions", "condition_definitions"):
        rows = conn.execute(text(f"select id, unit from {table} where unit is not null")).all()
        for row_id, unit in rows:
            new = canonical_unit(unit)
            if new != unit:
                conn.execute(text(f"update {table} set unit=:u where id=:id"), {"u": new, "id": row_id})
    rows = conn.execute(
        text("select id, readout_templates, condition_templates from protocol_forms")
    ).all()
    for form_id, readouts, conditions in rows:
        new_r, changed_r = _template_units(readouts)
        new_c, changed_c = _template_units(conditions)
        if changed_r or changed_c:
            conn.execute(
                text(
                    "update protocol_forms set readout_templates=cast(:r as jsonb), "
                    "condition_templates=cast(:c as jsonb) where id=:id"
                ),
                {
                    "r": json.dumps(new_r),
                    "c": json.dumps(new_c) if new_c is not None else None,
                    "id": form_id,
                },
            )
```

```python
# backend/alembic/versions/088_canonical_units.py
"""one spelling per unit on readouts, conditions and form templates

Revision ID: 088_canonical_units
Revises: 087_campaign_name_snapshot_width
Create Date: 2026-10-08
"""

from __future__ import annotations

from typing import Sequence

from alembic import op

from cellar.infrastructure.persistence.unit_rewrite import rewrite_stored_units

revision: str = "088_canonical_units"
down_revision: str | None = "087_campaign_name_snapshot_width"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    rewrite_stored_units(op.get_bind())


def downgrade() -> None:
    # Spelling only; the old variants carry nothing worth restoring.
    pass
```

- [ ] **Step 4: Run the test and the migration**

Run: `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/test_canonical_units_migration.py -q -p no:warnings`
Expected: PASS.
Run: `cd backend && uv run alembic upgrade head` (root `.env` exported, as `make` does)
Expected: upgrades to `088_canonical_units`; `select distinct unit from readout_definitions` shows no `uM`.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(units): rewrite stored unit spellings (migration 088)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/alembic/versions/088_canonical_units.py backend/src/cellar/infrastructure/persistence/unit_rewrite.py backend/tests/integration/test_canonical_units_migration.py
```

---

### Task 4: Forms tied to categories

**Files:**
- Modify: `backend/src/cellar/domain/workspace_config/protocol_form.py`
- Modify: `backend/src/cellar/domain/workspace_config/repository.py` (`ProtocolFormRepository`)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/workspace_config/models.py` (`ProtocolFormModel`)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/workspace_config/protocol_form_repository.py`
- Create: `backend/alembic/versions/089_protocol_form_category.py`
- Modify: `backend/src/cellar/application/workspace_config/create_protocol_form.py`, `update_protocol_form.py`
- Modify: `backend/src/cellar/application/workspace_config/protocol_categories.py` (`DeleteProtocolCategory`)
- Modify: `backend/src/cellar/infrastructure/di/_workspace_config.py` (`_delete_category` gets the form repo)
- Modify: `backend/src/cellar/interface/routes/protocol_forms.py` (typed template DTOs, new fields)
- Test: `backend/tests/_auth.py`, `backend/tests/unit/domain/workspace_config/test_protocol_form.py`, `backend/tests/integration/test_protocol_form_defaults.py`, `backend/tests/api/test_protocol_forms_category.py`
- Regenerate: orval

**Interfaces:**
- Produces: `ProtocolForm.category_id: uuid.UUID | None`, `ProtocolForm.assay_format_from_target: bool` (create/update kwargs of the same names); `ProtocolFormRepository.clear_default(workspace_id, category_id: uuid.UUID | None, *, except_id: uuid.UUID | None) -> None`; `ProtocolFormRepository.clear_category_defaults(workspace_id, category_id) -> None`; API: `ProtocolFormResponse` gains `category_id`, `assay_format_from_target`, typed `readout_templates: list[ProtocolFormReadoutTemplate]`, `condition_templates: list[ProtocolFormConditionTemplate] | None`, `ontology_defaults: list[ProtocolFormOntologyDefaultTemplate] | None`; create/update bodies accept `category_id`, `assay_format_from_target`.

- [ ] **Step 1: Write the failing domain test** (append to `tests/unit/domain/workspace_config/test_protocol_form.py`)

```python
def test_form_carries_category_and_assay_format_rule():
    ws, cat = uuid.uuid4(), uuid.uuid4()
    form = ProtocolForm.create(
        workspace_id=ws,
        name="IC50 dose-response",
        category_id=cat,
        assay_format_from_target=True,
        readout_templates=[ProtocolFormReadout(name="Signal", data_type="numeric")],
    )
    assert form.category_id == cat and form.assay_format_from_target is True
    form.update(category_id=None, assay_format_from_target=False)
    assert form.category_id is None and form.assay_format_from_target is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/unit/domain/workspace_config/test_protocol_form.py -q -p no:warnings`
Expected: FAIL with `TypeError: ... unexpected keyword argument 'category_id'`.

- [ ] **Step 3: Implement domain, persistence and migration**

Domain (`protocol_form.py`): add `category_id: uuid.UUID | None = None` and `assay_format_from_target: bool = False` to `__init__` (store as attributes), to `create(...)` (pass through), and to `update(...)` as `category_id: uuid.UUID | object | None = UNSET`, `assay_format_from_target: bool | object = UNSET` with

```python
        if category_id is not UNSET:
            self.category_id = category_id  # type: ignore[assignment]
        if assay_format_from_target is not UNSET:
            self.assay_format_from_target = bool(assay_format_from_target)
```

Update the class docstring: "At most one form per category (and one generic form) may be ``is_default``."

Repository protocol (`repository.py`, `ProtocolFormRepository`):

```python
    async def clear_default(
        self, workspace_id: uuid.UUID, category_id: uuid.UUID | None, *, except_id: uuid.UUID | None
    ) -> None:
        """Unset is_default on the category's forms (generic forms when None), except one."""
        ...

    async def clear_category_defaults(self, workspace_id: uuid.UUID, category_id: uuid.UUID) -> None:
        """Before a category is deleted, so its forms turn generic without a second default."""
        ...
```

Model (`models.py`, `ProtocolFormModel`):

```python
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("protocol_categories.id", ondelete="SET NULL")
    )
    assay_format_from_target: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    __table_args__ = (
        Index("ix_protocol_form_ws", "workspace_id"),
        Index(
            "ux_protocol_form_default",
            "workspace_id",
            text("coalesce(category_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )
```

(import `ForeignKey`, `text` from sqlalchemy if not already imported in models.py.)

SQLAlchemy repository: map `category_id` and `assay_format_from_target` in `_to_domain`, `_to_model`, `_update_model`; add

```python
    async def clear_default(self, workspace_id, category_id, *, except_id):
        stmt = (
            update(ProtocolFormModel)
            .where(
                ProtocolFormModel.workspace_id == workspace_id,
                ProtocolFormModel.is_default.is_(True),
                ProtocolFormModel.category_id.is_(None)
                if category_id is None
                else ProtocolFormModel.category_id == category_id,
            )
            .values(is_default=False, version=ProtocolFormModel.version + 1)
        )
        if except_id is not None:
            stmt = stmt.where(ProtocolFormModel.id != except_id)
        await self._session.execute(stmt)

    async def clear_category_defaults(self, workspace_id, category_id):
        await self.clear_default(workspace_id, category_id, except_id=None)
```

(import `update` from sqlalchemy.)

Migration:

```python
# backend/alembic/versions/089_protocol_form_category.py
"""protocol forms serve a category; at most one default per category

Revision ID: 089_protocol_form_category
Revises: 088_canonical_units
Create Date: 2026-10-08
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "089_protocol_form_category"
down_revision: str | None = "088_canonical_units"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_NIL = "'00000000-0000-0000-0000-000000000000'::uuid"


def upgrade() -> None:
    op.add_column("protocol_forms", sa.Column("category_id", sa.Uuid(), nullable=True))
    op.add_column(
        "protocol_forms",
        sa.Column("assay_format_from_target", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_foreign_key(
        "fk_protocol_form_category",
        "protocol_forms",
        "protocol_categories",
        ["category_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # "At most one default" was never enforced: keep the most recently updated per workspace.
    op.execute(
        """
        update protocol_forms f set is_default = false
        where f.is_default and exists (
            select 1 from protocol_forms g
            where g.workspace_id = f.workspace_id and g.is_default
              and (g.updated_at, g.id) > (f.updated_at, f.id)
        )
        """
    )
    op.execute(
        f"create unique index ux_protocol_form_default on protocol_forms "
        f"(workspace_id, coalesce(category_id, {_NIL})) where is_default"
    )


def downgrade() -> None:
    op.execute("drop index if exists ux_protocol_form_default")
    op.drop_constraint("fk_protocol_form_category", "protocol_forms", type_="foreignkey")
    op.drop_column("protocol_forms", "assay_format_from_target")
    op.drop_column("protocol_forms", "category_id")
```

Use cases: `CreateProtocolFormCommand` and `UpdateProtocolFormCommand` gain `category_id: uuid.UUID | None = None` / `= UNSET` and `assay_format_from_target: bool = False` / `= UNSET`, passed to `ProtocolForm.create` / collected into `update_kwargs`. Before saving a form that is (or becomes) default, clear the others — **before** `self._repo.save(form)` so the bulk update runs before the insert/update is flushed:

```python
            if form.is_default:
                await self._repo.clear_default(
                    form.workspace_id, form.category_id, except_id=form.id
                )
            await self._repo.save(form)
```

`DeleteProtocolCategory.__init__` gains `form_repo: ProtocolFormRepository`; before `await self._repo.delete(...)`:

```python
            await self._form_repo.clear_category_defaults(input.workspace_id, category.id)
```

DI `_delete_category`: pass `SQLAlchemyProtocolFormRepository(uow)` as `form_repo`.

Routes (`protocol_forms.py`): replace the opaque `list[dict]` with typed models (orval then generates typed items):

```python
class ProtocolFormReadoutTemplate(BaseModel):
    name: str
    data_type: str
    unit: str | None = None
    aggregation: str = "none"
    normalization: str = "none"
    is_calculated: bool = False
    calculation_formula: str | None = None
    pick_list_values: list[Any] | None = None
    dose_response_config: dict[str, Any] | None = None


class ProtocolFormConditionTemplate(BaseModel):
    name: str
    data_type: str
    unit: str | None = None
    pick_list_values: list[str] | None = None


class ProtocolFormOntologyDefaultTemplate(BaseModel):
    slot_name: str
    terms: list[dict[str, Any]] = []
```

`ProtocolFormResponse` gains `category_id: uuid.UUID | None = None`, `assay_format_from_target: bool = False`; its template fields use the typed models (`ProtocolFormReadoutTemplate(**asdict(r))`, etc.). `CreateProtocolFormBody` / `UpdateProtocolFormBody` gain `category_id: uuid.UUID | None = None`, `assay_format_from_target: bool = False` (update: `bool | None = None`), and type their template lists with the models; convert to dicts for the command with `[t.model_dump() for t in body.readout_templates]`. Add `"category_id"`, `"assay_format_from_target"` to the PATCH field loop.

- [ ] **Step 4: Write the integration and API tests**

```python
# backend/tests/integration/test_protocol_form_defaults.py
"""One default per category, enforced in the use case and the database."""

import uuid

from cellar.application.workspace_config.create_protocol_form import (
    CreateProtocolForm,
    CreateProtocolFormCommand,
)
from cellar.application.workspace_config.protocol_categories import (
    DeleteProtocolCategory,
    DeleteProtocolCategoryCommand,
)
from cellar.domain.workspace_config.protocol_category import ProtocolCategory
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.protocol_category_repository import (  # noqa: E501
    SQLAlchemyProtocolCategoryRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.protocol_form_repository import (  # noqa: E501
    SQLAlchemyProtocolFormRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests._auth import admin_auth

READOUT = [{"name": "Signal", "data_type": "numeric"}]


class _NoEvents:
    async def dispatch_all(self, events):
        return None


async def _create(session_factory, ws, auth, **kw):
    uow = AsyncUnitOfWork(session_factory)
    uc = CreateProtocolForm(uow, SQLAlchemyProtocolFormRepository(uow), _NoEvents())
    return (await uc(CreateProtocolFormCommand(workspace_id=ws, readout_templates=READOUT, **kw), auth=auth)).unwrap()


async def _category(session_factory, ws, label):
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        cat = ProtocolCategory.create(workspace_id=ws, label=label)
        await SQLAlchemyProtocolCategoryRepository(uow).save(cat)
        await uow.commit()
    return cat


async def _forms(session_factory, ws):
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        return await SQLAlchemyProtocolFormRepository(uow).find_by_workspace(ws)


async def test_a_new_default_replaces_the_categorys_old_default(session_factory, workspace_id, user_id):
    auth = admin_auth(workspace_id, user_id)
    cat = await _category(session_factory, workspace_id, "Enzyme inhibition")
    first = await _create(session_factory, workspace_id, auth, name="A", category_id=cat.id, is_default=True)
    second = await _create(session_factory, workspace_id, auth, name="B", category_id=cat.id, is_default=True)
    generic = await _create(session_factory, workspace_id, auth, name="G", is_default=True)
    by_id = {f.id: f for f in await _forms(session_factory, workspace_id)}
    assert not by_id[first.id].is_default and by_id[second.id].is_default
    assert by_id[generic.id].is_default  # other scope untouched


async def test_deleting_a_category_turns_its_forms_generic_without_a_second_default(
    session_factory, workspace_id, user_id
):
    auth = admin_auth(workspace_id, user_id)
    cat = await _category(session_factory, workspace_id, "Binding")
    own = await _create(session_factory, workspace_id, auth, name="Kd", category_id=cat.id, is_default=True)
    await _create(session_factory, workspace_id, auth, name="G", is_default=True)
    uow = AsyncUnitOfWork(session_factory)
    uc = DeleteProtocolCategory(
        uow,
        SQLAlchemyProtocolCategoryRepository(uow),
        SQLAlchemyProtocolRepository(uow),
        form_repo=SQLAlchemyProtocolFormRepository(uow),
    )
    (await uc(DeleteProtocolCategoryCommand(workspace_id=workspace_id, category_id=cat.id), auth=auth)).unwrap()
    by_id = {f.id: f for f in await _forms(session_factory, workspace_id)}
    assert by_id[own.id].category_id is None and not by_id[own.id].is_default
```

Create the shared helper used here and in Task 8:

```python
# backend/tests/_auth.py
"""An admin acting in a workspace, for application-level tests (same shape as the CLI loaders')."""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class _Admin:
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    workspace_role: str = "admin"
    org_id: uuid.UUID | None = None
    org_slug: str | None = None
    name: str = "test admin"
    email: str = ""
    is_admin: bool = True

    def has_role(self, minimum_role: str) -> bool:
        return True

    async def check_action(self, action: str) -> bool:
        return True


def admin_auth(workspace_id: uuid.UUID, user_id: uuid.UUID) -> _Admin:
    return _Admin(user_id=user_id, workspace_id=workspace_id)
```

Migration duplicate-default test (Review Focus 1), same file:

```python
async def test_migration_keeps_one_default_per_workspace(session_factory, workspace_id):
    """089's dedupe statement, run against two legacy defaults."""
    from sqlalchemy import text

    async with session_factory() as s:
        await s.execute(text("drop index if exists ux_protocol_form_default"))
        for name, ts in (("old", "2026-01-01"), ("new", "2026-02-01")):
            await s.execute(
                text(
                    "insert into protocol_forms (id, workspace_id, name, is_default, readout_templates, "
                    "version, created_at, updated_at) values (gen_random_uuid(), :ws, :n, true, "
                    "'[]'::jsonb, 1, :ts, :ts)"
                ),
                {"ws": workspace_id, "n": name, "ts": ts},
            )
        await s.execute(
            text(
                "update protocol_forms f set is_default = false where f.is_default and exists ("
                "select 1 from protocol_forms g where g.workspace_id = f.workspace_id and g.is_default "
                "and (g.updated_at, g.id) > (f.updated_at, f.id))"
            )
        )
        rows = dict((await s.execute(text("select name, is_default from protocol_forms where workspace_id=:ws"), {"ws": workspace_id})).all())
        await s.rollback()
    assert rows == {"old": False, "new": True}
```

```python
# backend/tests/api/test_protocol_forms_category.py
"""Forms serve a category over the API."""

from tests.api._protocols import seed_protocol_categories


async def test_form_round_trips_category_and_keeps_template_fields(client):
    cats = await seed_protocol_categories(client)
    enzyme = next(c for c in (await client.get("/api/v1/protocol-categories")).json() if c["label"] == "Enzyme inhibition")
    body = {
        "name": "IC50 dose-response",
        "category_id": enzyme["id"],
        "assay_format_from_target": True,
        "readout_templates": [
            {"name": "Signal", "data_type": "numeric", "normalization": "percent_inhibition"},
            {
                "name": "IC50",
                "data_type": "dose_response",
                "unit": "uM",
                "dose_response_config": {"curve_type": "ic50", "y_readout_name": "Signal", "y_normalization": "percent_inhibition"},
            },
        ],
    }
    r = await client.post("/api/v1/protocol-forms", json=body)
    assert r.status_code == 201, r.text
    form = r.json()
    assert form["category_id"] == enzyme["id"] and form["assay_format_from_target"] is True
    assert form["readout_templates"][1]["unit"] == "µM"
    assert form["readout_templates"][1]["dose_response_config"]["curve_type"] == "ic50"
```

(`seed_protocol_categories` already exists in `tests/api/_protocols.py`; ignore its return value if it returns nothing.)

- [ ] **Step 5: Run all of the above and the FK coverage check**

Run: `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/unit/domain/workspace_config/test_protocol_form.py tests/integration/test_protocol_form_defaults.py tests/api/test_protocol_forms_category.py tests/unit/cascade/test_fk_coverage.py -q -p no:warnings`
Expected: PASS. If `test_fk_coverage` reports the new FK `protocol_forms.category_id`, add it to `IGNORED_FKS` with the comment `# SET NULL: a deleted category turns its forms generic (Task 4)` and re-run.
Run: `uv run alembic upgrade head` (root `.env` exported). Expected: head `089_protocol_form_category`.

- [ ] **Step 6: Regenerate orval and commit**

```bash
cd frontend && pnpm generate:api   # revert version-stamp-only files
git commit -m "feat(protocol-forms): forms serve a category; one default per category

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar/domain/workspace_config/protocol_form.py backend/src/cellar/domain/workspace_config/repository.py backend/src/cellar/infrastructure/persistence/sqlalchemy/workspace_config/models.py backend/src/cellar/infrastructure/persistence/sqlalchemy/workspace_config/protocol_form_repository.py backend/alembic/versions/089_protocol_form_category.py backend/src/cellar/application/workspace_config/create_protocol_form.py backend/src/cellar/application/workspace_config/update_protocol_form.py backend/src/cellar/application/workspace_config/protocol_categories.py backend/src/cellar/infrastructure/di/_workspace_config.py backend/src/cellar/interface/routes/protocol_forms.py backend/tests frontend/src/shared/lib/api
```

---

### Task 5: Assay format follows the target

**Files:**
- Create: `backend/src/cellar/domain/screening_assay/assay_format.py`
- Modify: `backend/src/cellar/application/screening/create_protocol.py`
- Modify: `backend/src/cellar/infrastructure/di/_screening.py` (CreateProtocol gets `form_repo`, `target_repo`)
- Test: `backend/tests/unit/domain/screening_assay/test_assay_format.py`, `backend/tests/api/test_protocol_create_flow.py`

**Interfaces:**
- Consumes: `ProtocolForm.assay_format_from_target`, `ProtocolForm.ontology_defaults` (Task 4).
- Produces: `ASSAY_FORMAT_BY_TARGET_TYPE: dict[TargetType, OntologyTerm | None]`; `assay_format_for_targets(types: Iterable[TargetType]) -> OntologyTerm | None`; `CreateProtocolCommand.form_id: uuid.UUID | None = None`.

- [ ] **Step 1: Write the failing domain test**

```python
# backend/tests/unit/domain/screening_assay/test_assay_format.py
from cellar.domain.screening_assay.assay_format import (
    ASSAY_FORMAT_BY_TARGET_TYPE,
    assay_format_for_targets,
)
from cellar.domain.screening_assay.enums import TargetType

BAO = "http://www.bioassayontology.org/bao#"


def test_every_target_type_is_mapped():
    assert set(ASSAY_FORMAT_BY_TARGET_TYPE) == set(TargetType)


def test_single_and_complex_targets():
    assert assay_format_for_targets([TargetType.SINGLE_PROTEIN]).term_id == f"{BAO}BAO_0000357"
    assert assay_format_for_targets([TargetType.PROTEIN_COMPLEX]).term_id == f"{BAO}BAO_0000223"
    assert assay_format_for_targets([TargetType.DOMAIN, TargetType.SINGLE_PROTEIN]).label == "single protein format"


def test_mixed_unknown_or_no_targets_give_no_format():
    assert assay_format_for_targets([TargetType.SINGLE_PROTEIN, TargetType.NUCLEIC_ACID]) is None
    assert assay_format_for_targets([TargetType.UNKNOWN]) is None
    assert assay_format_for_targets([]) is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/unit/domain/screening_assay/test_assay_format.py -q -p no:warnings`
Expected: FAIL with ModuleNotFoundError.

- [ ] **Step 3: Implement the mapping and apply it on create**

```python
# backend/src/cellar/domain/screening_assay/assay_format.py
"""The BAO assay format a target-based assay has, from its registry target type."""

from __future__ import annotations

from collections.abc import Iterable

from cellar.domain.screening_assay.enums import TargetType
from cellar.domain.shared.ontology import OntologyTerm

BAO = "http://www.bioassayontology.org/bao#"


def _bao(code: str, label: str) -> OntologyTerm:
    return OntologyTerm(term_id=f"{BAO}{code}", label=label, ontology_source="BAO", uri=f"{BAO}{code}")


_SINGLE = _bao("BAO_0000357", "single protein format")
_COMPLEX = _bao("BAO_0000223", "protein complex format")

ASSAY_FORMAT_BY_TARGET_TYPE: dict[TargetType, OntologyTerm | None] = {
    TargetType.SINGLE_PROTEIN: _SINGLE,
    TargetType.DOMAIN: _SINGLE,
    TargetType.PROTEIN_COMPLEX: _COMPLEX,
    TargetType.PROTEIN_PROTEIN_INTERACTION: _COMPLEX,
    TargetType.PROTEIN_FAMILY: _bao("BAO_0000224", "protein format"),
    TargetType.NUCLEIC_ACID: _bao("BAO_0000225", "nucleic acid format"),
    TargetType.ORGANISM: _bao("BAO_0000218", "organism-based format"),
    TargetType.CELL_LINE: _bao("BAO_0000219", "cell based format"),
    TargetType.TISSUE: _bao("BAO_0000221", "tissue-based format"),
    TargetType.UNKNOWN: None,
}


def assay_format_for_targets(types: Iterable[TargetType]) -> OntologyTerm | None:
    """One format when every target maps to the same one; otherwise none."""
    formats = {ASSAY_FORMAT_BY_TARGET_TYPE.get(t) for t in types}
    if len(formats) != 1:
        return None
    return formats.pop()
```

`CreateProtocolCommand` gains `form_id: uuid.UUID | None = None` (comment: "The form the dialog started from; decides whether the assay format follows the targets."). `CreateProtocol.__init__` gains keyword args `form_repo: ProtocolFormRepository | None = None`, `target_repo: TargetRepository | None = None`. Inside the `async with self._uow:` block, right after `await self._repo.lock_naming(...)` and before `derive`:

```python
            if input.form_id is not None and "assay_format" not in ontology_annotations:
                form = (
                    await self._forms.find_by_id_in_workspace(input.workspace_id, input.form_id)
                    if self._forms
                    else None
                )
                if form is None:
                    return Failure(NotFoundError("ProtocolForm", str(input.form_id)))
                if form.assay_format_from_target:
                    targets = (
                        await self._targets.find_by_ids(input.workspace_id, target_ids)
                        if self._targets and target_ids
                        else []
                    )
                    fmt = assay_format_for_targets(t.target_type for t in targets)
                    if fmt is None:
                        fmt = next(
                            (
                                OntologyTerm(
                                    term_id=t["term_id"], label=t["label"],
                                    ontology_source=t["ontology_source"], uri=t.get("uri"),
                                )
                                for d in form.ontology_defaults
                                if d.slot_name == "assay_format"
                                for t in d.terms
                            ),
                            None,
                        )
                    if fmt is not None:
                        ontology_annotations["assay_format"] = [fmt]
```

DI (`_screening.py`, wherever `CreateProtocol(...)` is constructed): add `form_repo=SQLAlchemyProtocolFormRepository(uow), target_repo=SQLAlchemyTargetRepository(uow)` (use the target repository class the name service already uses in that file).

- [ ] **Step 4: Write the API test**

```python
# backend/tests/api/test_protocol_create_flow.py
"""Create flow over the API: forms, assay format from target, siblings, nicknames."""

from tests.api._protocols import seed_protocol_categories


async def _enzyme_form(client, *, from_target=True):
    enzyme = next(c for c in (await client.get("/api/v1/protocol-categories")).json() if c["label"] == "Enzyme inhibition")
    body = {
        "name": "IC50 dose-response",
        "category_id": enzyme["id"],
        "assay_format_from_target": from_target,
        "readout_templates": [{"name": "Signal", "data_type": "numeric"}],
        "ontology_defaults": [
            {"slot_name": "assay_format", "terms": [{"term_id": "http://www.bioassayontology.org/bao#BAO_0000217", "label": "biochemical format", "ontology_source": "BAO"}]}
        ],
    }
    return (await client.post("/api/v1/protocol-forms", json=body)).json()


async def test_assay_format_follows_a_single_protein_target(client, seeded_target):
    await seed_protocol_categories(client)
    form = await _enzyme_form(client)
    body = {
        "category": "Enzyme inhibition",
        "protocol_type": "biochemical",
        "target_ids": [seeded_target["id"]],
        "form_id": form["id"],
        "readout_definitions": [{"name": "Signal", "data_type": "numeric"}],
    }
    r = await client.post("/api/v1/protocols", json=body)
    assert r.status_code == 201, r.text
    fmt = r.json()["ontology_annotations"]["assay_format"][0]
    assert fmt["label"] == "single protein format"


async def test_without_targets_the_forms_format_applies(client):
    await seed_protocol_categories(client)
    form = await _enzyme_form(client)
    body = {
        "category": "Growth inhibition",  # needs organism; use a category without target need
        "protocol_type": "biochemical",
        "form_id": form["id"],
        "readout_definitions": [{"name": "Signal", "data_type": "numeric"}],
        "ontology_annotations": {"organism": [{"term_id": "http://purl.bioontology.org/ontology/NCBITAXON/1773", "label": "Mycobacterium tuberculosis", "ontology_source": "NCBITAXON"}]},
    }
    r = await client.post("/api/v1/protocols", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["ontology_annotations"]["assay_format"][0]["label"] == "biochemical format"
```

`seeded_target`: if no fixture exists that inserts a mirrored target, add one to `tests/api/conftest.py` that inserts a `targets` row (`target_type='single_protein'`, `name='PptT'`, `organism='Mycobacterium tuberculosis'`) for the client's workspace via the test session and yields `{"id": str(id)}`; look at `tests/api/conftest.py` and `tests/api/_protocols.py` for how other tests seed rows.

- [ ] **Step 5: Run the tests**

Run: `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/unit/domain/screening_assay/test_assay_format.py tests/api/test_protocol_create_flow.py -q -p no:warnings`
Expected: PASS (the API test needs the `form_id` request field added in Task 10; until then add `form_id: uuid.UUID | None = None` to `CreateProtocolRequest` here and pass it through in the route — Task 10 then only adds siblings and nicknames).

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(protocols): assay format follows the registry target when the form says so

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar/domain/screening_assay/assay_format.py backend/src/cellar/application/screening/create_protocol.py backend/src/cellar/infrastructure/di/_screening.py backend/src/cellar/interface/routes/protocols.py backend/tests
```

---

### Task 6: Shipped default forms

**Files:**
- Create: `backend/src/cellar/domain/workspace_config/default_protocol_forms.py`
- Create: `backend/src/cellar/application/workspace_config/protocol_form_defaults.py`
- Modify: `backend/src/cellar/application/workspace_config/protocol_categories.py` (`SeedDefaultProtocolCategories` also seeds forms)
- Modify: `backend/src/cellar/infrastructure/di/_workspace_config.py`, `backend/src/cellar/interface/dependencies/_workspace_config.py`, `backend/src/cellar/interface/routes/protocol_forms.py` (`POST /defaults`)
- Test: `backend/tests/unit/application/workspace_config/test_default_protocol_forms.py`, `backend/tests/api/test_protocol_forms_defaults.py`
- Regenerate: orval

**Interfaces:**
- Produces: `DefaultForm` dataclass; `DEFAULT_PROTOCOL_FORMS: tuple[DefaultForm, ...]`; `async seed_default_forms(form_repo, category_repo, workspace_id) -> list[ProtocolForm]` (returns the forms it created); `SeedDefaultProtocolForms` use case + `SeedDefaultProtocolFormsCommand(workspace_id)`; `POST /api/v1/protocol-forms/defaults` → `list[ProtocolFormResponse]`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/application/workspace_config/test_default_protocol_forms.py
"""Every shipped form is a valid starting point for a protocol."""

import uuid

import pytest

from cellar.application.screening._dose_response_config_serde import (
    deserialize_dose_response_config,
)
from cellar.domain.screening_assay.enums import (
    ConditionDataType,
    ProtocolType,
    ReadoutDataType,
    ReadoutNormalization,
)
from cellar.domain.screening_assay.protocol import ConditionDefinition, Protocol, ReadoutDefinition
from cellar.domain.shared.protocol_naming import DEFAULT_CATEGORY_PATTERNS
from cellar.domain.workspace_config.default_protocol_forms import DEFAULT_PROTOCOL_FORMS


def test_every_default_category_has_a_form_and_forms_name_real_categories():
    assert {f.category for f in DEFAULT_PROTOCOL_FORMS} == set(DEFAULT_CATEGORY_PATTERNS)


def test_one_default_only_where_a_category_has_one_form():
    by_cat: dict[str, list] = {}
    for f in DEFAULT_PROTOCOL_FORMS:
        by_cat.setdefault(f.category, []).append(f)
    for forms in by_cat.values():
        assert sum(f.is_default for f in forms) == (1 if len(forms) == 1 else 0)


@pytest.mark.parametrize("form", DEFAULT_PROTOCOL_FORMS, ids=lambda f: f"{f.category}: {f.name}")
def test_each_form_builds_a_valid_protocol(form):
    pid = uuid.uuid4()
    readouts = [
        ReadoutDefinition(
            protocol_id=pid,
            name=r.name,
            data_type=ReadoutDataType(r.data_type),
            unit=r.unit,
            normalizations=frozenset(
                {ReadoutNormalization(r.normalization)} if r.normalization != "none" else set()
            ),
            dose_response_config=deserialize_dose_response_config(r.dose_response_config)
            if r.dose_response_config
            else None,
        )
        for r in form.readouts
    ]
    Protocol.create(
        workspace_id=uuid.uuid4(),
        name="x",
        protocol_type=ProtocolType(form.protocol_type),
        created_by=uuid.uuid4(),
        readout_definitions=readouts,
        condition_definitions=[
            ConditionDefinition(protocol_id=pid, name=c.name, data_type=ConditionDataType(c.data_type), unit=c.unit)
            for c in form.conditions
        ]
        or None,
    )
```

```python
# backend/tests/api/test_protocol_forms_defaults.py
"""Add default forms: once per category form, idempotent."""


async def test_default_categories_bring_their_forms_and_reseeding_adds_nothing(client):
    r = await client.post("/api/v1/protocol-categories/defaults")
    assert r.status_code in (200, 201), r.text
    forms = (await client.get("/api/v1/protocol-forms")).json()
    enzyme = [f for f in forms if f["name"] in ("IC50 dose-response", "% inhibition single point")]
    assert enzyme and all(f["category_id"] for f in forms)
    again = await client.post("/api/v1/protocol-forms/defaults")
    assert again.status_code == 200, again.text
    assert len((await client.get("/api/v1/protocol-forms")).json()) == len(forms)
```

(Check the real path of the category seed route in `routes/protocol_categories.py` — it is the `SeedDefaultProtocolCategoriesDep` route around line 84 — and use it.)

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/unit/application/workspace_config/test_default_protocol_forms.py -q -p no:warnings`
Expected: FAIL with ModuleNotFoundError.

- [ ] **Step 3: Implement the data, the seeding and the route**

```python
# backend/src/cellar/domain/workspace_config/default_protocol_forms.py
"""Shipped starting points, one or more per default category.

General conventions only. A category with more than one common readout convention ships each
as its own form and none is the default; a category with one form gets it as its default.
"""

from __future__ import annotations

from dataclasses import dataclass

from cellar.domain.workspace_config.protocol_form import (
    ProtocolFormCondition,
    ProtocolFormReadout,
)

BAO = "http://www.bioassayontology.org/bao#"


@dataclass(frozen=True)
class DefaultForm:
    category: str
    name: str
    protocol_type: str
    readouts: tuple[ProtocolFormReadout, ...]
    conditions: tuple[ProtocolFormCondition, ...] = ()
    assay_format: tuple[str, str] | None = None  # (BAO code, label)
    assay_format_from_target: bool = False
    is_default: bool = False


def _signal(normalization: str) -> ProtocolFormReadout:
    return ProtocolFormReadout(name="Signal", data_type="numeric", normalization=normalization)


def _fit(name: str, curve: str, normalization: str) -> ProtocolFormReadout:
    return ProtocolFormReadout(
        name=name,
        data_type="dose_response",
        unit="µM",
        dose_response_config={
            "curve_type": curve,
            "y_readout_name": "Signal",
            "y_normalization": normalization,
        },
    )


def _value(name: str, unit: str | None = None) -> ProtocolFormReadout:
    return ProtocolFormReadout(name=name, data_type="numeric", unit=unit)


def _cond(name: str, data_type: str = "numeric", unit: str | None = None) -> ProtocolFormCondition:
    return ProtocolFormCondition(name=name, data_type=data_type, unit=unit)


_BIOCHEMICAL = ("BAO_0000217", "biochemical format")
_ORGANISM = ("BAO_0000218", "organism-based format")
_CELL = ("BAO_0000219", "cell based format")
_PHYSCHEM = ("BAO_0000100", "small-molecule physicochemical format")
_PLASMA = ("BAO_0020003", "plasma format")

_INH, _ACT, _CTRL = "percent_inhibition", "percent_activation", "percent_control"


def _dr(category, name, ptype, fmt, curve, norm, **kw) -> DefaultForm:
    return DefaultForm(category, name, ptype, (_signal(norm), _fit(name.split()[0], curve, norm)), assay_format=fmt, **kw)


DEFAULT_PROTOCOL_FORMS: tuple[DefaultForm, ...] = (
    _dr("Enzyme inhibition", "IC50 dose-response", "biochemical", _BIOCHEMICAL, "ic50", _INH, assay_format_from_target=True),
    DefaultForm("Enzyme inhibition", "% inhibition single point", "biochemical", (_signal(_INH),), assay_format=_BIOCHEMICAL, assay_format_from_target=True),
    _dr("Enzyme activation", "EC50 dose-response", "biochemical", _BIOCHEMICAL, "ec50", _ACT, assay_format_from_target=True),
    DefaultForm("Enzyme activation", "% activation single point", "biochemical", (_signal(_ACT),), assay_format=_BIOCHEMICAL, assay_format_from_target=True),
    DefaultForm("Binding", "Kd", "biochemical", (_value("Kd", "µM"),), assay_format=_BIOCHEMICAL, assay_format_from_target=True),
    DefaultForm("Binding", "Thermal shift (ΔTm)", "biochemical", (_value("ΔTm", "°C"),), assay_format=_BIOCHEMICAL, assay_format_from_target=True),
    _dr("Receptor function", "EC50 dose-response", "cell_based", _CELL, "ec50", _ACT, is_default=True),
    _dr("Ion-channel inhibition", "IC50 dose-response", "cell_based", _CELL, "ic50", _INH, is_default=True),
    DefaultForm("Growth inhibition", "MIC", "whole_cell", (_value("MIC", "µM"),), assay_format=_ORGANISM),
    _dr("Growth inhibition", "IC50 dose-response", "whole_cell", _ORGANISM, "ic50", _INH),
    DefaultForm("Growth inhibition", "% inhibition single point", "whole_cell", (_signal(_INH),), assay_format=_ORGANISM),
    DefaultForm("Bactericidal activity", "MBC", "whole_cell", (_value("MBC", "µM"),), assay_format=_ORGANISM, is_default=True),
    _dr("Intracellular growth inhibition", "IC50 dose-response", "cell_based", _CELL, "ic50", _INH, is_default=True),
    DefaultForm("Metabolite rescue", "MIC", "whole_cell", (_value("MIC", "µM"),), (_cond("Metabolite", "text"),), assay_format=_ORGANISM, is_default=True),
    _dr("Membrane potential", "EC50 dose-response", "whole_cell", _ORGANISM, "ec50", _CTRL, is_default=True),
    DefaultForm("Resistance selection", "Frequency of resistance", "whole_cell", (_value("Frequency of resistance"),), (_cond("Selecting concentration", unit="µM"),), assay_format=_ORGANISM, is_default=True),
    DefaultForm("Combination (checkerboard)", "FICI", "whole_cell", (_value("FICI"),), assay_format=_ORGANISM, is_default=True),
    _dr("Cytotoxicity", "CC50 dose-response", "cell_based", _CELL, "ic50", _CTRL, is_default=True),
    _dr("Infection inhibition", "EC50 dose-response", "cell_based", _CELL, "ec50", _INH, is_default=True),
    _dr("In vitro translation inhibition", "IC50 dose-response", "biochemical", ("BAO_0000366", "cell-free format"), "ic50", _INH, is_default=True),
    _dr("Intrabacterial pH homeostasis", "EC50 dose-response", "whole_cell", _ORGANISM, "ec50", _CTRL, is_default=True),
    DefaultForm("Detection interference", "% inhibition single point", "biochemical", (_signal(_INH),), assay_format=_BIOCHEMICAL, is_default=True),
    DefaultForm("Metabolic stability", "Metabolic stability", "admet", (_value("% remaining", "%"), _value("CLint", "µL/min/mg")), (_cond("Incubation time", unit="min"),), assay_format=("BAO_0000251", "microsome format"), is_default=True),
    DefaultForm("Plasma stability", "Plasma stability", "admet", (_value("% remaining", "%"),), (_cond("Incubation time", unit="min"),), assay_format=_PLASMA, is_default=True),
    DefaultForm("Plasma protein binding", "Plasma protein binding", "admet", (_value("Fraction unbound", "fraction"),), assay_format=_PLASMA, is_default=True),
    DefaultForm("Permeability", "Permeability", "admet", (_value("Papp", "10-6 cm/s"),), assay_format=_CELL, is_default=True),
    DefaultForm("Solubility", "Solubility", "physicochemical", (_value("Solubility", "µM"),), (_cond("pH"),), assay_format=_PHYSCHEM, is_default=True),
    DefaultForm("Lipophilicity", "LogD", "physicochemical", (_value("LogD"),), (_cond("pH"),), assay_format=_PHYSCHEM, is_default=True),
    DefaultForm("Compound identity / purity", "Purity", "analytical", (_value("Purity", "%"),), assay_format=_PHYSCHEM, is_default=True),
    DefaultForm("Pharmacokinetics", "Pharmacokinetics", "in_vivo", (_value("Cmax", "ng/mL"), _value("AUC", "ng·h/mL"), _value("t1/2", "h")), (_cond("Dose", unit="mg/kg"), _cond("Route", "text")), assay_format=_ORGANISM, is_default=True),
    DefaultForm("In vivo efficacy", "In vivo efficacy", "in_vivo", (_value("Efficacy"),), (_cond("Dose", unit="mg/kg"), _cond("Route", "text")), assay_format=_ORGANISM, is_default=True),
    DefaultForm("Prediction", "Prediction score", "in_silico", (_value("Prediction score"),), is_default=True),
)
```

Note `_dr` names the fit readout by the first word of the form name (`IC50`, `EC50`, `CC50`).

```python
# backend/src/cellar/application/workspace_config/protocol_form_defaults.py
"""Add the shipped default forms a workspace lacks. Never edits existing forms."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_admin, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError
from cellar.domain.workspace_config.default_protocol_forms import BAO, DEFAULT_PROTOCOL_FORMS
from cellar.domain.workspace_config.protocol_form import ProtocolForm, ProtocolFormOntologyDefault
from cellar.domain.workspace_config.repository import (
    ProtocolCategoryRepository,
    ProtocolFormRepository,
)


async def seed_default_forms(
    form_repo: ProtocolFormRepository,
    category_repo: ProtocolCategoryRepository,
    workspace_id: uuid.UUID,
) -> list[ProtocolForm]:
    categories = {c.label.lower(): c for c in await category_repo.find_by_workspace(workspace_id)}
    existing = await form_repo.find_by_workspace(workspace_id)
    have = {(f.category_id, f.name.lower()) for f in existing}
    defaults = {f.category_id for f in existing if f.is_default}
    created: list[ProtocolForm] = []
    for spec in DEFAULT_PROTOCOL_FORMS:
        category = categories.get(spec.category.lower())
        if category is None or (category.id, spec.name.lower()) in have:
            continue
        ontology_defaults = (
            [
                ProtocolFormOntologyDefault(
                    slot_name="assay_format",
                    terms=[
                        {
                            "term_id": f"{BAO}{spec.assay_format[0]}",
                            "label": spec.assay_format[1],
                            "ontology_source": "BAO",
                            "uri": f"{BAO}{spec.assay_format[0]}",
                        }
                    ],
                )
            ]
            if spec.assay_format
            else None
        )
        form = ProtocolForm.create(
            workspace_id=workspace_id,
            name=spec.name,
            protocol_type=spec.protocol_type,
            category_id=category.id,
            assay_format_from_target=spec.assay_format_from_target,
            is_default=spec.is_default and category.id not in defaults,
            readout_templates=list(spec.readouts),
            condition_templates=list(spec.conditions) or None,
            ontology_defaults=ontology_defaults,
        )
        await form_repo.save(form)
        created.append(form)
    return created


@dataclass(frozen=True, kw_only=True)
class SeedDefaultProtocolFormsCommand(Command):
    workspace_id: uuid.UUID


class SeedDefaultProtocolForms:
    def __init__(
        self,
        uow: UnitOfWork,
        form_repo: ProtocolFormRepository,
        category_repo: ProtocolCategoryRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._forms = form_repo
        self._categories = category_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: SeedDefaultProtocolFormsCommand, auth: AuthContext | None = None
    ) -> Result[list[ProtocolForm], DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            await seed_default_forms(self._forms, self._categories, input.workspace_id)
            forms = await self._forms.find_by_workspace(input.workspace_id)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(forms)
```

`SeedDefaultProtocolCategories.__init__` gains keyword `form_repo: ProtocolFormRepository | None = None`; after the category loop, `if self._forms: await seed_default_forms(self._forms, self._repo, input.workspace_id)`. DI: the category seed gets `form_repo=SQLAlchemyProtocolFormRepository(uow)`; define `SeedDefaultProtocolForms` with `(uow, SQLAlchemyProtocolFormRepository(uow), SQLAlchemyProtocolCategoryRepository(uow), c[EventDispatcher])`; add `SeedDefaultProtocolFormsDep`. Route:

```python
@router.post("/defaults", response_model=list[ProtocolFormResponse])
async def add_default_protocol_forms(
    auth: AuthDep, use_case: SeedDefaultProtocolFormsDep
) -> list[ProtocolFormResponse]:
    forms = result_to_response(
        await use_case(SeedDefaultProtocolFormsCommand(workspace_id=auth.workspace_id), auth=auth)
    )
    return [ProtocolFormResponse.from_domain(f) for f in forms]
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/unit/application/workspace_config/test_default_protocol_forms.py tests/api/test_protocol_forms_defaults.py -q -p no:warnings`
Expected: PASS. If a shipped form fails `test_each_form_builds_a_valid_protocol`, fix the form's data (never weaken the domain invariant).

- [ ] **Step 5: Regenerate orval and commit**

```bash
cd frontend && pnpm generate:api   # revert version-stamp-only files
git commit -m "feat(protocol-forms): shipped default forms for every default category

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar/domain/workspace_config/default_protocol_forms.py backend/src/cellar/application/workspace_config/protocol_form_defaults.py backend/src/cellar/application/workspace_config/protocol_categories.py backend/src/cellar/infrastructure/di/_workspace_config.py backend/src/cellar/interface/dependencies/_workspace_config.py backend/src/cellar/interface/routes/protocol_forms.py backend/tests frontend/src/shared/lib/api
```

---

### Task 7: New categories start like an existing one

**Files:**
- Modify: `backend/src/cellar/application/workspace_config/protocol_categories.py` (`CreateProtocolCategoryCommand`, `CreateProtocolCategory`)
- Modify: `backend/src/cellar/infrastructure/di/_workspace_config.py` (CreateProtocolCategory gets `form_repo`)
- Modify: `backend/src/cellar/interface/routes/protocol_categories.py` (create body)
- Test: `backend/tests/api/test_protocol_category_start_like.py`
- Regenerate: orval

**Interfaces:**
- Produces: `CreateProtocolCategoryCommand.start_like_category_id: uuid.UUID | None = None`; create body field `start_like_category_id`.

- [ ] **Step 1: Write the failing API test**

```python
# backend/tests/api/test_protocol_category_start_like.py
"""A new category can start its protocols like an existing one: its forms are copied."""


async def test_new_category_copies_the_sources_forms(client):
    await client.post("/api/v1/protocol-categories/defaults")
    cats = (await client.get("/api/v1/protocol-categories")).json()
    growth = next(c for c in cats if c["label"] == "Growth inhibition")
    r = await client.post(
        "/api/v1/protocol-categories",
        json={"label": "Gametocytocidal activity", "start_like_category_id": growth["id"]},
    )
    assert r.status_code == 201, r.text
    new_id = r.json()["id"]
    forms = (await client.get("/api/v1/protocol-forms")).json()
    copied = sorted(f["name"] for f in forms if f["category_id"] == new_id)
    source = sorted(f["name"] for f in forms if f["category_id"] == growth["id"])
    assert copied == source and copied


async def test_unknown_source_category_is_404(client):
    r = await client.post(
        "/api/v1/protocol-categories",
        json={"label": "X", "start_like_category_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert r.status_code == 404, r.text
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api/test_protocol_category_start_like.py -q -p no:warnings`
Expected: FAIL (422 extra field or no forms copied).

- [ ] **Step 3: Implement**

`CreateProtocolCategoryCommand` gains `start_like_category_id: uuid.UUID | None = None`; `CreateProtocolCategory.__init__` gains keyword `form_repo: ProtocolFormRepository | None = None`. Inside the unit of work, before creating the category:

```python
            source = None
            if input.start_like_category_id is not None:
                source = await self._repo.find_by_id_in_workspace(
                    input.workspace_id, input.start_like_category_id
                )
                if source is None:
                    return Failure(NotFoundError("ProtocolCategory", str(input.start_like_category_id)))
```

after `await self._repo.save(category)`:

```python
            if source is not None and self._forms is not None:
                for f in await self._forms.find_by_workspace(input.workspace_id):
                    if f.category_id != source.id:
                        continue
                    await self._forms.save(
                        ProtocolForm.create(
                            workspace_id=input.workspace_id,
                            name=f.name,
                            description=f.description,
                            protocol_type=f.protocol_type,
                            category_id=category.id,
                            assay_format_from_target=f.assay_format_from_target,
                            is_default=f.is_default,
                            readout_templates=f.readout_templates,
                            condition_templates=f.condition_templates or None,
                            ontology_defaults=f.ontology_defaults or None,
                        )
                    )
```

Route body: `start_like_category_id: uuid.UUID | None = None`, passed to the command. DI: `CreateProtocolCategory(uow, repo, dispatcher, form_repo=SQLAlchemyProtocolFormRepository(uow))` (replace the `_category_cmd` use for this one class with a dedicated factory).

- [ ] **Step 4: Run the test**

Run: same as Step 2. Expected: PASS.

- [ ] **Step 5: Regenerate orval and commit**

```bash
cd frontend && pnpm generate:api   # revert version-stamp-only files
git commit -m "feat(protocol-categories): start a new category's protocols like an existing one

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar/application/workspace_config/protocol_categories.py backend/src/cellar/infrastructure/di/_workspace_config.py backend/src/cellar/interface/routes/protocol_categories.py backend/tests/api/test_protocol_category_start_like.py frontend/src/shared/lib/api
```

---

### Task 8: Siblings in one step (application)

**Files:**
- Modify: `backend/src/cellar/domain/screening_assay/repository.py` (`NameSibling`)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/protocol_repository.py` (`find_name_siblings`)
- Modify: `backend/src/cellar/domain/shared/protocol_naming.py` (`with_discriminator`, used by `render_protocol_name`)
- Modify: `backend/src/cellar/application/screening/manage_protocol.py` (`set_discriminator_and_rename`, `SetProtocolDiscriminator` uses it)
- Modify: `backend/src/cellar/application/screening/preview_protocol_name.py`
- Modify: `backend/src/cellar/application/screening/create_protocol.py`
- Test: `backend/tests/integration/test_create_protocol_siblings.py`

**Interfaces:**
- Produces:
  - `NameSibling(protocol_id, code, name, discriminator, status: str | None = None, is_locked: bool = False)`
  - `with_discriminator(base: str, discriminator: str) -> str`
  - `async set_discriminator_and_rename(names, protocol, value, *, reason: str | None, audit_reason: str, user_id) -> Result[Protocol, DomainError]`
  - `SiblingDiscriminator(protocol_id: uuid.UUID, discriminator: str, reason: str | None = None)` (in `create_protocol.py`)
  - `CreateProtocolCommand.sibling_discriminators: list[SiblingDiscriminator]`
  - `PreviewProtocolNameQuery.sibling_discriminators: dict[uuid.UUID, str]`
  - `NamePreview.sibling_renames: list[SiblingRename]` with `SiblingRename(protocol_id, code, name: str | None, error: str | None)`

- [ ] **Step 1: Write the failing integration tests**

```python
# backend/tests/integration/test_create_protocol_siblings.py
"""A new protocol that shares its base name tells its siblings apart in the same save."""

import uuid

from cellar.application.screening.create_protocol import (
    CreateProtocol,
    CreateProtocolCommand,
    SiblingDiscriminator,
)
from cellar.domain.screening_assay.enums import NameFlag, ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.shared.errors import DomainError
from cellar.domain.shared.ontology import OntologyTerm
from cellar.domain.workspace_config.protocol_category import ProtocolCategory
from cellar.infrastructure.di._screening import _name_service
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.protocol_category_repository import (  # noqa: E501
    SQLAlchemyProtocolCategoryRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from returns.result import Failure
from tests._auth import admin_auth

BASE = "M. tuberculosis growth inhibition"
MTB = {"term_id": "http://purl.bioontology.org/ontology/NCBITAXON/1773", "label": "Mycobacterium tuberculosis", "ontology_source": "NCBITAXON"}


class _NoEvents:
    async def dispatch_all(self, events):
        return None


def _auth(ws, user):
    return admin_auth(ws, user)


async def _seed_bare(session_factory, ws, user, *, status="draft", locked=False):
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await SQLAlchemyProtocolCategoryRepository(uow).save(ProtocolCategory.create(workspace_id=ws, label="Growth inhibition"))
        pid = uuid.uuid4()
        p = Protocol.create(
            workspace_id=ws, name=BASE, name_base=BASE, protocol_type=ProtocolType.WHOLE_CELL,
            category="Growth inhibition", created_by=user, code="PRT-00001",
            ontology_annotations={"organism": [OntologyTerm(**MTB)]},
            readout_definitions=[ReadoutDefinition(protocol_id=pid, name="MIC", data_type=ReadoutDataType.NUMERIC)],
        )
        if status == "active":
            p.publish()
        if locked:
            p.lock(locked_by=user, reason="frozen")
        await SQLAlchemyProtocolRepository(uow).save(p)
        await uow.commit()
    return p


def _uc(session_factory):
    uow = AsyncUnitOfWork(session_factory)
    return CreateProtocol(uow, SQLAlchemyProtocolRepository(uow), _NoEvents(), names=_name_service(uow))


def _cmd(ws, **kw):
    return CreateProtocolCommand(
        workspace_id=ws, protocol_type="whole_cell", category="Growth inhibition",
        discriminator="hypoxia", ontology_annotations={"organism": [MTB]},
        readout_definitions=[{"name": "MIC", "data_type": "numeric"}], **kw,
    )


async def _load(session_factory, ws, pid):
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        return await SQLAlchemyProtocolRepository(uow).find_by_id_in_workspace(ws, pid)


async def test_draft_sibling_is_renamed_in_the_same_save(session_factory, workspace_id, user_id):
    bare = await _seed_bare(session_factory, workspace_id, user_id)
    result = await _uc(session_factory)(
        _cmd(workspace_id, sibling_discriminators=[SiblingDiscriminator(protocol_id=bare.id, discriminator="MABA")]),
        auth=_auth(workspace_id, user_id),
    )
    assert result.unwrap().name == f"{BASE} [hypoxia]"
    sibling = await _load(session_factory, workspace_id, bare.id)
    assert sibling.name == f"{BASE} [MABA]" and sibling.name_flag is None
    assert any(a.label == BASE for a in sibling.aliases)  # "formerly"


async def test_blank_leaves_the_sibling_flagged(session_factory, workspace_id, user_id):
    bare = await _seed_bare(session_factory, workspace_id, user_id)
    (await _uc(session_factory)(_cmd(workspace_id), auth=_auth(workspace_id, user_id))).unwrap()
    assert (await _load(session_factory, workspace_id, bare.id)).name_flag == NameFlag.NEEDS_DISCRIMINATOR


async def test_published_sibling_needs_a_reason_and_nothing_is_saved_without_one(
    session_factory, workspace_id, user_id
):
    bare = await _seed_bare(session_factory, workspace_id, user_id, status="active")
    uc = _uc(session_factory)
    try:
        result = await uc(
            _cmd(workspace_id, sibling_discriminators=[SiblingDiscriminator(protocol_id=bare.id, discriminator="MABA")]),
            auth=_auth(workspace_id, user_id),
        )
        failed = isinstance(result, Failure)
    except DomainError:
        failed = True
    assert failed
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        names = [p.name for p in await SQLAlchemyProtocolRepository(uow).find_by_workspace(workspace_id)]
    assert names == [BASE]  # the new protocol was not saved either


async def test_published_sibling_with_reason_is_corrected(session_factory, workspace_id, user_id):
    bare = await _seed_bare(session_factory, workspace_id, user_id, status="active")
    (await _uc(session_factory)(
        _cmd(workspace_id, sibling_discriminators=[SiblingDiscriminator(protocol_id=bare.id, discriminator="MABA", reason="Distinguish from the new hypoxia assay")]),
        auth=_auth(workspace_id, user_id),
    )).unwrap()
    assert (await _load(session_factory, workspace_id, bare.id)).name == f"{BASE} [MABA]"


async def test_locked_sibling_is_refused_and_nothing_is_saved(session_factory, workspace_id, user_id):
    bare = await _seed_bare(session_factory, workspace_id, user_id, status="active", locked=True)
    try:
        result = await _uc(session_factory)(
            _cmd(workspace_id, sibling_discriminators=[SiblingDiscriminator(protocol_id=bare.id, discriminator="MABA", reason="x")]),
            auth=_auth(workspace_id, user_id),
        )
        failed = isinstance(result, Failure)
    except DomainError:
        failed = True
    assert failed
    assert (await _load(session_factory, workspace_id, bare.id)).name == BASE
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/test_create_protocol_siblings.py -q -p no:warnings`
Expected: FAIL with `ImportError: cannot import name 'SiblingDiscriminator'`.

- [ ] **Step 3: Implement**

`repository.py`: add `status: str | None = None` and `is_locked: bool = False` to `NameSibling`. `find_name_siblings`: also select `ProtocolModel.status, ProtocolModel.is_locked` and pass them.

`protocol_naming.py`:

```python
def with_discriminator(base: str, discriminator: str) -> str:
    """The name a protocol gets when its discriminator trails the base in brackets."""
    return f"{base} [{discriminator}]"
```

and in `render_protocol_name` replace `f"{base} [{discriminator}]"` with `with_discriminator(base, discriminator)`.

`manage_protocol.py`:

```python
async def set_discriminator_and_rename(
    names: ProtocolNameService,
    protocol: Protocol,
    value: str | None,
    *,
    reason: str | None,
    audit_reason: str,
    user_id: uuid.UUID | None,
) -> Result[Protocol, DomainError]:
    """The one way a discriminator changes: guard (draft, or a correction with a reason),
    then re-derive the name through the naming service."""
    cleaned = await names.clean_discriminator(protocol.workspace_id, value)
    protocol.set_discriminator(cleaned, reason=reason)
    renamed = await names.apply(
        protocol, reason=audit_reason, person=True, allow_incomplete=True, user_id=user_id
    )
    if isinstance(renamed, Failure):
        return renamed
    return Success(protocol)
```

`SetProtocolDiscriminator.__call__` body after loading the protocol becomes:

```python
            renamed = await set_discriminator_and_rename(
                self._names,
                protocol,
                input.discriminator,
                reason=input.reason,
                audit_reason=input.reason or "Discriminator changed",
                user_id=auth.user_id if auth else None,
            )
            if isinstance(renamed, Failure):
                return renamed
            await self._repo.save(protocol)
```

`create_protocol.py`:

```python
@dataclass(frozen=True)
class SiblingDiscriminator:
    protocol_id: uuid.UUID
    discriminator: str
    reason: str | None = None
```

`CreateProtocolCommand` gains `sibling_discriminators: list[SiblingDiscriminator] = field(default_factory=list)`. In `__call__`, replace `await self._names.flag_siblings(input.workspace_id, derivation)` with:

```python
            await self._names.flag_siblings(input.workspace_id, derivation)
            offered = {s.protocol_id for s in derivation.bare_siblings}
            for item in input.sibling_discriminators:
                if item.protocol_id not in offered:
                    return Failure(
                        ValidationError(
                            f"Protocol {item.protocol_id} does not share this protocol's name"
                        )
                    )
                sibling = await self._repo.find_by_id_in_workspace(
                    input.workspace_id, item.protocol_id
                )
                if sibling is None:
                    return Failure(NotFoundError("Protocol", str(item.protocol_id)))
                renamed = await set_discriminator_and_rename(
                    self._names,
                    sibling,
                    item.discriminator,
                    reason=item.reason,
                    audit_reason=correction_reason(
                        item.reason, f"Distinguished from {protocol.code}"
                    ),
                    user_id=auth.user_id if auth else None,
                )
                if isinstance(renamed, Failure):
                    return renamed
                await self._repo.save(sibling)
```

(Import `set_discriminator_and_rename` and `correction_reason` from `manage_protocol`. `AsyncUnitOfWork.__aexit__` closes the session without committing when the block returns early, so a `return Failure(...)` before `commit()` saves nothing; exceptions raised by `set_discriminator` (locked, retired, missing reason) roll back and propagate to the error handlers.)

`preview_protocol_name.py`: `PreviewProtocolNameQuery` gains `sibling_discriminators: dict[uuid.UUID, str] = field(default_factory=dict)`;

```python
@dataclass(frozen=True)
class SiblingRename:
    protocol_id: uuid.UUID
    code: str | None
    name: str | None
    error: str | None
```

`NamePreview` gains `sibling_renames: list[SiblingRename]`. After `d = await self._names.derive(...)` (inside the uow):

```python
            renames: list[SiblingRename] = []
            taken = {d.rendered.name.lower()} | {
                s.name.lower() for s in d.siblings if s.protocol_id not in input.sibling_discriminators
            }
            for s in d.bare_siblings:
                raw = input.sibling_discriminators.get(s.protocol_id)
                if not raw or not raw.strip():
                    continue
                try:
                    cleaned = await self._names.clean_discriminator(input.workspace_id, raw)
                except ValidationError as exc:
                    renames.append(SiblingRename(s.protocol_id, s.code, None, exc.message))
                    continue
                name = with_discriminator(d.rendered.base, cleaned)
                error = "Same name as another protocol" if name.lower() in taken else None
                taken.add(name.lower())
                renames.append(SiblingRename(s.protocol_id, s.code, name, error))
```

and pass `sibling_renames=renames` into `NamePreview(...)`.

- [ ] **Step 4: Run the tests plus the naming suites**

Run: `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/test_create_protocol_siblings.py tests/integration/test_protocol_name_siblings.py tests/unit/application/screening tests/unit/domain/shared/test_protocol_naming.py -q -p no:warnings`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(protocols): a new protocol tells its siblings apart in the same save

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar/domain/screening_assay/repository.py backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/protocol_repository.py backend/src/cellar/domain/shared/protocol_naming.py backend/src/cellar/application/screening/manage_protocol.py backend/src/cellar/application/screening/preview_protocol_name.py backend/src/cellar/application/screening/create_protocol.py backend/tests/integration/test_create_protocol_siblings.py
```

---

### Task 9: Nicknames at create

**Files:**
- Modify: `backend/src/cellar/application/screening/create_protocol.py`
- Test: `backend/tests/integration/test_create_protocol_siblings.py` (append)

**Interfaces:**
- Produces: `CreateProtocolCommand.nicknames: list[str] = field(default_factory=list)`.

- [ ] **Step 1: Write the failing test** (append)

```python
async def test_nicknames_are_added_at_create(session_factory, workspace_id, user_id):
    await _seed_bare(session_factory, workspace_id, user_id)
    created = (await _uc(session_factory)(
        _cmd(workspace_id, nicknames=["LORA", "  low oxygen recovery  "]),
        auth=_auth(workspace_id, user_id),
    )).unwrap()
    loaded = await _load(session_factory, workspace_id, created.id)
    assert {a.label for a in loaded.aliases if a.kind.value == "nickname"} == {"LORA", "low oxygen recovery"}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/test_create_protocol_siblings.py::test_nicknames_are_added_at_create -q -p no:warnings`
Expected: FAIL with `TypeError: ... unexpected keyword argument 'nicknames'`.

- [ ] **Step 3: Implement** — add the field; right after `protocol = Protocol.create(...)` and before `await self._repo.save(protocol)`:

```python
            for nickname in input.nicknames:
                protocol.add_nickname(nickname)
```

- [ ] **Step 4: Run it** — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(protocols): nicknames at create

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar/application/screening/create_protocol.py backend/tests/integration/test_create_protocol_siblings.py
```

---

### Task 10: Create and preview API carry siblings, nicknames, form

**Files:**
- Modify: `backend/src/cellar/interface/routes/protocols.py` (`CreateProtocolRequest`, the create route, `NamePreviewRequest`, `NameSiblingResponse`, `NamePreviewResponse`, the preview route)
- Test: `backend/tests/api/test_protocol_create_flow.py` (append)
- Regenerate: orval

**Interfaces:**
- Produces (API): `CreateProtocolRequest` gains `form_id: uuid.UUID | None = None` (if not added in Task 5), `sibling_discriminators: list[SiblingDiscriminatorRequest] = []` (`protocol_id`, `discriminator`, `reason?`), `nicknames: list[str] = []`. `NamePreviewRequest` gains `sibling_discriminators: list[SiblingDiscriminatorRequest] = []`. `NameSiblingResponse` gains `status: str | None`, `is_locked: bool`. `NamePreviewResponse` gains `sibling_renames: list[SiblingRenameResponse]` (`protocol_id`, `code`, `name`, `error`). orval types: `SiblingDiscriminatorRequest`, `SiblingRenameResponse`.

- [ ] **Step 1: Write the failing API tests** (append to `tests/api/test_protocol_create_flow.py`)

```python
MTB = {"term_id": "http://purl.bioontology.org/ontology/NCBITAXON/1773", "label": "Mycobacterium tuberculosis", "ontology_source": "NCBITAXON"}


def _growth(**kw):
    return {
        "category": "Growth inhibition",
        "protocol_type": "whole_cell",
        "readout_definitions": [{"name": "MIC", "data_type": "numeric"}],
        "ontology_annotations": {"organism": [MTB]},
        **kw,
    }


async def test_preview_and_create_rename_a_bare_sibling(client):
    await seed_protocol_categories(client)
    first = (await client.post("/api/v1/protocols", json=_growth())).json()
    preview = (await client.post(
        "/api/v1/protocols/name-preview",
        json={"category": "Growth inhibition", "ontology_annotations": {"organism": [MTB]}, "discriminator": "hypoxia",
              "sibling_discriminators": [{"protocol_id": first["id"], "discriminator": "MABA"}]},
    )).json()
    sib = preview["siblings"][0]
    assert sib["status"] == "draft" and sib["is_locked"] is False
    assert preview["sibling_renames"] == [{"protocol_id": first["id"], "code": first["code"], "name": "M. tuberculosis growth inhibition [MABA]", "error": None}]
    r = await client.post("/api/v1/protocols", json=_growth(
        discriminator="hypoxia", nicknames=["LORA"],
        sibling_discriminators=[{"protocol_id": first["id"], "discriminator": "MABA"}],
    ))
    assert r.status_code == 201, r.text
    assert (await client.get(f"/api/v1/protocols/{first['id']}")).json()["name"].endswith("[MABA]")


async def test_preview_reports_a_sibling_name_clash(client):
    await seed_protocol_categories(client)
    first = (await client.post("/api/v1/protocols", json=_growth())).json()
    preview = (await client.post(
        "/api/v1/protocols/name-preview",
        json={"category": "Growth inhibition", "ontology_annotations": {"organism": [MTB]}, "discriminator": "MABA",
              "sibling_discriminators": [{"protocol_id": first["id"], "discriminator": "MABA"}]},
    )).json()
    assert preview["sibling_renames"][0]["error"]
```

(Use the preview route's actual path — grep `name-preview`/`preview` in `routes/protocols.py`.)

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api/test_protocol_create_flow.py -q -p no:warnings`
Expected: FAIL (422 extra fields / missing keys).

- [ ] **Step 3: Implement the request/response models and pass-through**

```python
class SiblingDiscriminatorRequest(BaseModel):
    protocol_id: uuid.UUID
    discriminator: str
    reason: str | None = None


class SiblingRenameResponse(BaseModel):
    protocol_id: uuid.UUID
    code: str | None
    name: str | None
    error: str | None
```

Create route: build `sibling_discriminators=[SiblingDiscriminator(protocol_id=s.protocol_id, discriminator=s.discriminator, reason=s.reason) for s in body.sibling_discriminators]`, `nicknames=body.nicknames`, `form_id=body.form_id` into `CreateProtocolCommand`. Preview route: `sibling_discriminators={s.protocol_id: s.discriminator for s in body.sibling_discriminators}`; response: `sibling_renames=[SiblingRenameResponse(**asdict(r)) for r in p.sibling_renames]`; `NameSiblingResponse.from_domain` passes `status=s.status, is_locked=s.is_locked`.

- [ ] **Step 4: Run the API tests and the whole backend unit suite**

Run: `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api/test_protocol_create_flow.py -q -p no:warnings && uv run pytest tests/unit -q -p no:warnings --deselect tests/unit/application/export/renderers/test_pdf_renderer.py::test_pdf_renders_a_small_report`
Expected: PASS.

- [ ] **Step 5: Regenerate orval and commit**

```bash
cd frontend && pnpm generate:api   # revert version-stamp-only files
git commit -m "feat(protocols): create and preview API carry siblings, nicknames and the form

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar/interface/routes/protocols.py backend/tests/api/test_protocol_create_flow.py frontend/src/shared/lib/api
```

Announce to daikon before merge: the create and preview payloads gain optional fields only (additive).

---

### Task 11: Unit picker (frontend)

**Files:**
- Create: `frontend/src/shared/hooks/use-units.ts`
- Create: `frontend/src/shared/components/unit-picker.tsx`
- Test: `frontend/src/shared/components/unit-picker.test.tsx`

**Interfaces:**
- Consumes: orval `UnitSuggestionResponse` (Task 2).
- Produces: `useUnits(): UseQueryResult<UnitSuggestion[]>` with `export type UnitSuggestion = UnitSuggestionResponse`; `<UnitPicker value: string; onChange(v: string): void; placeholder?: string />`; `unitMatches(unit: string, query: string): boolean`.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/shared/components/unit-picker.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { UnitPicker, unitMatches } from "./unit-picker";

beforeAll(() => {
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = vi.fn();
});

vi.mock("@/shared/hooks/use-units", () => ({
  useUnits: () => ({
    data: [
      { unit: "µM", group: "Concentration" },
      { unit: "µg/mL", group: "Mass concentration" },
      { unit: "mg/kg", group: "Dose" },
    ],
  }),
}));

describe("unitMatches", () => {
  it("treats u and μ as µ and ignores case", () => {
    expect(unitMatches("µM", "uM")).toBe(true);
    expect(unitMatches("µM", "μm")).toBe(true);
    expect(unitMatches("µg/mL", "ug/ml")).toBe(true);
    expect(unitMatches("mg/kg", "uM")).toBe(false);
  });
});

describe("UnitPicker", () => {
  it("suggests the canonical unit for a variant spelling and keeps free text", () => {
    const onChange = vi.fn();
    const { rerender } = render(<UnitPicker value="" onChange={onChange} />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "uM" } });
    expect(onChange).toHaveBeenLastCalledWith("uM");
    rerender(<UnitPicker value="uM" onChange={onChange} />);
    fireEvent.focus(screen.getByRole("combobox"));
    fireEvent.click(screen.getByText("µM"));
    expect(onChange).toHaveBeenLastCalledWith("µM");
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && pnpm exec vitest run src/shared/components/unit-picker.test.tsx`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

```ts
// frontend/src/shared/hooks/use-units.ts
"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { UnitSuggestionResponse } from "@/shared/lib/api/model";
import { useQuery } from "@tanstack/react-query";

export type UnitSuggestion = UnitSuggestionResponse;

export function useUnits() {
  return useQuery({
    queryKey: ["units"],
    queryFn: () => customInstance<UnitSuggestion[]>({ url: `${API_V1}/units`, method: "GET" }),
    staleTime: Number.POSITIVE_INFINITY,
  });
}
```

```tsx
// frontend/src/shared/components/unit-picker.tsx
"use client";

import { SearchCombobox } from "@/shared/components/search-combobox";
import { type UnitSuggestion, useUnits } from "@/shared/hooks/use-units";
import { useState } from "react";

const fold = (s: string) => s.replace(/[uμ]/g, "µ").toLowerCase();

/** Spelling-tolerant match: "uM" finds µM, "ug/ml" finds µg/mL. The backend stores the canonical spelling. */
export function unitMatches(unit: string, query: string): boolean {
  return fold(unit).includes(fold(query.trim()));
}

interface Props {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}

export function UnitPicker({ value, onChange, placeholder = "Unit" }: Props) {
  const [open, setOpen] = useState(false);
  const { data } = useUnits();
  const items = (data ?? [])
    .filter((u) => !value || (unitMatches(u.unit, value) && u.unit !== value))
    .slice(0, 8);
  return (
    <SearchCombobox<UnitSuggestion>
      searchValue={value}
      onSearchChange={onChange}
      items={items}
      getItemKey={(u) => u.unit}
      renderItem={(u) => (
        <span className="flex w-full justify-between">
          <span>{u.unit}</span>
          <span className="text-xs text-muted-foreground">{u.group}</span>
        </span>
      )}
      onSelect={(u) => {
        onChange(u.unit);
        setOpen(false);
      }}
      open={open && items.length > 0}
      onOpenChange={setOpen}
      onInputFocus={() => setOpen(true)}
      placeholder={placeholder}
      inputClassName="h-9"
    />
  );
}
```

- [ ] **Step 4: Run it** — Expected: PASS. Run `pnpm exec tsc --noEmit -p .` — Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(units): unit picker with spelling-tolerant suggestions

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- frontend/src/shared/hooks/use-units.ts frontend/src/shared/components/unit-picker.tsx frontend/src/shared/components/unit-picker.test.tsx
```

---

### Task 12: Form values and form-apply rules (pure frontend modules)

**Files:**
- Create: `frontend/src/features/screening-assay/components/create-protocol/form-values.ts` (moved from `create-protocol-dialog.tsx`: `readoutSchema`, `conditionSchema`, `protocolSchema`, `ProtocolFormValues`, `defaultReadout`, `defaultCondition`, plus `DEFAULT_VALUES`)
- Create: `frontend/src/features/screening-assay/lib/protocol-form-apply.ts`
- Modify: `frontend/src/features/screening-assay/components/create-protocol-dialog.tsx` (import from `form-values.ts`)
- Test: `frontend/src/features/screening-assay/lib/protocol-form-apply.test.ts`

**Interfaces:**
- Consumes: orval `ProtocolFormResponse` with typed templates (Task 4), `ProtocolForm` alias in `use-protocol-forms.ts`.
- Produces:
  - `formsForCategory(forms: ProtocolForm[], categoryId: string | null): { own: ProtocolForm[]; generic: ProtocolForm[] }`
  - `pickFormForCategory(forms: ProtocolForm[], categoryId: string | null): ProtocolForm | null`
  - `readoutsFromForm(form: ProtocolForm): ProtocolFormValues["readouts"]` (carries pick list, calculated, formula, dose-response config into the `dr_*` fields)
  - `conditionsFromForm(form: ProtocolForm): ProtocolFormValues["conditions"]`
  - `mergeFacetDefaults(current: Record<string, OntologyTerm[]>, form: ProtocolForm): Record<string, OntologyTerm[]>` (fills only empty slots; skips `assay_format` when `form.assay_format_from_target`)

- [ ] **Step 1: Move the schema and defaults into `form-values.ts`** — cut the "Zod schemas" and "Default factories" sections (from `const readoutSchema` through the end of `defaultCondition`) out of `create-protocol-dialog.tsx` into `create-protocol/form-values.ts`, `export` each symbol, and add:

```ts
export const DEFAULT_VALUES: ProtocolFormValues = {
  protocol_type: "biochemical",
  discriminator: "",
  target_ids: [],
  category: "",
  description: "",
  dose_unit: "uM",
  readouts: [defaultReadout(1)],
  conditions: [],
};
```

In the dialog, import them and replace the two inline default-value objects (`useForm` defaults and `resetForm`) with `DEFAULT_VALUES`. Run `pnpm exec vitest run src/features/screening-assay` — Expected: PASS (pure move).

- [ ] **Step 2: Write the failing tests**

```ts
// frontend/src/features/screening-assay/lib/protocol-form-apply.test.ts
import { describe, expect, it } from "vitest";
import type { ProtocolForm } from "@/features/workspace-config/hooks/use-protocol-forms";
import {
  formsForCategory,
  mergeFacetDefaults,
  pickFormForCategory,
  readoutsFromForm,
} from "./protocol-form-apply";

const form = (over: Partial<ProtocolForm>): ProtocolForm =>
  ({
    id: crypto.randomUUID(),
    workspace_id: "w",
    name: "f",
    is_default: false,
    category_id: null,
    assay_format_from_target: false,
    readout_templates: [{ name: "Signal", data_type: "numeric", aggregation: "none", normalization: "none", is_calculated: false }],
    condition_templates: null,
    ontology_defaults: null,
    version: 1,
    ...over,
  }) as ProtocolForm;

const BAO_BIOCHEM = { term_id: "bao#BAO_0000217", label: "biochemical format", ontology_source: "BAO", uri: null };
const MTB = { term_id: "ncbi#1773", label: "Mycobacterium tuberculosis", ontology_source: "NCBITAXON", uri: null };

describe("pickFormForCategory", () => {
  it("prefers the category's default, then its only form, then the generic default", () => {
    const a = form({ category_id: "c1" });
    const b = form({ category_id: "c1", is_default: true });
    const g = form({ is_default: true });
    expect(pickFormForCategory([a, b, g], "c1")).toBe(b);
    expect(pickFormForCategory([a, g], "c1")).toBe(a);
    expect(pickFormForCategory([g], "c2")).toBe(g);
  });

  it("asks (null) when the category has several forms and no default", () => {
    const a = form({ category_id: "c1" });
    const b = form({ category_id: "c1" });
    expect(pickFormForCategory([a, b, form({ is_default: true })], "c1")).toBeNull();
    expect(formsForCategory([a, b], "c1").own).toHaveLength(2);
  });
});

describe("readoutsFromForm", () => {
  it("carries every template field, including dose-response config", () => {
    const f = form({
      readout_templates: [
        { name: "Signal", data_type: "numeric", normalization: "percent_inhibition", aggregation: "none", is_calculated: false },
        {
          name: "IC50",
          data_type: "dose_response",
          unit: "µM",
          aggregation: "none",
          normalization: "none",
          is_calculated: false,
          dose_response_config: { curve_type: "ic50", y_readout_name: "Signal", hill_slope_constraint: "unconstrained" },
        },
      ],
    });
    const [signal, ic50] = readoutsFromForm(f);
    expect(signal.normalizations).toEqual(["percent_inhibition"]);
    expect(ic50.unit).toBe("µM");
    expect(ic50.dr_curve_type).toBe("ic50");
    expect(ic50.dr_y_readout).toBe("Signal");
  });
});

describe("mergeFacetDefaults", () => {
  it("fills empty slots only and never replaces a chemist's pick", () => {
    const f = form({ ontology_defaults: [{ slot_name: "organism", terms: [MTB] }, { slot_name: "assay_format", terms: [BAO_BIOCHEM] }] });
    const other = { ...MTB, term_id: "ncbi#5833", label: "Plasmodium falciparum" };
    expect(mergeFacetDefaults({ organism: [other] }, f)).toEqual({ organism: [other], assay_format: [BAO_BIOCHEM] });
  });

  it("leaves the assay format to the backend when the form follows the target", () => {
    const f = form({ assay_format_from_target: true, ontology_defaults: [{ slot_name: "assay_format", terms: [BAO_BIOCHEM] }] });
    expect(mergeFacetDefaults({}, f)).toEqual({});
  });
});
```

- [ ] **Step 3: Run them to verify they fail**

Run: `cd frontend && pnpm exec vitest run src/features/screening-assay/lib/protocol-form-apply.test.ts`
Expected: FAIL (module not found).

- [ ] **Step 4: Implement**

```ts
// frontend/src/features/screening-assay/lib/protocol-form-apply.ts
import type { ProtocolForm } from "@/features/workspace-config/hooks/use-protocol-forms";
import type { OntologyTerm } from "@/shared/components/ontology-search-input";
import {
  type ProtocolFormValues,
  defaultCondition,
  defaultReadout,
} from "../components/create-protocol/form-values";
import type { PickListValue, ReadoutNormalization } from "../types";
import { WELL_CONC_X } from "./readout-constants";

export function formsForCategory(forms: ProtocolForm[], categoryId: string | null) {
  return {
    own: categoryId ? forms.filter((f) => f.category_id === categoryId) : [],
    generic: forms.filter((f) => !f.category_id),
  };
}

/** The category's default, its only form, or (when it has none) the generic default; null means "ask". */
export function pickFormForCategory(forms: ProtocolForm[], categoryId: string | null): ProtocolForm | null {
  const { own, generic } = formsForCategory(forms, categoryId);
  const ownDefault = own.find((f) => f.is_default);
  if (ownDefault) return ownDefault;
  if (own.length === 1) return own[0];
  if (own.length === 0) return generic.find((f) => f.is_default) ?? null;
  return null;
}

export function readoutsFromForm(form: ProtocolForm): ProtocolFormValues["readouts"] {
  return form.readout_templates.map((tpl, i) => {
    const norm = tpl.normalization && tpl.normalization !== "none" ? [tpl.normalization as ReadoutNormalization] : [];
    const dr = tpl.dose_response_config as Record<string, unknown> | null | undefined;
    return {
      ...defaultReadout(i + 1),
      name: tpl.name,
      data_type: tpl.data_type,
      unit: tpl.unit ?? "",
      aggregation: tpl.aggregation ?? "none",
      normalizations: norm,
      is_calculated: tpl.is_calculated ?? false,
      calculation_formula: tpl.calculation_formula ?? "",
      pick_list_values: ((tpl.pick_list_values ?? []) as PickListValue[]).map((v) =>
        typeof v === "string" ? { label: v } : v,
      ),
      ...(dr
        ? {
            dr_curve_type: String(dr.curve_type ?? "ic50"),
            dr_x_readout: (dr.x_readout_name as string | null) ?? WELL_CONC_X,
            dr_y_readout: String(dr.y_readout_name ?? ""),
            dr_hill_constraint: String(dr.hill_slope_constraint ?? "unconstrained"),
            dr_normalization_scope: String(dr.normalization_scope ?? "per_plate"),
            dr_activity_threshold: dr.activity_threshold != null ? String(dr.activity_threshold) : "",
          }
        : {}),
    };
  });
}

export function conditionsFromForm(form: ProtocolForm): ProtocolFormValues["conditions"] {
  return (form.condition_templates ?? []).map((tpl) => ({
    ...defaultCondition(),
    name: tpl.name,
    data_type: tpl.data_type,
    unit: tpl.unit ?? "",
  }));
}

export function mergeFacetDefaults(
  current: Record<string, OntologyTerm[]>,
  form: ProtocolForm,
): Record<string, OntologyTerm[]> {
  const next = { ...current };
  for (const d of form.ontology_defaults ?? []) {
    if (d.slot_name === "assay_format" && form.assay_format_from_target) continue;
    if ((next[d.slot_name] ?? []).length > 0) continue;
    next[d.slot_name] = (d.terms ?? []).map((t) => ({
      term_id: String(t.term_id ?? ""),
      label: String(t.label ?? ""),
      ontology_source: String(t.ontology_source ?? ""),
      uri: (t.uri as string | null) ?? null,
    }));
  }
  return next;
}
```

- [ ] **Step 5: Run the tests, typecheck, commit**

Run: `cd frontend && pnpm exec vitest run src/features/screening-assay && pnpm exec tsc --noEmit -p .`
Expected: PASS, exit 0.

```bash
git commit -m "refactor(protocols): form values and form-apply rules as tested modules

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- frontend/src/features/screening-assay/components/create-protocol/form-values.ts frontend/src/features/screening-assay/lib/protocol-form-apply.ts frontend/src/features/screening-assay/lib/protocol-form-apply.test.ts frontend/src/features/screening-assay/components/create-protocol-dialog.tsx
```

---

### Task 13: Category-first dialog

**Files:**
- Create: `frontend/src/features/screening-assay/components/create-protocol/required-facts.tsx`
- Create: `frontend/src/features/screening-assay/components/create-protocol/starts-from.tsx`
- Create: `frontend/src/features/screening-assay/components/create-protocol/readout-row.tsx`
- Create: `frontend/src/features/screening-assay/components/create-protocol/sibling-discriminators.tsx`
- Create: `frontend/src/features/screening-assay/components/create-protocol/nickname-input.tsx`
- Modify: `frontend/src/features/screening-assay/components/create-protocol-dialog.tsx`
- Modify: `frontend/src/features/screening-assay/components/similar-protocols-panel.tsx`
- Modify: `frontend/src/features/screening-assay/hooks/use-protocol-name-preview.ts` (send `sibling_discriminators`)
- Modify: `frontend/src/features/screening-assay/components/protocol-name-preview.tsx` (`isPreviewSavable` also checks `sibling_renames` errors)
- Test: `frontend/src/features/screening-assay/components/create-protocol-dialog.test.tsx`, `similar-protocols-panel.test.tsx`, `create-protocol/sibling-discriminators.test.tsx`

**Interfaces:**
- Consumes: Tasks 10-12 (`sibling_renames`, `status`, `is_locked`, `form_id`, `nicknames`, `UnitPicker`, form-apply helpers, `useRequiredNameSlots`).
- Produces (props):
  - `RequiredFacts({ needs: Set<string>; followsTarget: boolean; facetSlots: ProtocolFacetSlot[]; annotations; onAnnotations; targetIds: string[]; onTargetIds })` — renders exactly the pickers the pattern needs; returns the slot names it rendered via `requiredFactSlots(needs, followsTarget): string[]` (exported, `"target"` or a facet slot name; `matrix` → `"assay_format"`).
  - `StartsFrom({ forms: ProtocolForm[]; selectedId: string | null; onPick(form: ProtocolForm | null) })`
  - `ReadoutRow({ form: UseFormReturn<ProtocolFormValues>; index: number; readouts: ProtocolFormValues["readouts"]; crossProtocols; canRemove: boolean; onRemove(): void })`
  - `SiblingDiscriminators({ siblings: NameSiblingResponse[]; renames: SiblingRenameResponse[]; values: Record<string, { discriminator: string; reason: string }>; newName: string; onChange(values) })`
  - `NicknameInput({ value: string[]; onChange(v: string[]) })`

- [ ] **Step 1: Write the failing tests** (replace the dialog test's three label tests with order/behaviour tests; keep the existing ones that still apply)

```tsx
// append to create-protocol-dialog.test.tsx (mocks: extend useProtocolForms to return forms; useProtocolCategories to include ids)
it("puts category first and the facts its pattern needs right under it", () => {
  render(<CreateProtocolDialog open onOpenChange={() => {}} />);
  const labels = screen.getAllByText((_, el) => el?.tagName === "LABEL").map((l) => l.textContent);
  expect(labels[0]).toBe("Category");
});

it("hides Dose unit until a readout fits dose-response curves", () => {
  render(<CreateProtocolDialog open onOpenChange={() => {}} />);
  expect(screen.queryByText("Dose unit")).not.toBeInTheDocument();
});

it("asks before replacing readouts the chemist edited", async () => {
  // render, type into the first readout name, pick a category with a default form,
  // expect the confirm "Replace your readouts with the form's?" to appear
});
```

Write the third test concretely against the mocks used in the file: set `useProtocolForms` to return `[{ id: "f1", category_id: "c-gi", is_default: true, name: "MIC", readout_templates: [{ name: "MIC", data_type: "numeric", unit: "µM", aggregation: "none", normalization: "none", is_calculated: false }], ... }]` and `useProtocolCategories` to include `{ id: "c-gi", label: "Growth inhibition", name_pattern: "{organism} growth inhibition" }`; type "Signal" into the readout name input (`getByPlaceholderText("e.g., % Inhibition")`), select the category through `ProtocolCategoryInput` (mocked to a `<select>` that calls `onChange`), then `expect(screen.getByText(/Replace your readouts/)).toBeInTheDocument()`.

```tsx
// frontend/src/features/screening-assay/components/create-protocol/sibling-discriminators.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SiblingDiscriminators } from "./sibling-discriminators";

const sib = (over = {}) => ({ protocol_id: "p1", code: "PRT-00001", name: "Microsomal stability", discriminator: null, status: "draft", is_locked: false, ...over });

describe("SiblingDiscriminators", () => {
  it("offers a field per bare, editable sibling and shows its new name", () => {
    const onChange = vi.fn();
    render(
      <SiblingDiscriminators
        siblings={[sib()]}
        renames={[{ protocol_id: "p1", code: "PRT-00001", name: "Microsomal stability [mouse]", error: null }]}
        values={{ p1: { discriminator: "mouse", reason: "" } }}
        newName="Microsomal stability [human]"
        onChange={onChange}
      />,
    );
    expect(screen.getByText(/PRT-00001 becomes/)).toBeInTheDocument();
    expect(screen.getByText("Microsomal stability [mouse]")).toBeInTheDocument();
  });

  it("asks for a reason on a published sibling and prefills it", () => {
    render(<SiblingDiscriminators siblings={[sib({ status: "active" })]} renames={[]} values={{}} newName="X [human]" onChange={vi.fn()} />);
    expect(screen.getByDisplayValue(/Distinguish from the new protocol/)).toBeInTheDocument();
  });

  it("does not offer locked or retired siblings and says they stay flagged", () => {
    render(<SiblingDiscriminators siblings={[sib({ is_locked: true })]} renames={[]} values={{}} newName="X" onChange={vi.fn()} />);
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getByText(/locked/i)).toBeInTheDocument();
  });
});
```

```tsx
// append to similar-protocols-panel.test.tsx
it("collapses non-run suggestions to one line", () => {
  data.mockReturnValueOnce([{ ...match, is_run_candidate: false }]);
  render(<SimilarProtocolsPanel draft={{ name: "RNAP core IC50" }} onLogRun={vi.fn()} />);
  expect(screen.getByRole("button", { name: /1 similar protocol/ })).toBeInTheDocument();
  expect(screen.queryByText("RNAP core IC50")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /1 similar protocol/ }));
  expect(screen.getByText("RNAP core IC50")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && pnpm exec vitest run src/features/screening-assay/components`
Expected: FAIL on the new tests.

- [ ] **Step 3: Build the components**

`sibling-discriminators.tsx`:

```tsx
"use client";

import { Input } from "@/shared/components/ui/input";
import type { NameSiblingResponse, SiblingRenameResponse } from "@/shared/lib/api/model";

export type SiblingValues = Record<string, { discriminator: string; reason: string }>;

const offered = (s: NameSiblingResponse) => !s.discriminator && !s.is_locked && s.status !== "retired";

export function SiblingDiscriminators({
  siblings,
  renames,
  values,
  newName,
  onChange,
}: {
  siblings: NameSiblingResponse[];
  renames: SiblingRenameResponse[];
  values: SiblingValues;
  newName: string;
  onChange: (v: SiblingValues) => void;
}) {
  const bare = siblings.filter((s) => !s.discriminator);
  if (bare.length === 0) return null;
  return (
    <div className="space-y-2 rounded-md border border-amber-300/60 bg-amber-50/60 p-3 text-sm">
      {bare.map((s) => {
        const v = values[s.protocol_id] ?? { discriminator: "", reason: "" };
        const rename = renames.find((r) => r.protocol_id === s.protocol_id);
        if (!offered(s)) {
          return (
            <p key={s.protocol_id} className="text-amber-900">
              {s.code} ({s.status === "retired" ? "retired" : "locked"}) keeps its name and is flagged for its owner.
            </p>
          );
        }
        const reason = v.reason || `Distinguish from the new protocol (${newName})`;
        return (
          <div key={s.protocol_id} className="grid gap-1">
            <label className="flex items-center gap-2">
              <span className="shrink-0 text-amber-900">{s.code} becomes {s.name} [</span>
              <Input
                aria-label={`Discriminator for ${s.code}`}
                className="h-8"
                value={v.discriminator}
                onChange={(e) =>
                  onChange({ ...values, [s.protocol_id]: { discriminator: e.target.value, reason: v.reason } })
                }
              />
              <span className="text-amber-900">]</span>
            </label>
            {rename?.name && !rename.error && <span className="text-xs text-muted-foreground">{rename.name}</span>}
            {rename?.error && <span className="text-xs text-destructive">{rename.error}</span>}
            {s.status === "active" && (
              <Input
                aria-label={`Correction reason for ${s.code}`}
                className="h-8"
                value={reason}
                onChange={(e) =>
                  onChange({ ...values, [s.protocol_id]: { discriminator: v.discriminator, reason: e.target.value } })
                }
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
```

`nickname-input.tsx`: an `Input` that adds the trimmed text on Enter (`e.preventDefault()`), ignores duplicates (case-insensitive), and renders each nickname as a `Badge` with an `×` button that removes it; label "Also known as".

`starts-from.tsx`: renders nothing when `forms.length === 0`; otherwise a row of `Button`s (`variant={f.id === selectedId ? "default" : "outline"}`, `size="sm"`) one per form plus a "Blank" button (`onPick(null)`); label "Starts from".

`required-facts.tsx`:

```tsx
export function requiredFactSlots(needs: Set<string>, followsTarget: boolean): string[] {
  const out: string[] = [];
  if (needs.has("target") || (needs.has("subject") && followsTarget)) out.push("target");
  if (needs.has("organism") || (needs.has("subject") && !followsTarget)) out.push("organism");
  if (needs.has("cell_line")) out.push("cell_line");
  if (needs.has("matrix")) out.push("assay_format");
  return out;
}
```

and the component renders, for each slot from `requiredFactSlots`, either `TargetMultiSelect` (label "Target") or the slot's `OntologySearchInput` (label from `facetSlots.find(s => s.name === slot)?.label`) with the same props the dialog passes today.

`readout-row.tsx`: move the body of the readout `<Card key={field.id}>…</Card>` from the dialog into `ReadoutRow`, changing only references (`form.control`, `readoutValues` → `readouts`, `removeReadout(index)` → `onRemove()`). Show by default: Name, a `UnitPicker` for Unit (replacing the free-text `Input`), and a small data-type label; wrap Data Type select, Aggregation, Normalization, Calculated/Formula, Pick list and the whole dose-response block in a `Collapsible` opened by a "More options" `CollapsibleTrigger` (open by default when the readout's data type is `pick_list` or `dose_response` and its required fields are empty).

`similar-protocols-panel.tsx`: keep the run-candidate box as is. For the other matches, when there is no run candidate, render a `Button variant="ghost" size="sm"` labelled `` `${n} similar protocol${n === 1 ? "" : "s"}` `` with a chevron, toggling the list; with a run candidate, keep listing the others under it as today.

`use-protocol-name-preview.ts`: add `sibling_discriminators?: { protocol_id: string; discriminator: string }[]` to the input and send it. `isPreviewSavable`: also `&& !(p.sibling_renames ?? []).some((r) => r.error)`.

- [ ] **Step 4: Recompose the dialog**

In `create-protocol-dialog.tsx`, render in this order inside the existing `DialogContent`:

1. `Category` (`ProtocolCategoryInput`, `autoFocus` on the trigger if the component forwards it; otherwise focus via a ref on open).
2. `<RequiredFacts …/>` with `needs = useRequiredNameSlots(categoryValue)` and `followsTarget = selectedForm?.assay_format_from_target ?? false`.
3. `<ProtocolNamePreview preview={preview.data} isFetching={preview.isFetching} />`.
4. Discriminator field, shown only when `needs.has("discriminator") || (preview.data?.siblings.length ?? 0) > 0 || showDiscriminator`; otherwise a `Button variant="link"` "+ method or condition" that sets `showDiscriminator`.
5. `<SiblingDiscriminators siblings={preview.data?.siblings ?? []} renames={preview.data?.sibling_renames ?? []} values={siblingValues} newName={preview.data?.name ?? ""} onChange={setSiblingValues} />`.
6. `<StartsFrom forms={[...own, ...generic]} selectedId={selectedForm?.id ?? null} onPick={applyPickedForm} />` (from `formsForCategory`).
7. Readouts: `readoutFields.map((field, index) => <ReadoutRow key={field.id} … />)` and "+ Add readout".
8. `<NicknameInput value={nicknames} onChange={setNicknames} />`.
9. `Collapsible` "More details": Type select; Assay format (the `assay_format` facet input, with helper text "Follows the target" when `followsTarget` and no explicit pick); every facet slot not in `requiredFactSlots(...)`; Targets when not required; Description; Project; Conditions (with `UnitPicker` for condition units); Dose unit select, rendered only when `readoutValues.some((r) => r.data_type === "dose_response")`.
10. `<SimilarProtocolsPanel …/>` (as today).
11. Footer: when `form.formState.isDirty` on open, "Draft kept" text and a "Clear" button (`resetForm()`), then the Create button.

Category change handling (replace the old Form Template select and `applyForm`):

```tsx
const { data: categories } = useProtocolCategories();
const categoryId = categories?.find((c) => c.label === categoryValue)?.id ?? null;
const [selectedForm, setSelectedForm] = useState<ProtocolForm | null>(null);
const [appliedReadouts, setAppliedReadouts] = useState(JSON.stringify(DEFAULT_VALUES.readouts));
const [pendingForm, setPendingForm] = useState<ProtocolForm | null>(null);

const applyPickedForm = (f: ProtocolForm | null) => {
  setSelectedForm(f);
  if (!f) return;
  const edited = JSON.stringify(form.getValues("readouts")) !== appliedReadouts;
  if (edited) {
    setPendingForm(f); // opens the AlertDialog "Replace your readouts with the form's?"
    return;
  }
  applyFormNow(f);
};

const applyFormNow = (f: ProtocolForm) => {
  if (f.protocol_type) form.setValue("protocol_type", f.protocol_type);
  const readouts = readoutsFromForm(f);
  if (readouts.length > 0) {
    form.setValue("readouts", readouts);
    setAppliedReadouts(JSON.stringify(readouts));
  }
  const conditions = conditionsFromForm(f);
  if (conditions.length > 0) form.setValue("conditions", conditions);
  setOntologyAnnotations((prev) => mergeFacetDefaults(prev, f));
};

useEffect(() => {
  if (!categoryId || prefill) return;
  applyPickedForm(pickFormForCategory(protocolForms ?? [], categoryId));
  // eslint-disable-next-line react-hooks/exhaustive-deps -- re-run on category change only
}, [categoryId]);
```

The confirm uses the existing `AlertDialog` primitive: "Replace your readouts with the form's?" with "Keep mine" (`setPendingForm(null)`) and "Replace" (`applyFormNow(pendingForm); setPendingForm(null)`).

Submit payload additions: `form_id: selectedForm?.id ?? null`, `nicknames`, `sibling_discriminators: Object.entries(siblingValues).filter(([, v]) => v.discriminator.trim()).map(([protocol_id, v]) => ({ protocol_id, discriminator: v.discriminator.trim(), reason: siblingIsActive(protocol_id) ? (v.reason || defaultReason) : null }))`. Preview input adds the same `sibling_discriminators` (without reasons). `resetForm` also clears `selectedForm`, `nicknames`, `siblingValues`, `showDiscriminator`, `appliedReadouts`.

Keep the `prefill` effect (new protocol from an existing one) as is, and set `appliedReadouts` from its readouts.

- [ ] **Step 5: Run the screening-assay suite, lint, typecheck**

Run: `cd frontend && pnpm exec vitest run src/features/screening-assay src/shared && pnpm lint; echo $? && pnpm exec tsc --noEmit -p .`
Expected: PASS, lint exit 0, tsc exit 0. Update tests that asserted the old Form Template select or the old field order to the new behaviour (do not delete coverage).

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(protocols): category-first create dialog with forms, siblings and nicknames

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- frontend/src/features/screening-assay
```

---

### Task 14: Protocol Forms admin

**Files:**
- Modify: `frontend/src/features/workspace-config/components/protocol-form-admin.tsx`
- Modify: `frontend/src/features/workspace-config/hooks/use-protocol-forms.ts` (`useSeedDefaultProtocolForms`)
- Test: `frontend/src/features/workspace-config/components/protocol-form-admin.test.tsx`

**Interfaces:**
- Consumes: Tasks 4, 6, 11 (typed templates, `category_id`, `assay_format_from_target`, `POST /protocol-forms/defaults`, `UnitPicker`).
- Produces: `useSeedDefaultProtocolForms()` mutation (invalidates `["protocol-forms"]`).

- [ ] **Step 1: Write the failing tests**

```tsx
// frontend/src/features/workspace-config/components/protocol-form-admin.test.tsx
// Mocks: useProtocolForms returns one form with a dose-response readout template:
//   readout_templates: [{ name: "Signal", data_type: "numeric", normalization: "percent_inhibition", ... },
//                       { name: "IC50", data_type: "dose_response", unit: "µM", dose_response_config: { curve_type: "ic50", y_readout_name: "Signal" }, ... }]
//   category_id: "c1"; useProtocolCategories returns [{ id: "c1", label: "Enzyme inhibition", name_pattern: "{target} inhibition" }]
//   useUpdateProtocolForm returns { mutateAsync: update, isPending: false }
it("keeps template fields it does not show when saving an edit", async () => {
  render(<ProtocolFormAdmin />);
  fireEvent.click(screen.getByRole("button", { name: /edit/i }));
  fireEvent.click(screen.getByRole("button", { name: /save/i }));
  await waitFor(() => expect(update).toHaveBeenCalled());
  const sent = update.mock.calls[0][0];
  expect(sent.readout_templates[1].dose_response_config).toEqual({ curve_type: "ic50", y_readout_name: "Signal" });
  expect(sent.category_id).toBe("c1");
  expect(sent.ontology_defaults).not.toBeNull();
});

it("groups forms under their category", () => {
  render(<ProtocolFormAdmin />);
  expect(screen.getByText("Enzyme inhibition")).toBeInTheDocument();
});
```

Write the mocks concretely in the file (mirror the mocking style of `create-protocol-dialog.test.tsx`).

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && pnpm exec vitest run src/features/workspace-config/components/protocol-form-admin.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement**

- `ReadoutRow` / `ConditionRow` gain `_source?: ProtocolFormReadoutTemplate` / `ProtocolFormConditionTemplate`; when loading an existing form, set `_source` to the template; on save, send `{ ..._source, name, data_type, unit, aggregation, normalization }` (and `{ ..._source, name, data_type, unit }` for conditions) so unshown fields survive.
- Form state gains `categoryId: string | null` (a `Select` of categories plus "Any category" for generic), `assayFormatFromTarget: boolean` (a `Switch` "Assay format follows the target"), and `ontologyDefaults: Record<string, OntologyTerm[]>` edited with one `OntologySearchInput` per `useProtocolFacetSlots()` slot; send `ontology_defaults` as `Object.entries(...).filter(([, t]) => t.length).map(([slot_name, terms]) => ({ slot_name, terms }))` or `null` when empty (never a blind `null`).
- Unit cells use `UnitPicker`.
- The "Default" switch label becomes "Default for this category".
- `FormTable` groups rows under category headings (sorted by category label, "Any category" last).
- Header gains an "Add default forms" button calling `useSeedDefaultProtocolForms().mutate()`.

```ts
// use-protocol-forms.ts
export function useSeedDefaultProtocolForms() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => customInstance<ProtocolForm[]>({ url: `${API_V1}/protocol-forms/defaults`, method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["protocol-forms"] }),
  });
}
```

- [ ] **Step 4: Run tests, lint, typecheck** — same commands as Task 13 Step 5 over `src/features/workspace-config`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(protocol-forms): admin by category, facet defaults, units; edits keep unshown fields

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- frontend/src/features/workspace-config
```

---

### Task 15: "Start protocols like" in Add category

**Files:**
- Modify: `frontend/src/features/workspace-config/components/protocol-category-admin.tsx` (`CategoryDialog`)
- Test: `frontend/src/features/workspace-config/components/protocol-category-admin.test.tsx` (append)

**Interfaces:**
- Consumes: Task 7 (`start_like_category_id` on the create body, regenerated in orval).

- [ ] **Step 1: Write the failing test** (append)

```tsx
it("sends the category new protocols should start like", async () => {
  // open "Add category", type a label, pick "Growth inhibition" under "Start protocols like", save
  // expect the create mutation to receive { label: "Gametocytocidal activity", start_like_category_id: "<growth id>" }
});
```

Write it concretely with the existing mocks in that test file (it already mocks the category hooks; add a category list containing Growth inhibition with an id and a forms list where that category has a form).

- [ ] **Step 2: Run it to verify it fails** — `pnpm exec vitest run src/features/workspace-config/components/protocol-category-admin.test.tsx`. Expected: FAIL.

- [ ] **Step 3: Implement** — in create mode only, add a `SearchableSelect` labelled "Start protocols like (optional)" listing categories that have at least one form (`useProtocolForms()` → `category_id` set), value → `start_like_category_id` in the create payload; helper text "Copies that category's forms: type, readouts, units, assay format."

- [ ] **Step 4: Run tests, lint, typecheck** — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(protocol-categories): new categories can start protocols like an existing one

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- frontend/src/features/workspace-config/components/protocol-category-admin.tsx frontend/src/features/workspace-config/components/protocol-category-admin.test.tsx
```

---

### Task 16: Verification and walk

**Files:**
- Modify: `docs/superpowers/reports/2026-10-08-chembl-naming-fit-test.md` (append "Create flow walk" results)
- Modify: `docs/implementation-status.md` if it tracks this sub-project (check `git ls-files docs/implementation-status.md`; docs/ is mostly gitignored)

- [ ] **Step 1: Full suites**

Run:
```bash
cd backend && uv run pytest tests/unit -q -p no:warnings --deselect tests/unit/application/export/renderers/test_pdf_renderer.py::test_pdf_renders_a_small_report
DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration tests/api -q -p no:warnings
uv run ruff check src tests && uv run ruff format --check src
cd ../frontend && pnpm exec vitest run && pnpm lint; echo "lint exit $?" && pnpm exec tsc --noEmit -p .
```
Expected: all green except the known PDF test and pre-existing failures listed in `docs/backlog/preexisting-test-lint-failures-main.md` (name any others in the report, do not fix inline).

- [ ] **Step 2: Migrations up and down**

Run: `cd backend && uv run alembic downgrade 087_campaign_name_snapshot_width && uv run alembic upgrade head` (root `.env` exported). Expected: both succeed.

- [ ] **Step 3: Browser walk** (verify skill / Claude-in-Chrome; the user signs in)

In a scratch workspace: Admin → Protocol Categories → "Add default categories" (forms appear in Admin → Protocol Forms, grouped). Then create, counting interactions per protocol: one protocol per shipped category; a family of three siblings in one category (e.g. three growth-inhibition assays differing by method), setting the first's discriminator from the second's dialog; an Enzyme inhibition protocol with a single-protein target (assay format under More details reads single protein format after create) and one with a complex target (protein complex format); a readout unit typed as `uM` (stored `µM`). Record per-protocol interaction counts and anything that misbehaved in the report.

- [ ] **Step 4: Commit the report**

```bash
git add -f docs/superpowers/reports/2026-10-08-chembl-naming-fit-test.md
git commit -m "docs(protocols): create-flow walk results

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- docs/superpowers/reports/2026-10-08-chembl-naming-fit-test.md
```
