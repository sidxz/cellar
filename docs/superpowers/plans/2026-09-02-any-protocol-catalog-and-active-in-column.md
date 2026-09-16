# Any-Protocol Catalog + "Active in" Column Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Derive the "Any protocol" where-picker from every protocol's measurements, and show a single "Active in" results column listing the protocols a compound was active in with the native value and curve class.

**Architecture:** Backend `_activity_query.py` gains two any-protocol where shapes (intercept-key across protocols, readout-name across protocols). `MoleculeActivityService` gains an `any` column token that returns per-protocol entries. Frontend derives picker options client-side from the already-loaded `Protocol[]`, renders one `ActiveInCell` column, and expands matched protocols in the existing detail sheet.

**Tech Stack:** Python 3.13 / SQLAlchemy 2 async / Pydantic v2 / pytest (testcontainers for `tests/api`); Next 16 / React 19 / AG Grid Community / vitest.

**Spec:** `docs/superpowers/specs/2026-09-02-any-protocol-catalog-and-active-in-column-spec.md`

## Global Constraints

- Branch: `feat/any-protocol-activity-search` (already exists, builds on commit `8cef97a9`).
- Commits: `git commit -m "..." -- <explicit paths>` only. End every message with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Never add a `Claude-Session:` trailer.
- Backend tests that touch Postgres need `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock`. Run from `backend/` with `uv run pytest`.
- Frontend: run from `frontend/`; `pnpm exec vitest run <path>`, `pnpm exec tsc --noEmit -p .`, `pnpm lint` (check exit code, not output).
- Never hand-roll a TS interface that mirrors a backend DTO. `activity_data` is `dict[str, dict[str, Any]]` in OpenAPI so orval emits nothing for it; the FE's `ActivityValue` is a documented client-side narrowing. Follow that pattern for the new `any` payload.
- Normalize to µM only for filtering and sorting. Display native units.
- Deviation from spec, agreed in planning: server-side `sort_by=any` is **not** built. Existing activity columns sort client-side over loaded rows via AG Grid `valueGetter`; the new column does the same. Add server sort only if chemists ask.

---

## File map

Backend
- Modify `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/_activity_query.py` — any-protocol where shapes.
- Modify `backend/src/cellar/domain/screening_assay/activity_types.py` — `AnyProtocolEntry`, `AnyProtocolActivity`.
- Modify `backend/src/cellar/domain/screening_assay/repository.py` — `find_aggregated_by_molecules_and_names` on `ReadoutDataRepository`.
- Modify `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/readout_data_repository.py` — implement it.
- Modify `backend/src/cellar/application/screening/molecule_activity_service.py` — `any` token.
- Modify `backend/src/cellar/application/research_organization/execute_search.py` — pass readout groups from criteria.
- Modify `backend/src/cellar/application/export/row_streams/search_results.py` — `any` token → one text column.
- Tests: `backend/tests/unit/test_search_query_composer.py`, `backend/tests/api/test_search.py`, `backend/tests/unit/application/screening/test_molecule_activity_service.py`, `backend/tests/unit/application/export/row_streams/test_search_results.py`.

Frontend (`frontend/src/features/research-organization/`)
- Modify `types/index.ts` — `readout_name`/`unit` on where condition; `AnyProtocolEntry`, `AnyProtocolActivity`.
- Modify `lib/activity-where-options.ts` — derived catalog, ids.
- Modify `lib/protocol-column-id.ts` — tolerate `any`.
- Modify `components/search/protocol-section.tsx` — pass `Protocol[]` to rows; use derived catalog.
- Modify `components/search/search-form.tsx` — pass protocols, cleaning rule, emit `any` column.
- Create `components/search/active-in-cell.tsx` — cell renderer.
- Modify `components/search/results-grid.tsx` — "Active in" column.
- Modify `components/search-page.tsx` — visible protocol ids on row click.
- Tests: `lib/activity-where-options.test.ts`, `lib/protocol-column-id.test.ts`, `components/search/active-in-cell.test.tsx`.

---

## Part 1 — Derived measurement catalog

### Task 1: Backend — intercept-key across protocols

**Files:**
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/_activity_query.py`
- Test: `backend/tests/unit/test_search_query_composer.py`

**Interfaces:**
- Consumes: `_jsonb_intercept_value(kind, level)`, `_fitted_value_micromolar()`, `_value_filter(col, cond)`, `_potency_any_protocol_clause(cond, ws)` — all already in the file.
- Produces: `_to_micromolar(expr: ColumnElement) -> ColumnElement` (module-private, reused by Task 6's sort helper if ever needed); any-protocol `dr_curve` conditions accept `intercept_key`.

- [ ] **Step 1: Write the failing tests** — append to `class TestActivityAnyProtocol` in `backend/tests/unit/test_search_query_composer.py`:

```python
    def test_intercept_key_any_protocol_uses_jsonb_and_unit_case(self) -> None:
        clause = _compose({
            "criteria": [
                {"type": "activity", "protocol_id": None,
                 "where": [{"source": "dr_curve", "intercept_key": {"kind": "ec", "level": 90},
                            "operator": "lt", "value": 10.0}]}
            ],
            "logic": "and",
        })
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "jsonb_array_elements" in sql
        assert "dose_unit" in sql
        assert "molecular_weight" in sql
        assert "readout_definition_id" not in sql

    def test_intercept_key_any_protocol_invalid_kind_rejected(self) -> None:
        with pytest.raises(ValueError, match="intercept_key"):
            _compose({
                "criteria": [
                    {"type": "activity", "protocol_id": None,
                     "where": [{"source": "dr_curve", "intercept_key": {"kind": "xx", "level": 50},
                                "operator": "lt", "value": 1}]}
                ],
                "logic": "and",
            })
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/unit/test_search_query_composer.py::TestActivityAnyProtocol -q`
Expected: the two new tests FAIL (first: `jsonb_array_elements` missing — the current potency path uses `fitted_value`; second: no ValueError).

- [ ] **Step 3: Implement** — in `_activity_query.py` replace `_fitted_value_micromolar` and `_potency_any_protocol_clause` with:

```python
def _to_micromolar(expr: Any) -> ColumnElement:
    """Express ``expr`` (a value in the owning protocol's ``dose_unit``) in µM.

    Molar units scale by a constant; mg/mL needs the molecule's molecular
    weight (µM = mg/mL × 1e6 / MW) and yields NULL when MW is unknown, so
    that curve simply cannot match a cutoff. The CASE is generated from
    ``ConcentrationUnit`` so a new unit cannot be silently mis-scaled.
    Callers must join ``ProtocolModel`` and ``MoleculeModel``.
    """
    whens = []
    for unit in ConcentrationUnit:
        factor = unit.micromolar_factor
        if factor is None:
            scaled = expr * 1_000_000.0 / MoleculeModel.molecular_weight
        else:
            scaled = expr * factor
        whens.append((ProtocolModel.dose_unit == unit.value, scaled))
    return sa.case(*whens, else_=None)


def _potency_any_protocol_clause(cond: dict[str, Any], workspace_id: uuid.UUID) -> ColumnElement:
    """Molecules with at least one DR curve in ANY protocol whose intercept,
    normalized to µM, satisfies the condition.

    ``intercept_key`` (kind, level) picks the intercept from the curve's
    ``intercept_values`` JSONB (curves store the primary there too, so one
    path serves IC50 and EC90). Without it the primary ``fitted_value`` is
    used — the legacy shape from the first any-protocol release.
    """
    ik = cond.get("intercept_key")
    if ik is None:
        expr: Any = DoseResponseCurveModel.fitted_value
    else:
        kind = ik.get("kind") if isinstance(ik, dict) else None
        level = ik.get("level") if isinstance(ik, dict) else None
        if kind not in ("ic", "ec") or not isinstance(level, (int, float)):
            msg = f"Invalid intercept_key on any-protocol activity where: {ik!r}"
            raise ValueError(msg)
        expr = _jsonb_intercept_value(kind, float(level))
    sub = (
        sa.select(DoseResponseCurveModel.molecule_id)
        .join(ProtocolModel, DoseResponseCurveModel.protocol_id == ProtocolModel.id)
        .join(MoleculeModel, DoseResponseCurveModel.molecule_id == MoleculeModel.id)
        .where(
            DoseResponseCurveModel.workspace_id == workspace_id,
            _value_filter(_to_micromolar(expr), cond),
        )
    )
    return MoleculeModel.id.in_(sub)
```

Then in `_activity_where_clause`, the existing block

```python
    if protocol_id is None:
        if source == "readout_data":
            ...
        if source == "dr_curve" and not rd_id:
            return _potency_any_protocol_clause(cond, workspace_id)
```

stays as is (Task 2 edits the `readout_data` branch). Delete the old `_fitted_value_micromolar` function.

- [ ] **Step 4: Run tests**

Run: `cd backend && uv run pytest tests/unit/test_search_query_composer.py -q && uv run ruff check src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/_activity_query.py && uv run ruff format --check src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/_activity_query.py`
Expected: all pass, ruff clean. (The earlier `test_potency_any_protocol_normalizes_to_micromolar` must still pass — it asserts `fitted_value`, `dose_unit`, `molecular_weight`.)

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(search): any-protocol dr_curve conditions accept an intercept_key (IC50/EC90 across protocols, µM)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/_activity_query.py backend/tests/unit/test_search_query_composer.py
```

---

### Task 2: Backend — readout by name across protocols

**Files:**
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/_activity_query.py`
- Test: `backend/tests/unit/test_search_query_composer.py`

**Interfaces:**
- Produces: `normalize_readout_name(name: str) -> str` (public, module `_activity_query.py`; Task 7's reader imports it so both sides normalize identically); any-protocol `readout_data` conditions accept `readout_name` + optional `unit`.

- [ ] **Step 1: Write the failing tests** — append to `TestActivityAnyProtocol`:

```python
    def test_readout_name_any_protocol_joins_definitions(self) -> None:
        clause = _compose({
            "criteria": [
                {"type": "activity", "protocol_id": None,
                 "where": [{"source": "readout_data", "readout_name": "  % Inhibition ",
                            "unit": "%", "operator": "gt", "value": 50}]}
            ],
            "logic": "and",
        })
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "readout_definitions" in sql
        assert "'% inhibition'" in sql          # normalized: lower + trim + single spaces
        assert "value_numeric > 50" in sql
        assert "is_outlier" in sql

    def test_readout_name_any_protocol_null_unit_matches_empty(self) -> None:
        clause = _compose({
            "criteria": [
                {"type": "activity", "protocol_id": None,
                 "where": [{"source": "readout_data", "readout_name": "MIC",
                            "operator": "lt", "value": 2}]}
            ],
            "logic": "and",
        })
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "coalesce(readout_definitions.unit, '') = ''" in sql

    def test_readout_data_any_protocol_without_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="readout_name"):
            _compose({
                "criteria": [
                    {"type": "activity", "protocol_id": None,
                     "where": [{"source": "readout_data", "operator": "gt", "value": 1}]}
                ],
                "logic": "and",
            })
```

Also **update** the existing `test_readout_data_any_protocol_rejected` (it sends a `readout_definition_id` with no protocol): keep it but change its `match=` to `"protocol_id"` — a readout-def id without a protocol is now the "needs protocol_id" error, not the "readout_data" one.

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/unit/test_search_query_composer.py::TestActivityAnyProtocol -q`
Expected: three new tests FAIL; the updated one FAILS on the message.

- [ ] **Step 3: Implement** — add near the top of `_activity_query.py` (after `_ACTIVITY_OP_MAP`):

```python
import re

_WS_RUN = re.compile(r"\s+")


def normalize_readout_name(name: str) -> str:
    """Grouping key for readout-defs across protocols: lowercase, trimmed,
    internal whitespace collapsed. The FE catalog uses the same rule.
    A controlled readout vocabulary would replace this string key."""
    return _WS_RUN.sub(" ", name.strip()).lower()


def _sql_normalized_name(col: Any) -> ColumnElement:
    return sa.func.lower(sa.func.btrim(sa.func.regexp_replace(col, r"\s+", " ", "g")))
```

Add `ReadoutDefinitionModel` to the `screening_assay.models` import. Add this clause builder after `_potency_any_protocol_clause`:

```python
def _readout_name_any_protocol_clause(
    cond: dict[str, Any], workspace_id: uuid.UUID
) -> ColumnElement:
    """Molecules with a non-outlier readout value, in ANY protocol whose
    readout-def matches by normalized name + unit, satisfying the condition.
    No unit conversion: the unit is part of the group identity."""
    name = cond.get("readout_name")
    if not isinstance(name, str) or not name.strip():
        msg = "any-protocol readout_data where needs a non-empty readout_name"
        raise ValueError(msg)
    unit = cond.get("unit") or ""
    sub = (
        sa.select(ReadoutDataModel.molecule_id)
        .join(
            ReadoutDefinitionModel,
            ReadoutDataModel.readout_definition_id == ReadoutDefinitionModel.id,
        )
        .where(
            ReadoutDataModel.workspace_id == workspace_id,
            ReadoutDataModel.is_outlier == False,  # noqa: E712
            _sql_normalized_name(ReadoutDefinitionModel.name) == normalize_readout_name(name),
            sa.func.coalesce(ReadoutDefinitionModel.unit, "") == unit,
            _value_filter(ReadoutDataModel.value_numeric, cond),
        )
    )
    return MoleculeModel.id.in_(sub)
```

Replace the any-protocol block in `_activity_where_clause` with:

```python
    rd_id = cond.get("readout_definition_id")
    if protocol_id is None:
        if source == "readout_data" and not rd_id:
            return _readout_name_any_protocol_clause(cond, workspace_id)
        if source == "dr_curve" and not rd_id:
            return _potency_any_protocol_clause(cond, workspace_id)
    if not rd_id:
        msg = "where condition needs readout_definition_id"
        raise ValueError(msg)
    if protocol_id is None:
        msg = "where condition with readout_definition_id needs protocol_id"
        raise ValueError(msg)
```

Update the `_activity_clause` docstring's any-protocol paragraph to list the three allowed shapes (presence, curve_class, dr_curve±intercept_key, readout_data+readout_name).

- [ ] **Step 4: Run tests + lint**

Run: `cd backend && uv run pytest tests/unit/test_search_query_composer.py -q && uv run ruff check src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/_activity_query.py && uv run ruff format --check src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/_activity_query.py`
Expected: PASS, clean. If `"'% inhibition'"` fails on quoting, print `sql` and adjust the assertion to the literal form SQLAlchemy emitted (the intent is the normalized lowercase string is bound).

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(search): any-protocol readout_data conditions match readout-defs by normalized name + unit

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/_activity_query.py backend/tests/unit/test_search_query_composer.py
```

---

### Task 3: API test — both shapes against Postgres

**Files:**
- Test: `backend/tests/api/test_search.py` (extend `_seed_multi_run_dr`, add a readout seeder, add tests to `TestActivityAnyProtocol`)

**Interfaces:**
- Consumes: `_seed_multi_run_dr(uow, *, workspace_id, molecule_id, run_count, approved, dose_unit, fitted_value)` (exists), `DoseResponseCurve`, `InterceptValue`/`InterceptSpec` domain types (`cellar.domain.screening_assay.curve_fitting.InterceptValue`, `cellar.domain.screening_assay.dose_response_config.InterceptSpec`, `InterceptKind`, `InterceptBasis`).

- [ ] **Step 1: Extend the seeder** — add parameters and intercepts to `_seed_multi_run_dr`:

```python
async def _seed_multi_run_dr(
    uow: AsyncUnitOfWork,
    *,
    workspace_id: uuid.UUID,
    molecule_id: uuid.UUID,
    run_count: int,
    approved: bool = True,
    dose_unit: str = "uM",
    fitted_value: float = 5.0,
    intercepts: list[tuple[str, float, float]] | None = None,
) -> tuple[uuid.UUID, uuid.UUID, list[uuid.UUID]]:
    """... existing docstring ...

    ``intercepts`` = list of ``(kind, level, value)`` stored on every curve's
    ``intercept_values`` (e.g. ``[("ic", 50, 5.0), ("ic", 90, 40.0)]``).
    """
```

and, where the curve is built, add:

```python
            intercept_values = (
                [
                    InterceptValue(
                        spec=InterceptSpec(
                            kind=InterceptKind(kind),
                            level=level,
                            basis=InterceptBasis.RELATIVE_PERCENT,
                            label=f"{kind.upper()}{int(level)}",
                        ),
                        value=value,
                        confidence_interval_low=None,
                        confidence_interval_high=None,
                        at_bound=False,
                    )
                    for kind, level, value in intercepts
                ]
                if intercepts
                else None
            )
            curve = DoseResponseCurve(
                ...,  # existing kwargs unchanged
                intercept_values=intercept_values,
            )
```

Add the imports at the top of the test file:

```python
from cellar.domain.screening_assay.curve_fitting import InterceptValue
from cellar.domain.screening_assay.dose_response_config import (
    InterceptBasis,
    InterceptKind,
    InterceptSpec,
)
```

- [ ] **Step 2: Add a readout seeder** (after `_seed_multi_run_dr`):

```python
async def _seed_numeric_readout(
    uow: AsyncUnitOfWork,
    *,
    workspace_id: uuid.UUID,
    molecule_id: uuid.UUID,
    readout_name: str,
    unit: str | None,
    value: float,
) -> uuid.UUID:
    """One protocol + one numeric readout-def + one run + one readout_data row."""
    protocol_id, rd_id, run_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with uow:
        await uow.session.execute(
            sa.text(
                "INSERT INTO protocols (id, workspace_id, name, protocol_type, status, "
                "is_locked, dose_unit, pos_control_signal, version, protocol_version, created_by) "
                "VALUES (:id, :ws, :name, 'biochemical', 'active', false, 'uM', 'high', 1, 1, :user)"
            ),
            {"id": protocol_id, "ws": workspace_id, "name": f"RD-{protocol_id.hex[:8]}",
             "user": _SEED_USER_ID},
        )
        await uow.session.execute(
            sa.text(
                "INSERT INTO readout_definitions "
                "(id, protocol_id, name, data_type, unit, display_order, is_calculated) "
                "VALUES (:id, :proto, :name, 'numeric', :unit, 0, false)"
            ),
            {"id": rd_id, "proto": protocol_id, "name": readout_name, "unit": unit},
        )
        await uow.session.execute(
            sa.text(
                "INSERT INTO runs (id, workspace_id, protocol_id, run_date, operator, "
                "status, is_locked, version, notes) "
                "VALUES (:id, :ws, :proto, :run_date, :user, 'approved', false, 1, NULL)"
            ),
            {"id": run_id, "ws": workspace_id, "proto": protocol_id,
             "run_date": date.today(), "user": _SEED_USER_ID},
        )
        await uow.session.execute(
            sa.text(
                "INSERT INTO readout_data (id, workspace_id, run_id, molecule_id, "
                "readout_definition_id, value_numeric, is_outlier, is_computed) "
                "VALUES (:id, :ws, :run, :mol, :rd, :val, false, false)"
            ),
            {"id": uuid.uuid4(), "ws": workspace_id, "run": run_id, "mol": molecule_id,
             "rd": rd_id, "val": value},
        )
        await uow.commit()
    return protocol_id
```

If the `readout_data` INSERT fails on a NOT NULL column, run `docker exec -i chem-vault2-postgres-1 psql -U cellar -d cellar -c '\d readout_data'` and add the missing column with a neutral value; do not change the schema.

- [ ] **Step 3: Write the failing tests** — in `TestActivityAnyProtocol`:

```python
    async def test_intercept_key_across_protocols(
        self, client: AsyncClient, org_id: str, uow: AsyncUnitOfWork, workspace_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/api/v1/molecules",
            json={"name": "AnyIcMol", "smiles": "CCCCCO", "originating_org_id": org_id},
        )
        mol_id = str(resp.json()["molecule"]["id"])
        # Protocol A (µM): IC50 5 µM, IC90 40 µM.  Protocol B (nM): IC50 5 nM.
        await _seed_multi_run_dr(
            uow, workspace_id=workspace_id, molecule_id=uuid.UUID(mol_id), run_count=1,
            intercepts=[("ic", 50, 5.0), ("ic", 90, 40.0)],
        )
        await _seed_multi_run_dr(
            uow, workspace_id=workspace_id, molecule_id=uuid.UUID(mol_id), run_count=1,
            dose_unit="nM", intercepts=[("ic", 50, 5.0)],
        )

        async def ids_for(where: list[dict]) -> set[str]:
            body = {"query": {"criteria": [{"type": "activity", "protocol_id": None,
                                            "where": where}], "logic": "and"}}
            res = await client.post("/api/v1/search/execute", json=body)
            assert res.status_code == 200, res.text
            return {m["id"] for m in res.json()["items"]}

        ic50 = {"kind": "ic", "level": 50}
        ic90 = {"kind": "ic", "level": 90}
        # IC50 < 1 µM: only B (5 nM) qualifies after normalization.
        assert mol_id in await ids_for([{"source": "dr_curve", "intercept_key": ic50,
                                         "operator": "lt", "value": 1.0}])
        # IC90 < 10 µM: A's IC90 is 40 µM, B has no IC90 → no match.
        assert mol_id not in await ids_for([{"source": "dr_curve", "intercept_key": ic90,
                                             "operator": "lt", "value": 10.0}])
        # IC90 < 50 µM: A qualifies.
        assert mol_id in await ids_for([{"source": "dr_curve", "intercept_key": ic90,
                                         "operator": "lt", "value": 50.0}])

    async def test_readout_name_across_protocols(
        self, client: AsyncClient, org_id: str, uow: AsyncUnitOfWork, workspace_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/api/v1/molecules",
            json={"name": "AnyRdMol", "smiles": "CCCCCCO", "originating_org_id": org_id},
        )
        mol_id = uuid.UUID(resp.json()["molecule"]["id"])
        await _seed_numeric_readout(uow, workspace_id=workspace_id, molecule_id=mol_id,
                                    readout_name="% Inhibition", unit="%", value=20.0)
        await _seed_numeric_readout(uow, workspace_id=workspace_id, molecule_id=mol_id,
                                    readout_name="%  inhibition", unit="%", value=80.0)
        await _seed_numeric_readout(uow, workspace_id=workspace_id, molecule_id=mol_id,
                                    readout_name="% Inhibition", unit=None, value=99.0)

        async def ids_for(where: list[dict]) -> set[str]:
            body = {"query": {"criteria": [{"type": "activity", "protocol_id": None,
                                            "where": where}], "logic": "and"}}
            res = await client.post("/api/v1/search/execute", json=body)
            assert res.status_code == 200, res.text
            return {m["id"] for m in res.json()["items"]}

        # > 50 in "% Inhibition (%)": second protocol (80) matches despite spacing/case.
        assert str(mol_id) in await ids_for([{"source": "readout_data",
                                              "readout_name": "% Inhibition", "unit": "%",
                                              "operator": "gt", "value": 50}])
        # > 90 in "% Inhibition (%)": 99 is in the unit-less group, so no match.
        assert str(mol_id) not in await ids_for([{"source": "readout_data",
                                                  "readout_name": "% Inhibition", "unit": "%",
                                                  "operator": "gt", "value": 90}])
```

- [ ] **Step 4: Run**

Run: `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api/test_search.py -q`
Expected: all pass (the two new tests included). If the readout seeder's INSERT fails, fix the column list per Step 2's note.

- [ ] **Step 5: Lint + commit**

Run: `cd backend && uv run ruff format tests/api/test_search.py && uv run ruff check tests/api/test_search.py`

```bash
git commit -m "test(api): any-protocol intercept-key and readout-name searches against Postgres

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- backend/tests/api/test_search.py
```

---

### Task 4: Frontend — derived catalog + ids + types

**Files:**
- Modify: `frontend/src/features/research-organization/types/index.ts` (the `ActivityWhereCondition` interface, ~line 292)
- Modify: `frontend/src/features/research-organization/lib/activity-where-options.ts`
- Test: `frontend/src/features/research-organization/lib/activity-where-options.test.ts`

**Interfaces:**
- Produces:
  - `ActivityWhereCondition.readout_name?: string; unit?: string | null`
  - `buildAnyProtocolWhereOptions(protocols: Protocol[]): WhereOption[]` (signature change: now takes protocols)
  - `anyDrOptionId(key: {kind: string; level: number}): string` → `any:dr:<kind>:<level>`
  - `anyRdOptionId(name: string, unit: string | null): string` → `any:rd:<normalized>|<unit>`
  - `normalizeReadoutName(name: string): string`
  - `POTENCY_UM_OPTION_ID` stays exported (legacy)
  - `parseWhereOptionId(id)` returns `Pick<ActivityWhereCondition, "source" | "readout_definition_id" | "intercept_key" | "readout_name" | "unit">`
  - `whereConditionOptionId(cond, anyProtocol)` inverse for the new ids
  - `WhereOption.protocolCount?: number`

- [ ] **Step 1: Write the failing tests** — replace the existing `describe("any-protocol options", ...)` block in `activity-where-options.test.ts` with:

```ts
describe("any-protocol derived catalog", () => {
  const P1 = "11111111-1111-1111-1111-111111111111";
  const P2 = "22222222-2222-2222-2222-222222222222";
  const P3 = "33333333-3333-3333-3333-333333333333";

  function protocolWith(id: string, rds: ReadoutDefinition[]): Protocol {
    return { ...proto([]), id, name: `P-${id.slice(0, 2)}`, readout_definitions: rds };
  }

  const ic50 = { kind: "ic" as const, level: 50, basis: "relative_percent" as const, label: null };
  const ic90 = { ...ic50, level: 90 };

  const protocols = [
    protocolWith(P1, [
      rd({ id: "a1", name: "IC50", data_type: "dose_response", unit: "uM",
           dose_response_config: drConfig("ic50", [ic50, ic90]) }),
      rd({ id: "a2", name: "% Inhibition", unit: "%" }),
    ]),
    protocolWith(P2, [
      rd({ id: "b1", name: "IC50", data_type: "dose_response", unit: "nM",
           dose_response_config: drConfig("ic50", [ic50]) }),
      rd({ id: "b2", name: "%  inhibition ", unit: "%" }),
      rd({ id: "b3", name: "Scientist", data_type: "text" }),
    ]),
    protocolWith(P3, [
      // legacy DR readout, no declared intercepts → falls back to curve_type
      rd({ id: "c1", name: "EC50", data_type: "dose_response", unit: "uM",
           dose_response_config: drConfig("ec50", []) }),
      rd({ id: "c2", name: "% Inhibition", unit: null }),
    ]),
  ];

  it("groups DR intercepts by (kind, level) with protocol counts, µM unit", () => {
    const opts = buildAnyProtocolWhereOptions(protocols);
    const dr = opts.filter((o) => o.group === "dose_response");
    expect(dr.map((o) => [o.id, o.protocolCount])).toEqual([
      ["any:dr:ic:50", 2],
      ["any:dr:ec:50", 1],
      ["any:dr:ic:90", 1],
    ]);
    expect(dr[0].label).toBe("IC50 · 2 protocols");
    expect(dr[0].unit).toBe("µM");
    expect(dr[0].source).toBe("dr_curve");
    expect(dr[0].intercept_key).toEqual({ kind: "ic", level: 50 });
  });

  it("groups numeric readouts by normalized name + unit; text excluded", () => {
    const opts = buildAnyProtocolWhereOptions(protocols);
    const num = opts.filter((o) => o.group === "numeric_readout");
    expect(num.map((o) => [o.id, o.protocolCount])).toEqual([
      ["any:rd:% inhibition|%", 2],
      ["any:rd:% inhibition|", 1],
    ]);
    expect(num[0].label).toBe("% Inhibition (%) · 2 protocols");
    expect(num[1].label).toBe("% Inhibition · 1 protocol");
    expect(opts.some((o) => o.label.includes("Scientist"))).toBe(false);
  });

  it("always ends with Curve Class", () => {
    const opts = buildAnyProtocolWhereOptions(protocols);
    expect(opts[opts.length - 1].id).toBe(CURVE_CLASS_OPTION_ID);
    expect(buildAnyProtocolWhereOptions([]).map((o) => o.id)).toEqual([CURVE_CLASS_OPTION_ID]);
  });

  it("round-trips DR and readout ids through parse and back", () => {
    const dr = parseWhereOptionId("any:dr:ic:90");
    expect(dr).toEqual({ source: "dr_curve", readout_definition_id: "",
                         intercept_key: { kind: "ic", level: 90 } });
    expect(whereConditionOptionId({ ...dr!, operator: "lt", value: 1 }, true)).toBe("any:dr:ic:90");

    const rdc = parseWhereOptionId("any:rd:% inhibition|%");
    expect(rdc).toEqual({ source: "readout_data", readout_definition_id: "",
                          intercept_key: null, readout_name: "% inhibition", unit: "%" });
    expect(whereConditionOptionId({ ...rdc!, operator: "gt", value: 50 }, true))
      .toBe("any:rd:% inhibition|%");
    // per-protocol rows never resolve any:* ids
    expect(whereConditionOptionId({ ...rdc!, operator: "gt", value: 50 }, false)).toBe("");
  });

  it("legacy potency (dr_curve, no rd, no key) still resolves on any-protocol rows", () => {
    const cond = { source: "dr_curve" as const, readout_definition_id: "", operator: "lt" as const,
                   value: 1, intercept_key: null };
    expect(whereConditionOptionId(cond, true)).toBe(POTENCY_UM_OPTION_ID);
    expect(parseWhereOptionId(POTENCY_UM_OPTION_ID)).toEqual(
      { source: "dr_curve", readout_definition_id: "", intercept_key: null });
  });
});
```

The test file already has `rd(...)` and `proto(...)` helpers and a `drConfig` helper or equivalent near the top; if `drConfig(curveType, intercepts)` does not exist there, add:

```ts
function drConfig(curve_type: "ic50" | "ec50", intercepts: InterceptSpec[]): DoseResponseConfig {
  return {
    curve_type, y_readout_name: "raw", x_readout_name: null, intercepts,
    hill_slope_constraint: "unconstrained", activity_threshold: null,
    normalization_scope: "per_plate", top_constraint: null, bottom_constraint: null,
    top_constraint_min: null, top_constraint_max: null, bottom_constraint_min: null,
    bottom_constraint_max: null, hill_slope_min: null, hill_slope_max: null,
  } as DoseResponseConfig;
}
```

(copy any additional required fields from `results-grid-columns.test.tsx`'s `drConfig`). Import `POTENCY_UM_OPTION_ID` and the types you use.

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && pnpm exec vitest run src/features/research-organization/lib/activity-where-options.test.ts`
Expected: FAIL (function signature / ids don't exist).

- [ ] **Step 3: Types** — in `types/index.ts` add to `ActivityWhereCondition` after `intercept_key`:

```ts
  /** Any-protocol ``readout_data`` rows only: the readout-def group to match,
   *  by normalized name (+ ``unit``) across every protocol. Mutually exclusive
   *  with ``readout_definition_id``. */
  readout_name?: string;
  unit?: string | null;
```

- [ ] **Step 4: Implement the catalog** — in `activity-where-options.ts` replace the `POTENCY_UM_OPTION_ID` / `CURVE_CLASS_OPTION` / `buildAnyProtocolWhereOptions` block with:

```ts
/** Legacy any-protocol option (first release): primary fitted value of any
 *  DR curve in µM. Not offered in the picker any more; saved searches that
 *  carry it keep round-tripping. */
export const POTENCY_UM_OPTION_ID = "potency_um";

const CURVE_CLASS_OPTION: WhereOption = {
  id: CURVE_CLASS_OPTION_ID,
  label: "Curve Class",
  unit: null,
  source: "curve_class",
  readout_definition_id: "",
  intercept_key: null,
  group: "curve_class",
};

/** Grouping key for a readout name across protocols: lowercase, trimmed,
 *  internal whitespace collapsed. Mirrors the backend's
 *  `normalize_readout_name`. A controlled vocabulary would replace this. */
export function normalizeReadoutName(name: string): string {
  return name.trim().replace(/\s+/g, " ").toLowerCase();
}

export function anyDrOptionId(key: { kind: string; level: number }): string {
  return `any:dr:${key.kind}:${key.level}`;
}

export function anyRdOptionId(name: string, unit: string | null): string {
  return `any:rd:${normalizeReadoutName(name)}|${unit ?? ""}`;
}

function countLabel(n: number): string {
  return `${n} protocol${n === 1 ? "" : "s"}`;
}

/** Build the "Any protocol" picker from what the workspace's protocols
 *  actually measure: one entry per DR intercept (kind, level) and one per
 *  numeric readout (normalized name + unit), each with a protocol count,
 *  then Curve Class. Sorted by count desc, then label. */
export function buildAnyProtocolWhereOptions(protocols: Protocol[]): WhereOption[] {
  const dr = new Map<string, { key: InterceptKey; label: string; protos: Set<string> }>();
  const num = new Map<
    string,
    { name: string; unit: string | null; protos: Set<string> }
  >();

  for (const p of protocols) {
    for (const rd of p.readout_definitions ?? []) {
      const cfg = rd.dose_response_config;
      if (cfg) {
        const specs = cfg.intercepts ?? [];
        const keys: Array<{ key: InterceptKey; label: string }> =
          specs.length > 0
            ? specs.map((s) => ({ key: { kind: s.kind, level: s.level }, label: interceptLabel(s) }))
            : [{ key: { kind: cfg.curve_type.startsWith("ic") ? "ic" : "ec", level: 50 },
                 label: cfg.curve_type.toUpperCase() }];
        for (const { key, label } of keys) {
          const id = anyDrOptionId(key);
          const entry = dr.get(id) ?? { key, label, protos: new Set<string>() };
          entry.protos.add(p.id);
          dr.set(id, entry);
        }
      } else if (rd.data_type === "numeric") {
        const id = anyRdOptionId(rd.name, rd.unit);
        const entry = num.get(id) ?? { name: rd.name.trim(), unit: rd.unit, protos: new Set<string>() };
        entry.protos.add(p.id);
        num.set(id, entry);
      }
    }
  }

  const byCountThenLabel = (a: WhereOption, b: WhereOption) =>
    (b.protocolCount ?? 0) - (a.protocolCount ?? 0) || a.label.localeCompare(b.label);

  const drOpts: WhereOption[] = [...dr.entries()].map(([id, e]) => ({
    id,
    label: `${e.label} · ${countLabel(e.protos.size)}`,
    unit: "µM",
    source: "dr_curve",
    readout_definition_id: "",
    intercept_key: e.key,
    group: "dose_response",
    protocolCount: e.protos.size,
  }));
  const numOpts: WhereOption[] = [...num.entries()].map(([id, e]) => ({
    id,
    label: `${e.name}${e.unit ? ` (${e.unit})` : ""} · ${countLabel(e.protos.size)}`,
    unit: e.unit,
    source: "readout_data",
    readout_definition_id: "",
    intercept_key: null,
    group: "numeric_readout",
    protocolCount: e.protos.size,
  }));

  return [...drOpts.sort(byCountThenLabel), ...numOpts.sort(byCountThenLabel), CURVE_CLASS_OPTION];
}
```

Add `protocolCount?: number;` to `WhereOption` with the comment `/** Any-protocol options: how many protocols measure this. */`. Import `interceptLabel` from `@/features/screening-assay/lib/intercept-label` and `InterceptKey` from `@/features/screening-assay/types` (it's `{ kind: "ec" | "ic"; level: number }`). Keep the per-protocol `buildActivityWhereOptions` pushing `CURVE_CLASS_OPTION` as today.

Then extend the parser and inverse:

```ts
export function parseWhereOptionId(
  id: string,
): Pick<
  ActivityWhereCondition,
  "source" | "readout_definition_id" | "intercept_key" | "readout_name" | "unit"
> | null {
  if (id === CURVE_CLASS_OPTION_ID) {
    return { source: "curve_class", readout_definition_id: "", intercept_key: null };
  }
  if (id === POTENCY_UM_OPTION_ID) {
    return { source: "dr_curve", readout_definition_id: "", intercept_key: null };
  }
  if (id.startsWith("any:dr:")) {
    const [, , kind, levelStr] = id.split(":");
    const level = Number(levelStr);
    if (Number.isNaN(level)) return null;
    const intercept_key = narrowInterceptKey({ kind, level });
    if (!intercept_key) return null;
    return { source: "dr_curve", readout_definition_id: "", intercept_key };
  }
  if (id.startsWith("any:rd:")) {
    const body = id.slice("any:rd:".length);
    const sep = body.lastIndexOf("|");
    if (sep < 0) return null;
    const unit = body.slice(sep + 1);
    return {
      source: "readout_data",
      readout_definition_id: "",
      intercept_key: null,
      readout_name: body.slice(0, sep),
      unit: unit === "" ? null : unit,
    };
  }
  // ... existing dr_curve / readout_data branches unchanged
}

export function whereConditionOptionId(cond: ActivityWhereCondition, anyProtocol = false): string {
  if (cond.source === "curve_class") return CURVE_CLASS_OPTION_ID;
  if (!cond.readout_definition_id) {
    if (!anyProtocol) return "";
    if (cond.source === "readout_data") {
      return cond.readout_name ? anyRdOptionId(cond.readout_name, cond.unit ?? null) : "";
    }
    if (cond.source === "dr_curve") {
      return cond.intercept_key ? anyDrOptionId(cond.intercept_key) : POTENCY_UM_OPTION_ID;
    }
    return "";
  }
  // ... existing per-protocol branches unchanged
}
```

Note: `readout_name` on the wire is the **normalized** string (the option id carries it normalized). The backend normalizes again, so this is safe and keeps ids and conditions identical.

- [ ] **Step 5: Run tests + typecheck**

Run: `cd frontend && pnpm exec vitest run src/features/research-organization/lib/activity-where-options.test.ts && pnpm exec tsc --noEmit -p .`
Expected: PASS. `tsc` will now FAIL in `protocol-section.tsx` because `buildAnyProtocolWhereOptions()` is called with no argument — that's Task 5. If nothing else fails, proceed.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(search): derive the any-protocol where-picker from every protocol's measurements

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- frontend/src/features/research-organization/types/index.ts frontend/src/features/research-organization/lib/activity-where-options.ts frontend/src/features/research-organization/lib/activity-where-options.test.ts
```

---

### Task 5: Frontend — wire the catalog into the section + form

**Files:**
- Modify: `frontend/src/features/research-organization/components/search/protocol-section.tsx`
- Modify: `frontend/src/features/research-organization/components/search/search-form.tsx`

**Interfaces:**
- Consumes: `buildAnyProtocolWhereOptions(protocols)` (Task 4); `ProtocolSectionProps` (existing); `search-form.tsx` already holds `protocols: Protocol[]`.
- Produces: `ProtocolSectionProps.protocols: Protocol[]` (new required prop); `ActivityRowProps.fullProtocols: Protocol[]`.

- [ ] **Step 1: Thread `Protocol[]` into the section.** In `protocol-section.tsx`:
  - Add to `ProtocolSectionProps`: `/** Full protocol records (with readout_definitions) — feeds the any-protocol catalog. */ protocols: Protocol[];` and import `type Protocol` from `@/features/screening-assay/types`.
  - Destructure it in `ProtocolSection({ criteria, conjunctions, projectIds, protocols, onChange })` and pass `fullProtocols={protocols}` to every `<ActivityRow ...>` render inside the section (there are two: the pristine placeholder row and the mapped real rows — grep `<ActivityRow`).
  - Add to `ActivityRowProps`: `fullProtocols: Protocol[];` and destructure it.
  - Change the memo:

```tsx
  const whereOptions = useMemo(
    () =>
      isAnyProtocol ? buildAnyProtocolWhereOptions(fullProtocols) : buildActivityWhereOptions(protocol),
    [isAnyProtocol, fullProtocols, protocol],
  );
```

  - In `WhereRow`'s select `onValueChange`, the non-curve-class branch spreads `...parsed` — `parsed` now may carry `readout_name`/`unit`. When switching from a readout option to a DR option those must be cleared, so change that branch to:

```tsx
            onChange({
              ...cond,
              ...parsed,
              readout_name: parsed.readout_name,
              unit: parsed.unit,
              operator: cond.operator === "eq" || isCurveClass ? "lt" : cond.operator,
              curve_classes: undefined,
            });
```

  - Legacy saved searches: when a where-row's `fieldValue === POTENCY_UM_OPTION_ID` and no option carries that id, `WhereRow` must still show a label. In `WhereRow`, compute `const legacyPotency = fieldValue === POTENCY_UM_OPTION_ID && !options.some((o) => o.id === fieldValue);` and pass `legacyPotency` to `<WhereOptionList options={options} legacyPotency={legacyPotency} />`; in `WhereOptionList`, when the flag is set, render first `<SelectItem value={POTENCY_UM_OPTION_ID} disabled>Potency (primary fit) — legacy</SelectItem>` so the Select displays it but new rows can't pick it. Import `POTENCY_UM_OPTION_ID`.
  - The option list renderer (`WhereOptionList`) shows `o.label` and appends `o.unit` for numeric options at line ~434; the DR heading branch prints `o.label` only. No change needed: any-protocol labels already carry the count, and the numeric label carries the unit — so **remove** the unit suffix for options whose id starts with `any:` to avoid "(%) (%)": change that line to `{o.unit && !o.id.startsWith("any:") ? \` (${o.unit})\` : ""}`.

- [ ] **Step 2: Pass protocols from the form.** In `search-form.tsx`, find the `<ProtocolSection` render and add `protocols={protocols}`. Update the where-cleaning rule (the block edited in `8cef97a9`):

```ts
        // Any-protocol rows: potency (dr_curve, no rd) and readout-by-name are
        // readout-def-less by design.
        if (!w.readout_definition_id) {
          const anyDr = c.protocol_id === null && w.source === "dr_curve";
          const anyRd = c.protocol_id === null && w.source === "readout_data" && !!w.readout_name;
          if (!anyDr && !anyRd) return false;
        }
```

- [ ] **Step 3: Typecheck, lint, run the section-adjacent tests**

Run: `cd frontend && pnpm exec tsc --noEmit -p . && pnpm lint; echo "lint exit=$?" && pnpm exec vitest run src/features/research-organization`
Expected: tsc clean, lint exit 0, all tests pass.

- [ ] **Step 4: Manual check in Chrome** (backend + frontend running; see Task 10 for launch). On /search pick "Any protocol", open the where select: expect "IC50 · 3 protocols", "EC50 · 1 protocol", "EC90 · 1 protocol" under Dose-response, "% Inhibition (%) · 2 protocols" etc. under Numeric readouts, then Curve Class. Pick "% Inhibition (%) · 2 protocols", `>` 50, Search: expect a 200 and a non-zero count if local data has such values (it may be 0; the request succeeding is the check).

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(search): any-protocol rows use the derived measurement catalog

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- frontend/src/features/research-organization/components/search/protocol-section.tsx frontend/src/features/research-organization/components/search/search-form.tsx
```

---

## Part 2 — "Active in" results column

### Task 6: Backend — domain types + `any` token (DR entries)

**Files:**
- Modify: `backend/src/cellar/domain/screening_assay/activity_types.py`
- Modify: `backend/src/cellar/application/screening/molecule_activity_service.py`
- Test: `backend/tests/unit/application/screening/test_molecule_activity_service.py`

**Interfaces:**
- Consumes: `_build_dr_activity(...)`, `_build_resolved_runs(...)`, `_fetch_curves_and_runs(...)`, `self._protocol_repo.find_by_ids`, `self._protocol_repo.find_effective_targets_for_protocols`, `ConcentrationUnit.micromolar_factor`.
- Produces:
  - `AnyProtocolEntry`, `AnyProtocolActivity` dataclasses (frozen) in `activity_types.py`.
  - `enrich_molecules(...)` return type widens to `dict[uuid.UUID, dict[str, ActivityValue | AnyProtocolActivity]]`; key `"any"` holds an `AnyProtocolActivity`.
  - New keyword `any_readout_groups: list[tuple[str, str | None]] | None = None` on `enrich_molecules` / `_enrich_molecules` (used by Task 7; accepted but ignored in this task).

- [ ] **Step 1: Write the failing test** — append to `test_molecule_activity_service.py`:

```python
# ---------------------------------------------------------------------------
# Tests — "any" column: one entry per (protocol, DR readout-def), best first.
# ---------------------------------------------------------------------------

PROTO_B = uuid.UUID("bbbbbbbb-0000-0000-0000-00000000000b")
RD_B = uuid.UUID("bbbbbbbb-0000-0000-0000-00000000000d")


def _make_protocol(*, protocol_id: uuid.UUID, name: str, dose_unit: str):
    """Minimal stand-in for the Protocol aggregate as the service reads it."""
    from types import SimpleNamespace

    from cellar.domain.shared.enums import ConcentrationUnit

    return SimpleNamespace(
        id=protocol_id,
        name=name,
        protocol_type=SimpleNamespace(value="biochemical"),
        dose_unit=ConcentrationUnit(dose_unit),
    )


class TestEnrichMoleculesAnyColumn:
    @pytest.mark.asyncio
    async def test_any_lists_protocols_best_first_in_native_units(self) -> None:
        run_a, run_b = uuid.uuid4(), uuid.uuid4()
        curve_a = _make_curve(fitted_value=5.0, run_id=run_a,
                              intercept_values=[_make_intercept_value(
                                  kind=InterceptKind.IC, level=50.0, label="IC50", value=5.0)])
        curve_b = _make_curve(protocol_id=PROTO_B, readout_definition_id=RD_B,
                              fitted_value=5.0, run_id=run_b, curve_class=CurveClass.PARTIAL,
                              intercept_values=[_make_intercept_value(
                                  kind=InterceptKind.IC, level=50.0, label="IC50", value=5.0)])
        curve_repo = AsyncMock()
        curve_repo.find_all_curves_for_molecules = AsyncMock(
            return_value={MOL_ID: {RD_ID: [curve_a], RD_B: [curve_b]}}
        )
        runs = {
            run_a: _make_run(run_id=run_a, run_date=date(2026, 4, 1)),
            run_b: _make_run(run_id=run_b, run_date=date(2026, 4, 2), protocol_id=PROTO_B),
        }
        service = _make_service(curve_repo=curve_repo, run_repo=_run_repo_for(runs))
        service._protocol_repo.find_by_ids = AsyncMock(return_value=[
            _make_protocol(protocol_id=PROTO_ID, name="Alpha", dose_unit="uM"),
            _make_protocol(protocol_id=PROTO_B, name="Beta", dose_unit="nM"),
        ])
        from types import SimpleNamespace
        service._protocol_repo.find_effective_targets_for_protocols = AsyncMock(return_value={
            PROTO_ID: [SimpleNamespace(id=uuid.uuid4(), name="NadD")],
            PROTO_B: [],
        })

        result = await service.enrich_molecules(WS, [MOL_ID], ["any"])

        block = result[MOL_ID]["any"]
        assert [e.protocol_name for e in block.entries] == ["Beta", "Alpha"]  # 5 nM < 5 µM
        beta, alpha = block.entries
        assert (beta.value, beta.unit) == (5.0, "nM")
        assert beta.value_um == pytest.approx(0.005)
        assert (alpha.value, alpha.unit, alpha.value_um) == (5.0, "uM", 5.0)
        assert alpha.label == "IC50"
        assert alpha.curve_class == "full" and beta.curve_class == "partial"
        assert alpha.target_names == ["NadD"] and beta.target_names == []
        assert alpha.source == "dose_response"
        assert alpha.readout_definition_id == RD_ID
        assert alpha.run_count == 1

    @pytest.mark.asyncio
    async def test_any_absent_when_molecule_has_no_curves(self) -> None:
        curve_repo = AsyncMock()
        curve_repo.find_all_curves_for_molecules = AsyncMock(return_value={})
        service = _make_service(curve_repo=curve_repo)
        result = await service.enrich_molecules(WS, [MOL_ID], ["any"])
        assert result == {}
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest tests/unit/application/screening/test_molecule_activity_service.py::TestEnrichMoleculesAnyColumn -q`
Expected: FAIL (`KeyError: 'any'` or similar).

- [ ] **Step 3: Domain types** — in `activity_types.py`, after `ActivityValue`:

```python
@dataclass(frozen=True)
class AnyProtocolEntry:
    """One protocol's measurement of a molecule, for the search grid's
    "Active in" column. Value is in the protocol's NATIVE unit; ``value_um``
    is the µM normalization used only for ordering."""

    protocol_id: uuid.UUID
    protocol_name: str
    protocol_type: str
    target_names: list[str]
    label: str  # "IC50", "EC90", "% Inhibition"
    source: str  # "dose_response" | "readout"
    readout_definition_id: uuid.UUID
    value: float | None
    qualifier: str | None
    unit: str | None
    value_um: float | None
    curve_class: str | None  # DR only
    run_count: int


@dataclass(frozen=True)
class AnyProtocolActivity:
    """Value of the ``any`` column: entries sorted best-first
    (``value_um`` asc, NULL last, then label)."""

    entries: list[AnyProtocolEntry]
```

- [ ] **Step 4: Service** — in `molecule_activity_service.py`:

Imports: add `AnyProtocolActivity, AnyProtocolEntry` to the `activity_types` import; add `from cellar.domain.shared.enums import ConcentrationUnit`.

Signature of both `enrich_molecules` and `_enrich_molecules`: add `any_readout_groups: list[tuple[str, str | None]] | None = None,` after `run_scopes`, pass it through, and widen the return annotation to `dict[uuid.UUID, dict[str, ActivityValue | AnyProtocolActivity]]`. Extend the `enrich_molecules` docstring's format list with:

```
          - "any" -- one AnyProtocolActivity listing every protocol the
            molecule has DR curves in (plus readout groups named in
            ``any_readout_groups``), best first, native units.
```

In `_enrich_molecules`, after the column-spec parsing loop add `want_any = "any" in protocol_columns`. After the existing DR fetch block, add:

```python
        # "any" column: every curve the molecule has, in every protocol.
        any_curves: dict[uuid.UUID, dict[uuid.UUID, list[DoseResponseCurve]]] = {}
        any_runs: dict[uuid.UUID, Run] = {}
        any_protos: dict[uuid.UUID, Any] = {}
        any_targets: dict[uuid.UUID, list[str]] = {}
        if want_any:
            any_curves = await self._curve_repo.find_all_curves_for_molecules(
                workspace_id, molecule_ids, readout_definition_ids=None, run_scope=RunScope.all()
            )
            any_run_ids = list(
                {c.run_id for by_rd in any_curves.values() for cs in by_rd.values() for c in cs}
            )
            any_runs = (
                await self._run_repo.find_by_ids(workspace_id, any_run_ids) if any_run_ids else {}
            )
            any_proto_ids = list(
                {c.protocol_id for by_rd in any_curves.values() for cs in by_rd.values() for c in cs}
            )
            if any_proto_ids:
                for p in await self._protocol_repo.find_by_ids(workspace_id, any_proto_ids):
                    any_protos[p.id] = p
                targets = await self._protocol_repo.find_effective_targets_for_protocols(
                    workspace_id, any_proto_ids
                )
                any_targets = {pid: [t.name for t in refs] for pid, refs in targets.items()}
```

In the per-molecule build loop, after the DR columns block and before `if mol_activity:`:

```python
            if want_any:
                block = self._build_any_activity(
                    any_curves.get(mol_id, {}),
                    runs_by_id=any_runs,
                    protos=any_protos,
                    targets=any_targets,
                    selection_rule=selection_rule,
                    qualifier_handling=qualifier_handling,
                )
                if block is not None:
                    mol_activity["any"] = block
```

Change `mol_activity`'s annotation to `dict[str, ActivityValue | AnyProtocolActivity]` and `result`'s accordingly. Add the builder as a method next to `_build_dr_activity`:

```python
    def _build_any_activity(
        self,
        by_rd: dict[uuid.UUID, list[DoseResponseCurve]],
        *,
        runs_by_id: dict[uuid.UUID, Run],
        protos: dict[uuid.UUID, Any],
        targets: dict[uuid.UUID, list[str]],
        selection_rule: SelectionRule,
        qualifier_handling: QualifierHandling,
    ) -> AnyProtocolActivity | None:
        """One entry per (protocol, DR readout-def) the molecule has curves in,
        collapsed per readout-def by the same run aggregation as the DR
        columns. Native unit from the protocol; µM only for ordering."""
        entries: list[AnyProtocolEntry] = []
        for rd_id, curves in by_rd.items():
            resolved = self._build_resolved_runs(curves, runs_by_id)
            if not resolved:
                continue
            proto = protos.get(curves[0].protocol_id)
            unit = proto.dose_unit.value if proto is not None else "uM"
            av = self._build_dr_activity(
                resolved_runs=resolved,
                unit=unit,
                selection_rule=selection_rule,
                qualifier_handling=qualifier_handling,
            )
            if av is None:
                continue
            entries.append(
                AnyProtocolEntry(
                    protocol_id=curves[0].protocol_id,
                    protocol_name=proto.name if proto is not None else "",
                    protocol_type=proto.protocol_type.value if proto is not None else "",
                    target_names=targets.get(curves[0].protocol_id, []),
                    label=_primary_intercept_label(av),
                    source="dose_response",
                    readout_definition_id=rd_id,
                    value=av.value,
                    qualifier=av.qualifier,
                    unit=unit,
                    value_um=_value_to_micromolar(av.value, unit),
                    curve_class=av.curve_params.curve_class if av.curve_params else None,
                    run_count=av.run_count,
                )
            )
        if not entries:
            return None
        entries.sort(key=lambda e: (e.value_um is None, e.value_um or 0.0, e.label))
        return AnyProtocolActivity(entries=entries)
```

and two module-level helpers (bottom of the file):

```python
def _primary_intercept_label(av: ActivityValue) -> str:
    """Label of the cell's primary intercept: the protocol's declared label
    when the curve carries it, else the curve type upper-cased ("IC50")."""
    first = (av.intercept_values or [None])[0]
    if isinstance(first, dict):
        spec = first.get("spec") or {}
        if spec.get("label"):
            return str(spec["label"])
        if spec.get("kind") and spec.get("level") is not None:
            return f"{str(spec['kind']).upper()}{int(float(spec['level']))}"
    return (av.curve_type or "").upper()


def _value_to_micromolar(value: float | None, unit: str) -> float | None:
    """µM for ordering only (Python-side twin of the SQL CASE in _activity_query). mg/mL needs molecular weight, which this
    service does not load — those entries sort last (None)."""
    if value is None:
        return None
    try:
        factor = ConcentrationUnit(unit).micromolar_factor
    except ValueError:
        return None
    return None if factor is None else value * factor
```

Check `av.curve_params.curve_class` is a plain string (it is set from `rep.curve_class`, which `_build_resolved_runs` stores as `c.curve_class.value`).

- [ ] **Step 5: Run tests + lint**

Run: `cd backend && uv run pytest tests/unit/application/screening/test_molecule_activity_service.py -q && uv run ruff check src/cellar/application/screening/molecule_activity_service.py src/cellar/domain/screening_assay/activity_types.py && uv run ruff format --check src/cellar/application/screening/molecule_activity_service.py src/cellar/domain/screening_assay/activity_types.py`
Expected: PASS, clean. Then `uv run pytest tests/unit -q` — only the pre-existing PDF renderer failure may remain (`libgobject`, recorded in `docs/backlog/preexisting-test-lint-failures-main.md`).

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(search): 'any' activity column — per-protocol DR entries, native units, best first

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- backend/src/cellar/domain/screening_assay/activity_types.py backend/src/cellar/application/screening/molecule_activity_service.py backend/tests/unit/application/screening/test_molecule_activity_service.py
```

---

### Task 7: Backend — readout entries when the criterion names a readout group

**Files:**
- Modify: `backend/src/cellar/domain/screening_assay/repository.py` (`ReadoutDataRepository` protocol, next to `find_aggregated_by_molecules`)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/readout_data_repository.py`
- Modify: `backend/src/cellar/application/screening/molecule_activity_service.py`
- Modify: `backend/src/cellar/application/research_organization/execute_search.py`
- Test: `backend/tests/unit/application/screening/test_molecule_activity_service.py`, `backend/tests/api/test_search.py`

**Interfaces:**
- Consumes: `normalize_readout_name` (Task 2) — import it in the reader from `cellar.infrastructure.persistence.sqlalchemy.chemical_registration._activity_query`; `_seed_numeric_readout` (Task 3).
- Produces:
  - `ReadoutDataRepository.find_aggregated_by_molecules_and_names(workspace_id, molecule_ids, groups: list[tuple[str, str | None]]) -> dict[uuid.UUID, list[tuple[uuid.UUID, AggregatedReadout]]]` — value list = `(protocol_id, aggregated)` per matching readout-def.
  - `collect_any_readout_groups(criteria: list[dict]) -> list[tuple[str, str | None]]` in `execute_search.py`.

- [ ] **Step 1: Failing unit test** — append to `TestEnrichMoleculesAnyColumn`:

```python
    @pytest.mark.asyncio
    async def test_any_includes_named_readout_groups(self) -> None:
        from cellar.domain.screening_assay.activity_types import AggregatedReadout

        curve_repo = AsyncMock()
        curve_repo.find_all_curves_for_molecules = AsyncMock(return_value={})
        service = _make_service(curve_repo=curve_repo)
        rd_x = uuid.uuid4()
        service._readout_repo.find_aggregated_by_molecules_and_names = AsyncMock(return_value={
            MOL_ID: [(PROTO_B, AggregatedReadout(
                readout_definition_id=rd_x, readout_name="% Inhibition", value=82.0,
                qualifier=None, unit="%", aggregation="mean", data_point_count=3))]
        })
        service._protocol_repo.find_by_ids = AsyncMock(return_value=[
            _make_protocol(protocol_id=PROTO_B, name="Beta", dose_unit="uM")])
        service._protocol_repo.find_effective_targets_for_protocols = AsyncMock(return_value={})

        result = await service.enrich_molecules(
            WS, [MOL_ID], ["any"], any_readout_groups=[("% inhibition", "%")]
        )
        [entry] = result[MOL_ID]["any"].entries
        assert (entry.label, entry.value, entry.unit, entry.source) == ("% Inhibition", 82.0, "%", "readout")
        assert entry.value_um is None and entry.curve_class is None
        assert entry.protocol_name == "Beta" and entry.run_count == 3
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest tests/unit/application/screening/test_molecule_activity_service.py::TestEnrichMoleculesAnyColumn -q`
Expected: the new test FAILS.

- [ ] **Step 3: Repository protocol** — in `domain/screening_assay/repository.py`, after `find_aggregated_by_molecules`:

```python
    async def find_aggregated_by_molecules_and_names(
        self,
        workspace_id: uuid.UUID,
        molecule_ids: list[uuid.UUID],
        groups: list[tuple[str, str | None]],
    ) -> dict[uuid.UUID, list[tuple[uuid.UUID, AggregatedReadout]]]:
        """Raw-layer aggregation across EVERY protocol whose readout-def matches
        a ``(normalized_name, unit)`` group. Returns, per molecule, one
        ``(protocol_id, AggregatedReadout)`` per matching readout-def."""
        ...
```

- [ ] **Step 4: Implementation** — in `readout_data_repository.py`, after `find_aggregated_by_molecules`:

```python
    async def find_aggregated_by_molecules_and_names(
        self,
        workspace_id: uuid.UUID,
        molecule_ids: list[uuid.UUID],
        groups: list[tuple[str, str | None]],
    ) -> dict[uuid.UUID, list[tuple[uuid.UUID, AggregatedReadout]]]:
        from cellar.infrastructure.persistence.sqlalchemy.chemical_registration._activity_query import (
            normalize_readout_name,
        )
        from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
            ReadoutDefinitionModel,
        )

        if not molecule_ids or not groups:
            return {}
        wanted = {(normalize_readout_name(n), u or "") for n, u in groups}
        norm_name = func.lower(
            func.btrim(func.regexp_replace(ReadoutDefinitionModel.name, r"\s+", " ", "g"))
        ).label("norm_name")
        unit_key = func.coalesce(ReadoutDefinitionModel.unit, "").label("unit_key")
        stmt = (
            select(
                ReadoutDataModel.molecule_id,
                ReadoutDataModel.readout_definition_id,
                ReadoutDefinitionModel.protocol_id,
                ReadoutDefinitionModel.name.label("readout_name"),
                ReadoutDefinitionModel.aggregation,
                ReadoutDefinitionModel.unit,
                norm_name,
                unit_key,
                func.avg(ReadoutDataModel.value_numeric).label("avg_val"),
                func.min(ReadoutDataModel.value_numeric).label("min_val"),
                func.max(ReadoutDataModel.value_numeric).label("max_val"),
                func.count(ReadoutDataModel.value_numeric).label("count_val"),
            )
            .join(
                ReadoutDefinitionModel,
                ReadoutDataModel.readout_definition_id == ReadoutDefinitionModel.id,
            )
            .where(
                ReadoutDataModel.workspace_id == workspace_id,
                ReadoutDataModel.molecule_id.in_(molecule_ids),
                ReadoutDataModel.normalization_applied.is_(None),
                ReadoutDataModel.is_outlier == False,  # noqa: E712
                sa.tuple_(norm_name, unit_key).in_(list(wanted)),
            )
            .group_by(
                ReadoutDataModel.molecule_id,
                ReadoutDataModel.readout_definition_id,
                ReadoutDefinitionModel.protocol_id,
                ReadoutDefinitionModel.name,
                ReadoutDefinitionModel.aggregation,
                ReadoutDefinitionModel.unit,
            )
        )
        rows = (await self._uow.session.execute(stmt)).all()
        out: dict[uuid.UUID, list[tuple[uuid.UUID, AggregatedReadout]]] = {}
        for row in rows:
            agg = row.aggregation or "mean"
            val = row.min_val if agg == "min" else row.max_val if agg == "max" else row.avg_val
            out.setdefault(row.molecule_id, []).append(
                (
                    row.protocol_id,
                    AggregatedReadout(
                        readout_definition_id=row.readout_definition_id,
                        readout_name=row.readout_name,
                        value=val,
                        qualifier=None,
                        unit=row.unit,
                        aggregation=agg,
                        data_point_count=row.count_val,
                    ),
                )
            )
        return out
```

If `sa` is not imported in that module, `import sqlalchemy as sa`. If `tuple_(...).in_(...)` on labelled expressions fails at runtime, replace the `.where(...)` tuple clause with `sa.or_(*[sa.and_(norm_name == n, unit_key == u) for n, u in wanted])`.

- [ ] **Step 5: Service** — in `_enrich_molecules`, inside the `if want_any:` fetch block, after the targets lookup add:

```python
            any_readouts: dict[uuid.UUID, list[tuple[uuid.UUID, AggregatedReadout]]] = {}
            if any_readout_groups:
                any_readouts = await self._readout_repo.find_aggregated_by_molecules_and_names(
                    workspace_id, molecule_ids, any_readout_groups
                )
                extra_proto_ids = [
                    pid
                    for lst in any_readouts.values()
                    for pid, _ in lst
                    if pid not in any_protos
                ]
                if extra_proto_ids:
                    for p in await self._protocol_repo.find_by_ids(workspace_id, extra_proto_ids):
                        any_protos[p.id] = p
                    more = await self._protocol_repo.find_effective_targets_for_protocols(
                        workspace_id, extra_proto_ids
                    )
                    any_targets.update({pid: [t.name for t in refs] for pid, refs in more.items()})
```

(declare `any_readouts: dict[...] = {}` next to the other `any_*` declarations so it exists when `want_any` is False). Pass `readouts=any_readouts.get(mol_id, [])` into `_build_any_activity` and extend it:

```python
    def _build_any_activity(
        self,
        by_rd: dict[uuid.UUID, list[DoseResponseCurve]],
        *,
        readouts: list[tuple[uuid.UUID, AggregatedReadout]] | None = None,
        runs_by_id: dict[uuid.UUID, Run],
        ...
    ) -> AnyProtocolActivity | None:
        entries: list[AnyProtocolEntry] = []
        ...  # DR loop unchanged
        for proto_id, agg in readouts or []:
            proto = protos.get(proto_id)
            entries.append(
                AnyProtocolEntry(
                    protocol_id=proto_id,
                    protocol_name=proto.name if proto is not None else "",
                    protocol_type=proto.protocol_type.value if proto is not None else "",
                    target_names=targets.get(proto_id, []),
                    label=agg.readout_name,
                    source="readout",
                    readout_definition_id=agg.readout_definition_id,
                    value=agg.value,
                    qualifier=agg.qualifier,
                    unit=agg.unit,
                    value_um=None,
                    curve_class=None,
                    run_count=agg.data_point_count,
                )
            )
        if not entries:
            return None
        entries.sort(key=lambda e: (e.value_um is None, e.value_um or 0.0, e.label))
        return AnyProtocolActivity(entries=entries)
```

- [ ] **Step 6: execute_search** — in `execute_search.py` add a helper next to `_collect_run_scopes`:

```python
def collect_any_readout_groups(criteria: list[dict]) -> list[tuple[str, str | None]]:
    """``(readout_name, unit)`` groups named by any-protocol activity criteria
    (``protocol_id`` None + ``readout_data`` where with ``readout_name``).
    Feeds the ``any`` column so readout entries appear only when asked for."""
    groups: list[tuple[str, str | None]] = []

    def _visit(c: dict) -> None:
        if c.get("type") != "activity" or c.get("protocol_id") is not None:
            return
        where = c.get("where") if isinstance(c.get("where"), list) else []
        for w in where:
            if not isinstance(w, dict) or w.get("source") != "readout_data":
                continue
            name = w.get("readout_name")
            if isinstance(name, str) and name.strip():
                key = (name, w.get("unit") or None)
                if key not in groups:
                    groups.append(key)

    walk_criteria(criteria, _visit)
    return groups
```

and in the enrichment call site:

```python
                run_scopes = _collect_run_scopes(criteria, drc_cols)
                any_groups = collect_any_readout_groups(criteria)
                activity_data_raw = await self._activity_service.enrich_molecules(
                    input.workspace_id,
                    mol_ids,
                    input.protocol_columns,
                    selection_rule=input.aggregation,
                    run_scopes=run_scopes or None,
                    any_readout_groups=any_groups or None,
                )
```

`asdict(v)` already serializes the new dataclasses (nested dataclass + UUID handled by FastAPI's encoder, as with `ActivityValue.runs`).

- [ ] **Step 7: API test** — append to `TestActivityAnyProtocol` in `tests/api/test_search.py`:

```python
    async def test_any_column_returns_entries(
        self, client: AsyncClient, org_id: str, uow: AsyncUnitOfWork, workspace_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/api/v1/molecules",
            json={"name": "AnyColMol", "smiles": "CCCCCCCO", "originating_org_id": org_id},
        )
        mol_id = str(resp.json()["molecule"]["id"])
        await _seed_multi_run_dr(uow, workspace_id=workspace_id, molecule_id=uuid.UUID(mol_id),
                                 run_count=1, intercepts=[("ic", 50, 5.0)])
        await _seed_multi_run_dr(uow, workspace_id=workspace_id, molecule_id=uuid.UUID(mol_id),
                                 run_count=1, dose_unit="nM", intercepts=[("ic", 50, 5.0)])
        await _seed_numeric_readout(uow, workspace_id=workspace_id, molecule_id=uuid.UUID(mol_id),
                                    readout_name="% Inhibition", unit="%", value=77.0)

        body = {
            "query": {"criteria": [{"type": "activity", "protocol_id": None,
                                    "where": [{"source": "readout_data", "readout_name": "% inhibition",
                                               "unit": "%", "operator": "gt", "value": 50}]}],
                      "logic": "and"},
            "protocol_columns": ["any"],
        }
        res = await client.post("/api/v1/search/execute", json=body)
        assert res.status_code == 200, res.text
        entries = res.json()["activity_data"][mol_id]["any"]["entries"]
        # nM curve first (0.005 µM), then µM curve, readouts (no µM) last.
        assert [e["unit"] for e in entries] == ["nM", "uM", "%"]
        assert entries[2]["label"] == "% Inhibition" and entries[2]["value"] == 77.0
        assert all(e["protocol_name"] for e in entries)
```

- [ ] **Step 8: Run everything**

Run: `cd backend && uv run pytest tests/unit/application/screening/test_molecule_activity_service.py tests/unit/application/research_organization -q && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api/test_search.py -q && uv run ruff check src tests/api/test_search.py tests/unit/application/screening/test_molecule_activity_service.py && uv run ruff format --check src`
Expected: PASS, clean.

- [ ] **Step 9: Commit**

```bash
git commit -m "feat(search): 'any' column adds readout entries for readout groups named in the criterion

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- backend/src/cellar/domain/screening_assay/repository.py backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/readout_data_repository.py backend/src/cellar/application/screening/molecule_activity_service.py backend/src/cellar/application/research_organization/execute_search.py backend/tests/unit/application/screening/test_molecule_activity_service.py backend/tests/api/test_search.py
```

---

### Task 8: Backend — export tolerates the `any` token

**Files:**
- Modify: `backend/src/cellar/application/export/row_streams/search_results.py`
- Test: `backend/tests/unit/application/export/row_streams/test_search_results.py`

**Interfaces:**
- Consumes: `_expand_protocol_column(token, by_id)`, `_cell_value(spec, raw)`, `ColumnSpec`.
- Produces: token `any` → one `ColumnSpec(key="any::text", header="Active in", kind="text")`; cell renders `"Beta: IC50 5 nM; Alpha: IC50 5 uM"`.

- [ ] **Step 1: Failing test** — append:

```python
def test_any_token_expands_to_one_text_column():
    cols = _expand_protocol_column("any", {})
    assert [(c.key, c.header, c.kind) for c in cols] == [("any::text", "Active in", "text")]


def test_cell_value_any_joins_entries():
    spec = ColumnSpec(key="any::text", header="Active in", kind="text")
    raw = {"activity": {"any": {"entries": [
        {"protocol_name": "Beta", "label": "IC50", "value": 5.0, "unit": "nM", "qualifier": None},
        {"protocol_name": "Alpha", "label": "IC50", "value": 5.0, "unit": "uM", "qualifier": ">"},
        {"protocol_name": "Gamma", "label": "% Inhibition", "value": None, "unit": "%", "qualifier": None},
    ]}}}
    assert _cell_value(spec, raw) == "Beta: IC50 5 nM; Alpha: IC50 >5 uM; Gamma: % Inhibition —"
```

Import `_expand_protocol_column` alongside `_cell_value` at the top of the test file.

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest tests/unit/application/export/row_streams/test_search_results.py -q -k any`
Expected: FAIL.

- [ ] **Step 3: Implement** — in `_expand_protocol_column`, before `parts = token.split(":")`:

```python
    if token == "any":
        return [ColumnSpec(key="any::text", header="Active in", kind="text")]
```

In `_cell_value`, after `col_token, suffix = spec.key.rsplit("::", 1)`:

```python
    if col_token == "any":
        block = (raw.get("activity") or {}).get("any") or {}
        return _format_any_entries(block.get("entries") or [])
```

and add the helper near `_display_value`:

```python
def _format_any_entries(entries: list[dict]) -> str:
    """"Protocol: LABEL value unit" per entry, joined by "; " — the text
    form of the grid's "Active in" cell."""
    parts: list[str] = []
    for e in entries:
        value = e.get("value")
        if value is None:
            shown = "—"
        else:
            q = e.get("qualifier") or ""
            q = "" if q == "=" else q
            num = f"{value:g}"
            unit = e.get("unit") or ""
            shown = f"{q}{num}{' ' + unit if unit else ''}"
        parts.append(f"{e.get('protocol_name') or 'Protocol'}: {e.get('label') or ''} {shown}".rstrip())
    return "; ".join(parts)
```

- [ ] **Step 4: Run + lint**

Run: `cd backend && uv run pytest tests/unit/application/export -q && uv run ruff check src/cellar/application/export/row_streams/search_results.py && uv run ruff format --check src/cellar/application/export/row_streams/search_results.py`
Expected: PASS (except the pre-existing PDF `libgobject` failure), clean.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(export): 'any' activity column exports as one 'Active in' text column

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- backend/src/cellar/application/export/row_streams/search_results.py backend/tests/unit/application/export/row_streams/test_search_results.py
```

---

### Task 9: Frontend — `any` column: types, resolver, form, cell, grid, sheet

**Files:**
- Modify: `frontend/src/features/research-organization/types/index.ts`
- Modify: `frontend/src/features/research-organization/lib/protocol-column-id.ts`
- Modify: `frontend/src/features/research-organization/components/search/search-form.tsx`
- Create: `frontend/src/features/research-organization/components/search/active-in-cell.tsx`
- Modify: `frontend/src/features/research-organization/components/search/results-grid.tsx`
- Modify: `frontend/src/features/research-organization/components/search-page.tsx`
- Test: `frontend/src/features/research-organization/lib/protocol-column-id.test.ts`, `frontend/src/features/research-organization/components/search/active-in-cell.test.tsx`

**Interfaces:**
- Produces:
  - `AnyProtocolEntry`, `AnyProtocolActivity` interfaces (client-side narrowing of the `any` blob, same justification as `ActivityValue`).
  - `ANY_COLUMN_ID = "any"` (in `protocol-column-id.ts`).
  - `anyProtocolActivity(mol: { activity?: Record<string, unknown> }): AnyProtocolActivity | undefined`.
  - `ActiveInCell({ value }: { value: AnyProtocolActivity | undefined })` React component.
  - `buildActiveInColumn(): ColDef<EnrichedMolecule>` exported from `results-grid.tsx`.

- [ ] **Step 1: Failing tests**

`protocol-column-id.test.ts` — append:

```ts
describe("any column token", () => {
  it("is ignored by resolveColumns and uniqueProtocolIds, and survives toBackendProtocolColumns", () => {
    expect(resolveColumns(["any"], [])).toEqual([]);
    expect(uniqueProtocolIds(["any"], [])).toEqual([]);
    expect(toBackendProtocolColumns(["any", "any"])).toEqual(["any"]);
  });
});
```

(import `toBackendProtocolColumns`/`uniqueProtocolIds` if the file doesn't already.)

`components/search/active-in-cell.test.tsx` — create:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { AnyProtocolActivity, AnyProtocolEntry } from "../../types";
import { ActiveInCell } from "./active-in-cell";

function entry(over: Partial<AnyProtocolEntry>): AnyProtocolEntry {
  return {
    protocol_id: "p",
    protocol_name: "Proto",
    protocol_type: "biochemical",
    target_names: [],
    label: "IC50",
    source: "dose_response",
    readout_definition_id: "rd",
    value: 1,
    qualifier: null,
    unit: "uM",
    value_um: 1,
    curve_class: "full",
    run_count: 1,
    ...over,
  };
}

describe("ActiveInCell", () => {
  it("renders a dash when empty", () => {
    render(<ActiveInCell value={undefined} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("shows at most three entries, native units, then +N more", () => {
    const value: AnyProtocolActivity = {
      entries: [
        entry({ protocol_name: "Beta", value: 5, unit: "nM", value_um: 0.005 }),
        entry({ protocol_name: "Alpha", value: 5, unit: "uM" }),
        entry({ protocol_name: "Gamma", label: "EC90", value: 12.5, curve_class: "partial" }),
        entry({ protocol_name: "Delta", value: 40 }),
        entry({ protocol_name: "Eps", value: 41 }),
      ],
    };
    render(<ActiveInCell value={value} />);
    expect(screen.getByText("Beta")).toBeInTheDocument();
    expect(screen.getByText("5 nM")).toBeInTheDocument();
    expect(screen.getByText("Gamma")).toBeInTheDocument();
    expect(screen.queryByText("Delta")).not.toBeInTheDocument();
    expect(screen.getByText("+2 more")).toBeInTheDocument();
  });

  it("greys inactive curves, prefixes qualifiers, shows single target", () => {
    const value: AnyProtocolActivity = {
      entries: [
        entry({ protocol_name: "Cyto", curve_class: "inactive", qualifier: ">", value: 100,
                target_names: ["Mtb"] }),
      ],
    };
    render(<ActiveInCell value={value} />);
    expect(screen.getByText(">100 uM")).toBeInTheDocument();
    expect(screen.getByText("Mtb")).toBeInTheDocument();
    expect(screen.getByTestId("active-in-row")).toHaveClass("text-muted-foreground");
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && pnpm exec vitest run src/features/research-organization/lib/protocol-column-id.test.ts src/features/research-organization/components/search/active-in-cell.test.tsx`
Expected: FAIL (module not found / assertions).

- [ ] **Step 3: Types** — in `types/index.ts`, after the `ActivityValue` interface:

```ts
// ─── "any" column — CLIENT-SIDE narrowing, NOT a DTO alias ─────────────────
// Same situation as ActivityValue: `activity_data` is `dict[str, dict[str, Any]]`
// on the wire, so orval emits `unknown`. Produced by
// MoleculeActivityService._build_any_activity (AnyProtocolActivity dataclass).
export interface AnyProtocolEntry {
  protocol_id: string;
  protocol_name: string;
  protocol_type: string;
  target_names: string[];
  /** "IC50", "EC90", "% Inhibition" */
  label: string;
  source: "dose_response" | "readout";
  readout_definition_id: string;
  /** Native unit of the owning protocol. */
  value: number | null;
  qualifier: string | null;
  unit: string | null;
  /** µM normalization — ordering only, never displayed. Null for readouts. */
  value_um: number | null;
  curve_class: CurveClass | null;
  run_count: number;
}

export interface AnyProtocolActivity {
  /** Best first (value_um asc, nulls last). */
  entries: AnyProtocolEntry[];
}

/** Read the "any" column off an enriched row. The activity map is typed as
 *  ActivityValue for every other key; this is the one differently-shaped
 *  entry, so it gets a single typed accessor instead of a union type that
 *  would force narrowing at every DR cell. */
export function anyProtocolActivity(mol: {
  activity?: Record<string, unknown>;
}): AnyProtocolActivity | undefined {
  const raw = mol.activity?.any;
  return raw && typeof raw === "object" && Array.isArray((raw as AnyProtocolActivity).entries)
    ? (raw as AnyProtocolActivity)
    : undefined;
}
```

Import `CurveClass` from `@/features/screening-assay/types` if not already imported in that file.

- [ ] **Step 4: Resolver** — in `protocol-column-id.ts`: export `export const ANY_COLUMN_ID = "any";` near the formatters with the comment `/** The single cross-protocol "Active in" column. Carries no protocol id. */`. `resolveColumns` already `continue`s on unknown prefixes, so `any` is ignored; `toBackendProtocolColumns` already de-dupes non-drc tokens. No other change; the test documents the behaviour.

- [ ] **Step 5: Form** — in `search-form.tsx` `deriveProtocolColumns`, replace the ponytail comment + `if (!c.protocol_id) continue;` with:

```ts
    if (c.protocol_id === null) {
      add(ANY_COLUMN_ID); // one "Active in" column for every any-protocol row
      continue;
    }
    if (!c.protocol_id) continue;
```

Import `ANY_COLUMN_ID` from `../../lib/protocol-column-id`.

- [ ] **Step 6: Cell** — create `components/search/active-in-cell.tsx`:

```tsx
"use client";

import type { CurveClass } from "@/features/screening-assay/types";
import { cn } from "@/shared/lib/utils";
import type { AnyProtocolActivity, AnyProtocolEntry } from "../../types";

const MAX_ROWS = 3;

/** Curve-class dot: trustworthy → green, partial → amber, everything else grey. */
const DOT: Record<CurveClass, string> = {
  full: "bg-emerald-500",
  partial: "bg-amber-500",
  bell_shaped: "bg-muted-foreground/50",
  inactive: "bg-muted-foreground/50",
};

function formatValue(e: AnyProtocolEntry): string {
  if (e.value == null) return "—";
  const q = e.qualifier && e.qualifier !== "=" ? e.qualifier : "";
  return `${q}${Number(e.value.toPrecision(3))}${e.unit ? ` ${e.unit}` : ""}`;
}

/** One line per protocol the compound was measured in: name · label · native
 *  value · curve-class dot. Best first (server-sorted). Inactive curves are
 *  muted. No sparklines here — the detail sheet has the plots. */
export function ActiveInCell({ value }: { value: AnyProtocolActivity | undefined }) {
  const entries = value?.entries ?? [];
  if (entries.length === 0) return <span className="text-muted-foreground">&mdash;</span>;
  const shown = entries.slice(0, MAX_ROWS);
  const more = entries.length - shown.length;
  return (
    <div className="flex flex-col gap-0.5 py-1 text-xs leading-tight">
      {shown.map((e) => {
        const inactive = e.curve_class === "inactive";
        const singleTarget = e.target_names.length === 1 ? e.target_names[0] : null;
        return (
          <div
            key={`${e.protocol_id}:${e.readout_definition_id}`}
            data-testid="active-in-row"
            className={cn("flex min-w-0 items-center gap-1.5", inactive && "text-muted-foreground")}
          >
            {e.curve_class ? (
              <span className={cn("h-2 w-2 shrink-0 rounded-full", DOT[e.curve_class])} aria-hidden />
            ) : (
              <span className="h-2 w-2 shrink-0" aria-hidden />
            )}
            <span className="truncate">{e.protocol_name}</span>
            {singleTarget && (
              <span className="shrink-0 rounded bg-muted px-1 text-[10px] text-muted-foreground">
                {singleTarget}
              </span>
            )}
            <span className="ml-auto shrink-0 text-muted-foreground">{e.label}</span>
            <span className="shrink-0 font-mono">{formatValue(e)}</span>
          </div>
        );
      })}
      {more > 0 && <span className="text-muted-foreground">+{more} more</span>}
    </div>
  );
}
```

Check the `cn` import path matches the one `protocol-section.tsx` uses.

- [ ] **Step 7: Grid** — in `results-grid.tsx`:
  - Import `ActiveInCell` and `anyProtocolActivity`, `ANY_COLUMN_ID`.
  - Add, after `buildMoleculeColumn`:

```tsx
/** The cross-protocol "Active in" column. Sorts client-side by the best
 *  µM-normalized entry (nulls last), like the other activity columns. */
export function buildActiveInColumn(): ColDef<EnrichedMolecule> {
  return {
    headerName: "Active in",
    colId: ANY_COLUMN_ID,
    width: 320,
    filter: false,
    autoHeight: true,
    valueGetter: (p) => {
      const first = p.data ? anyProtocolActivity(p.data)?.entries[0] : undefined;
      return first?.value_um ?? null;
    },
    comparator: (a: number | null, b: number | null) => {
      if (a == null && b == null) return 0;
      if (a == null) return 1;
      if (b == null) return -1;
      return a - b;
    },
    cellRenderer: (params: ICellRendererParams<EnrichedMolecule>) => (
      <ActiveInCell value={params.data ? anyProtocolActivity(params.data) : undefined} />
    ),
  };
}
```

  - In the `columnDefs` memo: `const activeIn = protocolColumns.includes(ANY_COLUMN_ID) ? [buildActiveInColumn()] : [];` and return `[molecule, ...sim, ...activeIn, ...props, ...protoGroups]`.
  - `EnrichedMolecule` in this file is `Molecule & { activity?: Record<string, ActivityValue> }`; `anyProtocolActivity` accepts `Record<string, unknown>` so it is assignable. If `tsc` complains about `autoHeight` with fixed `rowHeight`, drop `autoHeight` (the cell fits in the existing row height at 3 lines of `text-xs`).

- [ ] **Step 8: Sheet** — in `search-page.tsx`, find where the row click sets the detail molecule (the `onRowClick` handler passed to `ResultsGrid`) and where `<CompoundDetailSheet visibleProtocolIds={visibleProtocolIds} ...>` is rendered. Add state:

```ts
  const [clickedAnyProtocolIds, setClickedAnyProtocolIds] = useState<string[]>([]);
```

In the row-click handler, before/after setting the detail molecule:

```ts
      setClickedAnyProtocolIds(
        anyProtocolActivity(molecule)?.entries.map((e) => e.protocol_id) ?? [],
      );
```

and pass the union to the sheet:

```tsx
  const sheetVisibleProtocolIds = useMemo(
    () => [...new Set([...visibleProtocolIds, ...clickedAnyProtocolIds])],
    [visibleProtocolIds, clickedAnyProtocolIds],
  );
  // ...
  <CompoundDetailSheet visibleProtocolIds={sheetVisibleProtocolIds} ... />
```

Import `anyProtocolActivity` from `../types`.

- [ ] **Step 9: Verify**

Run: `cd frontend && pnpm exec vitest run src/features/research-organization && pnpm exec tsc --noEmit -p . && pnpm lint; echo "lint exit=$?"`
Expected: all pass, tsc clean, lint exit 0. If biome flags import order, run `pnpm exec biome check --write <file>` on the touched files only (never `--unsafe`).

- [ ] **Step 10: Commit**

```bash
git commit -m "feat(search): 'Active in' results column for any-protocol searches; matched protocols expand in the detail sheet

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- frontend/src/features/research-organization/types/index.ts frontend/src/features/research-organization/lib/protocol-column-id.ts frontend/src/features/research-organization/lib/protocol-column-id.test.ts frontend/src/features/research-organization/components/search/search-form.tsx frontend/src/features/research-organization/components/search/active-in-cell.tsx frontend/src/features/research-organization/components/search/active-in-cell.test.tsx frontend/src/features/research-organization/components/search/results-grid.tsx frontend/src/features/research-organization/components/search-page.tsx
```

---

### Task 10: End-to-end check in Chrome + push

**Files:** none (verification only).

- [ ] **Step 1: Servers.** Check `curl -s localhost:8000/version` and `curl -s -o /dev/null -w '%{http_code}' localhost:3000`. If the backend is down: `make dev-be` from the repo root (it must go through make so `.env` exports the Sentinel key). The frontend hot-reloads. If the backend was already up before Part 2's service changes, it auto-reloads (`--reload`); confirm `/version` reports the current SHA.

- [ ] **Step 2: Walkthrough** (Claude-in-Chrome, new tab on `http://localhost:3000/search`):
  1. Protocol picker → "Any protocol". Live count shows ~145 on the local dataset.
  2. "add filter" → where select lists "IC50 · N protocols", "EC50 · …", "EC90 · …", numeric readouts with counts, then Curve Class.
  3. Pick "IC50 · N protocols", `<` 1 → Search. Expect a 200, an "Active in" column between Molecule and the property columns, rows sorted best first, each row showing protocol name, "IC50", native value with unit, and a green/amber/grey dot.
  4. Click the "Active in" header → rows re-order by best value; click again → reverse.
  5. Click a row → detail sheet opens with the matched protocol's curve expanded under the selected section, others collapsed.
  6. Switch the where to "Curve Class" Full+Partial → Search → column still populated.
  7. Export toolbar → CSV → confirm the request returns 200 (read network requests) — the file itself can't be opened from the sandbox; the API test in Task 8 covers the content.
- [ ] **Step 3: Backend log** — `grep -c '"path": "/api/v1/search/execute", "status_code": 200' .logs/backend.log` increases; no 500s: `grep '"path": "/api/v1/search' .logs/backend.log | grep -v '"status_code": 200'` prints nothing new.

- [ ] **Step 4: Push**

```bash
git push origin feat/any-protocol-activity-search
```

Report what was verified and anything skipped.
