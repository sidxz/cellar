# SAR Unit B — frontend atomic swap + server-side filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **Execute from a fresh session** (clean context). Bring up the backend on `:8000` + the dev Postgres first.

**Goal:** Rewire the SAR workbench table **and** heatmap to the Unit-A server endpoints (server-paginated table via AG-Grid Infinite Row Model, server-aggregated heatmap), add server-side filtering, and delete the client-side compute — so SAR is correct over the **full collection** of any size.

**Architecture:** `SarView` orchestrates `core → useDecompositionRun` (job-poll) and `colorSpec → useActivityProjection` (job-poll), then feeds `runId`/`projectionId`/`labels`/`counts` into the table + heatmap. The table is an AG-Grid Infinite Row Model whose `IDatasource.getRows` POSTs `/rows`; the heatmap reads server cells from `/heatmap`. The shared `DataGrid` gains one additive `datasource` prop. All renderers (`buildRGroupColumns`, `potencyShade`, `snapshotFromActivity`, `fragmentDisplay`, axis pickers, `CurveExpandDialog`) are kept verbatim — only the data source changes. The backend `/rows` gains: server-side **filtering**, a per-row **`activity_snapshot`**, and a response-level **`activity_reference`** (so the plot column + potency shading work under pagination — the same shape the `/search` grid already returns).

**Tech Stack:** Frontend — Next.js 16 / React 19 / TypeScript / AG Grid Community 35.2 (Infinite Row Model) / TanStack Query v5 / orval / vitest / Playwright. Backend — Python 3.13 / SQLAlchemy 2.0 async / FastAPI / pytest. FE commands run from `frontend/`; BE from `backend/`.

**Spec:** `docs/superpowers/specs/2026-06-15-sar-unit-b-frontend-swap-design.md`.
**Spec refinement (this plan):** the table's potency **plot column + shading + row-click curve-expand** need per-row data that paginated `/rows` didn't return. So `/rows` is extended with `activity_snapshot` (per row, the stored `ActivityValue` wire shape) + `activity_reference` (response-level min scalar over the filtered set) — precedented by the `/search` grid's `activity_data`. Documented in Tasks 1–2.

**Commit convention:** explicit pathspec every commit; FE commits from `frontend/`, BE from `backend/`; trailer:
`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

## File Structure

**Backend — modify:**
- `backend/src/cellar/application/sar_analysis/decomposition_rows.py` — `DecompositionRow.activity_snapshot`; `FetchDecompositionRowsInput.filter`; `FetchDecompositionRowsOutput.activity_reference`; reader Protocol `fetch_rows`/`count_rows`/`activity_reference` gain `filter`; thread through the use case.
- `backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/decomposition_row_reader.py` — `_apply_filter`, a shared `_filtered_base`, `activity_snapshot` select, `activity_reference` method.
- `backend/src/cellar/interface/routes/sar_analysis.py` — `DecompositionRowView.activity_snapshot`; `DecompositionRowsResponse.activity_reference`; thread `filter`.
- Tests: extend `backend/tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py` + `backend/tests/api/test_sar_analysis_routes.py`.

**Frontend — create:**
- `frontend/src/features/sar-analysis/lib/ag-filter-model.ts` — `agFilterModelToParam`.
- `frontend/src/features/sar-analysis/hooks/use-decomposition-run.ts`
- `frontend/src/features/sar-analysis/hooks/use-activity-projection.ts`
- `frontend/src/features/sar-analysis/hooks/use-heatmap-aggregation.ts`
- `frontend/src/features/sar-analysis/hooks/use-decomposition-rows.ts`
- Tests: one `*.test.ts(x)` per file above (vitest), under the feature's `__tests__`/colocated convention.

**Frontend — modify:**
- `frontend/src/shared/components/data-grid/data-grid.tsx` — additive `datasource` prop.
- `frontend/src/features/sar-analysis/components/sar-view.tsx` — orchestration rewrite.
- `frontend/src/features/sar-analysis/components/rgroup-table.tsx` — server datasource; keep renderers.
- `frontend/src/features/sar-analysis/components/rgroup-heatmap.tsx` — server cells; keep renderers.

**Frontend — delete:**
- `frontend/src/features/sar-analysis/hooks/use-sar-activity.ts`
- `frontend/src/features/sar-analysis/hooks/use-rgroup-decomposition.ts`
- `frontend/src/features/sar-analysis/lib/rgroup-heatmap-grid.ts` (`buildHeatmapGrid`/`heatmapCellKey`)
- `buildRGroupRows` (from `rgroup-table.tsx`), `bestMoleculeId` (from `rgroup-heatmap.tsx`)
- their tests; prune any dangling `model/index.ts` barrel lines after orval regen.

**Frontend — regenerate:** `pnpm generate:api` (Task 3) → new DTOs + endpoint fns for `/sar/activity-projection`, `/sar/decomposition/{run_id}/heatmap`, the `projection_id`/`activity`/`activity_snapshot`/`activity_reference` row fields.

---

## Task 0: Pre-flight

- [ ] **Step 1: Confirm the environment + baseline**

Run:
```bash
cd backend && uv run alembic heads        # expect 058_sar_activity_projections (head)
cd ../frontend && pnpm -v && node -v       # toolchain present
# backend must be running on :8000 for orval (Task 3): in another shell, `make dev-be` or the project's run cmd
curl -sf http://localhost:8000/openapi.json >/dev/null && echo "openapi reachable" || echo "START THE BACKEND on :8000"
```
Expected: alembic head `058`; openapi reachable. If the backend isn't up, start it before Task 3.

---

## Task 1: Backend — `/rows` server-side filtering

Make the `/rows` reader honor the `filter` param (the route already accepts it; Part 1b/2 ignored it). Filterable columns: `molecular_weight`/`logp`/`tpsa`/`activity` (numeric) + `registration_number`/`name`/`R1`/`R2`/… (text). Applied to **both** `fetch_rows` and `count_rows` so the total reflects the filtered set. Lenient: unknown col/op/kind → clause skipped.

**Files:**
- Modify: `backend/src/cellar/application/sar_analysis/decomposition_rows.py`
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/decomposition_row_reader.py`
- Test: `backend/tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py`

- [ ] **Step 1: Write the failing integration tests** — append to `test_decomposition_row_reader.py`:

```python
@pytest.mark.asyncio
async def test_fetch_rows_numeric_filter_on_physchem(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        light = await _seed_molecule(uow, ws, org, reg="CV-LIGHT", smiles="C", mw=100.0)
        heavy = await _seed_molecule(uow, ws, org, reg="CV-HEAVY", smiles="CC", mw=400.0)
        await repo.write_assignments(run.id, [
            RGroupAssignment(molecule_id=light, rgroups={"R1": "F"}),
            RGroupAssignment(molecule_id=heavy, rgroups={"R1": "Cl"}),
        ])
        await uow.commit()
    flt = {"molecular_weight": {"kind": "number", "op": "gte", "value": 300}}
    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        rows = await reader.fetch_rows(run.id, workspace_id=ws, offset=0, limit=50, sort=[], filter=flt)
        total = await reader.count_rows(run.id, workspace_id=ws, filter=flt)
    assert [r.registration_number for r in rows] == ["CV-HEAVY"]
    assert total == 1  # filtered count


@pytest.mark.asyncio
async def test_fetch_rows_text_filter_on_rgroup(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        for reg, r1 in (("CV-1", "Cl"), ("CV-2", "Br"), ("CV-3", "F")):
            m = await _seed_molecule(uow, ws, org, reg=reg, smiles="Fc1ccccc1")
            await repo.write_assignments(run.id, [RGroupAssignment(molecule_id=m, rgroups={"R1": r1})])
        await uow.commit()
    flt = {"R1": {"kind": "text", "op": "eq", "value": "Br"}}
    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        rows = await reader.fetch_rows(run.id, workspace_id=ws, offset=0, limit=50, sort=[], filter=flt)
    assert [r.rgroups["R1"] for r in rows] == ["Br"]


@pytest.mark.asyncio
async def test_fetch_rows_text_contains_on_registration(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        a = await _seed_molecule(uow, ws, org, reg="ABC-1", smiles="Fc1ccccc1")
        b = await _seed_molecule(uow, ws, org, reg="XYZ-2", smiles="Clc1ccccc1")
        await repo.write_assignments(run.id, [
            RGroupAssignment(molecule_id=a, rgroups={"R1": "F"}),
            RGroupAssignment(molecule_id=b, rgroups={"R1": "Cl"}),
        ])
        await uow.commit()
    flt = {"registration_number": {"kind": "text", "op": "contains", "value": "abc"}}  # case-insensitive
    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        rows = await reader.fetch_rows(run.id, workspace_id=ws, offset=0, limit=50, sort=[], filter=flt)
    assert [r.registration_number for r in rows] == ["ABC-1"]


@pytest.mark.asyncio
async def test_fetch_rows_unknown_filter_clause_is_ignored(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        m = await _seed_molecule(uow, ws, org, reg="CV-1", smiles="Fc1ccccc1")
        await repo.write_assignments(run.id, [RGroupAssignment(molecule_id=m, rgroups={"R1": "F"})])
        await uow.commit()
    flt = {"bogus_col": {"kind": "number", "op": "gt", "value": 1}, "R1": {"kind": "text", "op": "weird", "value": "F"}}
    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        rows = await reader.fetch_rows(run.id, workspace_id=ws, offset=0, limit=50, sort=[], filter=flt)
        total = await reader.count_rows(run.id, workspace_id=ws, filter=flt)
    assert len(rows) == 1 and total == 1  # unknown col + unknown op both skipped (lenient)
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `cd backend && uv run pytest tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py -k "filter" -v`
Expected: FAIL — `fetch_rows()`/`count_rows()` got an unexpected keyword argument `filter`.

- [ ] **Step 3: Add the filter to `decomposition_rows.py`**

`FetchDecompositionRowsInput` — add a trailing field:
```python
    filter: dict[str, Any] | None = None
```
(Import `Any`: `from typing import Any, Protocol`.)

`DecompositionRowReader` Protocol — add `filter` to `fetch_rows` and `count_rows`:
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
        filter: dict[str, Any] | None = None,
    ) -> list[DecompositionRow]: ...

    async def count_rows(
        self,
        run_id: UUID,
        *,
        workspace_id: UUID,
        projection_id: UUID | None = None,
        filter: dict[str, Any] | None = None,
    ) -> int: ...
```

`FetchDecompositionRows.execute` — pass `filter` to both reader calls:
```python
            rows = await self._reader.fetch_rows(
                payload.run_id,
                workspace_id=payload.workspace_id,
                offset=payload.offset,
                limit=payload.limit,
                sort=payload.sort,
                projection_id=payload.projection_id,
                filter=payload.filter,
            )
            total = await self._reader.count_rows(
                payload.run_id,
                workspace_id=payload.workspace_id,
                projection_id=payload.projection_id,
                filter=payload.filter,
            )
```

- [ ] **Step 4: Implement the filter in `decomposition_row_reader.py`**

Add imports (extend the existing `sqlalchemy` import + `Any`):
```python
from typing import Any
from sqlalchemy import func, null, select  # already present; no change needed beyond `Any`
```

Add the column resolver + clause builder + shared base (module level, near `_sort_column`):
```python
_TEXT_FILTER_COLS: dict[str, Any] = {
    "registration_number": MoleculeModel.registration_number,
    "name": MoleculeModel.name,
}
_NUMERIC_FILTER_COLS: dict[str, Any] = {
    "molecular_weight": MoleculeModel.molecular_weight,
    "logp": MoleculeModel.logp,
    "tpsa": MoleculeModel.tpsa,
}


def _filter_column(col: str, *, projection_id: UUID | None):
    """Resolve a filter key to a column expression, or None if unknown / N/A."""
    if col in _NUMERIC_FILTER_COLS:
        return _NUMERIC_FILTER_COLS[col]
    if col in _TEXT_FILTER_COLS:
        return _TEXT_FILTER_COLS[col]
    if col == "activity":
        return SarActivityValueModel.scalar if projection_id is not None else None
    if _RGROUP_LABEL.match(col):
        return RGroupAssignmentModel.rgroups[col].as_string()
    return None


def _number_condition(column, op: str, value, value2):
    if op == "eq":
        return column == value
    if op == "neq":
        return column != value
    if op == "gt":
        return column > value
    if op == "gte":
        return column >= value
    if op == "lt":
        return column < value
    if op == "lte":
        return column <= value
    if op == "between" and value2 is not None:
        return column.between(value, value2)
    return None


def _text_condition(column, op: str, value: str):
    if op == "eq":
        return column == value
    if op == "neq":
        return column != value
    if op == "contains":
        return column.ilike(f"%{value}%")
    if op == "startsWith":
        return column.ilike(f"{value}%")
    if op == "endsWith":
        return column.ilike(f"%{value}")
    return None


def _apply_filter(stmt, filter: dict[str, Any] | None, *, projection_id: UUID | None):
    """Apply each recognized filter clause as a WHERE condition; skip unknowns
    (lenient, like the sort handling). Numeric clauses target physchem columns or
    the joined activity scalar; text clauses target reg#/name (ILIKE) or
    ``rgroups->>'Rn'``."""
    if not filter:
        return stmt
    for col, clause in filter.items():
        if not isinstance(clause, dict):
            continue
        column = _filter_column(col, projection_id=projection_id)
        if column is None:
            continue
        kind = clause.get("kind")
        op = clause.get("op")
        value = clause.get("value")
        if kind == "number" and isinstance(value, (int, float)):
            cond = _number_condition(column, op, value, clause.get("value2"))
        elif kind == "text" and isinstance(value, str):
            cond = _text_condition(column, op, value)
        else:
            cond = None
        if cond is not None:
            stmt = stmt.where(cond)
    return stmt
```

In `SQLAlchemyDecompositionRowReader`, add a shared base helper + thread filter through `fetch_rows`/`count_rows`. Add this method:
```python
    def _activity_join(self, stmt, projection_id: UUID | None):
        if projection_id is None:
            return stmt
        return stmt.outerjoin(
            SarActivityValueModel,
            (SarActivityValueModel.projection_id == projection_id)
            & (SarActivityValueModel.molecule_id == RGroupAssignmentModel.molecule_id),
        )
```

Replace the body of `fetch_rows` so it (a) takes `filter`, (b) uses `_activity_join` instead of the inline outerjoin, and (c) applies `_apply_filter`:
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
        filter: dict[str, Any] | None = None,
    ) -> list[DecompositionRow]:
        activity_col = SarActivityValueModel.scalar if projection_id is not None else null()
        snapshot_col = SarActivityValueModel.snapshot if projection_id is not None else null()

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
                snapshot_col.label("activity_snapshot"),
            ),
            run_id,
            workspace_id,
        )
        stmt = self._activity_join(stmt, projection_id)
        stmt = _apply_filter(stmt, filter, projection_id=projection_id)

        order_by = []
        for spec in sort:
            if spec.col == "activity":
                col = SarActivityValueModel.scalar if projection_id is not None else None
            else:
                col = _sort_column(spec.col)
            if col is None:
                continue
            ordered = col.desc() if spec.direction == "desc" else col.asc()
            order_by.append(ordered.nulls_last())
        order_by.append(RGroupAssignmentModel.molecule_id)

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
                activity_snapshot=dict(row[9]) if row[9] is not None else None,
            )
            for row in result.all()
        ]
```
(The `activity_snapshot` select + `DecompositionRow.activity_snapshot` field land in Task 2; if implementing Task 1 alone, omit the `snapshot_col`/`activity_snapshot` lines and the row field, then re-add them in Task 2. Recommended: do Tasks 1+2 together since they touch the same method.)

Replace `count_rows` to take `projection_id` + `filter`:
```python
    async def count_rows(
        self,
        run_id: UUID,
        *,
        workspace_id: UUID,
        projection_id: UUID | None = None,
        filter: dict[str, Any] | None = None,
    ) -> int:
        stmt = self._scoped_join(
            select(func.count()).select_from(RGroupAssignmentModel), run_id, workspace_id
        )
        stmt = self._activity_join(stmt, projection_id)
        stmt = _apply_filter(stmt, filter, projection_id=projection_id)
        return int((await self._uow.session.execute(stmt)).scalar_one())
```

- [ ] **Step 5: Run the filter tests**

Run: `cd backend && uv run pytest tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py -v && uv run lint-imports && uv run ruff check src/cellar/application/sar_analysis/decomposition_rows.py src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/decomposition_row_reader.py`
Expected: all PASS (existing + new); lint + ruff clean.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(sar): /rows server-side filtering (physchem/activity/reg#/R-group)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- backend/src/cellar/application/sar_analysis/decomposition_rows.py backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/decomposition_row_reader.py backend/tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py
```

---

## Task 2: Backend — `/rows` per-row `activity_snapshot` + `activity_reference`

So the table's plot column + potency shading + row-click curve-expand work under pagination. `activity_snapshot` is the stored `ActivityValue` (the same wire shape `/search` returns). `activity_reference` is the min scalar across the filtered set (the potency-ramp anchor, consistent across pages).

**Files:**
- Modify: `backend/src/cellar/application/sar_analysis/decomposition_rows.py`
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/decomposition_row_reader.py`
- Modify: `backend/src/cellar/interface/routes/sar_analysis.py`
- Test: extend the reader integration test + `backend/tests/api/test_sar_analysis_routes.py`

- [ ] **Step 1: Write failing tests** — append to `test_decomposition_row_reader.py`:

```python
@pytest.mark.asyncio
async def test_fetch_rows_returns_snapshot_and_reference(uow):
    from cellar.domain.sar_analysis.activity_projection_types import ActivityScalar
    from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_repository import (  # noqa: E501
        SQLAlchemySarActivityProjectionRepository,
    )

    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        proj = await _seed_ready_projection(uow, ws)  # helper added in Part-2 Task 15
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        pr = SQLAlchemySarActivityProjectionRepository(uow)
        potent = await _seed_molecule(uow, ws, org, reg="CV-POTENT", smiles="Fc1ccccc1")
        weak = await _seed_molecule(uow, ws, org, reg="CV-WEAK", smiles="Clc1ccccc1")
        await repo.write_assignments(run.id, [
            RGroupAssignment(molecule_id=potent, rgroups={"R1": "F"}),
            RGroupAssignment(molecule_id=weak, rgroups={"R1": "Cl"}),
        ])
        await pr.write_values(proj.id, [
            ActivityScalar(molecule_id=potent, scalar=0.1, unit="uM", qualifier=None,
                           source="dose_response", snapshot={"value": 0.1, "raw_data": []}),
            ActivityScalar(molecule_id=weak, scalar=5.0, unit="uM", qualifier=None,
                           source="dose_response", snapshot={"value": 5.0}),
        ])
        await uow.commit()
    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        rows = await reader.fetch_rows(run.id, workspace_id=ws, offset=0, limit=50, sort=[], projection_id=proj.id)
        ref = await reader.activity_reference(run.id, workspace_id=ws, projection_id=proj.id, filter=None)
    by_reg = {r.registration_number: r for r in rows}
    assert by_reg["CV-POTENT"].activity_snapshot == {"value": 0.1, "raw_data": []}
    assert by_reg["CV-WEAK"].activity_snapshot == {"value": 5.0}
    assert ref == pytest.approx(0.1)  # min scalar = most-potent reference


@pytest.mark.asyncio
async def test_activity_reference_none_without_projection(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        async with uow:
            pass
    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        ref = await reader.activity_reference(run.id, workspace_id=ws, projection_id=None, filter=None)
    assert ref is None
```

- [ ] **Step 2: Run to confirm fail**

Run: `cd backend && uv run pytest tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py -k "snapshot or reference" -v`
Expected: FAIL — `DecompositionRow` has no `activity_snapshot` / reader has no `activity_reference`.

- [ ] **Step 3: Add `activity_snapshot` to `DecompositionRow` + `activity_reference` to the output (decomposition_rows.py)**

`DecompositionRow` — trailing field:
```python
    activity_snapshot: dict[str, Any] | None = None
```

`DecompositionRowReader` Protocol — add the method:
```python
    async def activity_reference(
        self,
        run_id: UUID,
        *,
        workspace_id: UUID,
        projection_id: UUID | None,
        filter: dict[str, Any] | None = None,
    ) -> float | None: ...
```

`FetchDecompositionRowsOutput` — trailing field:
```python
    activity_reference: float | None = None
```

`FetchDecompositionRows.execute` — compute the reference when a projection is given, return it:
```python
            reference = None
            if payload.projection_id is not None:
                reference = await self._reader.activity_reference(
                    payload.run_id,
                    workspace_id=payload.workspace_id,
                    projection_id=payload.projection_id,
                    filter=payload.filter,
                )
        return Success(
            FetchDecompositionRowsOutput(rows=rows, total=total, activity_reference=reference)
        )
```
(The `activity_snapshot` select in `fetch_rows` is already in the Task-1 body above.)

- [ ] **Step 4: Implement `activity_reference` in the reader**

Add to `SQLAlchemyDecompositionRowReader`:
```python
    async def activity_reference(
        self,
        run_id: UUID,
        *,
        workspace_id: UUID,
        projection_id: UUID | None,
        filter: dict[str, Any] | None = None,
    ) -> float | None:
        """The most-potent (min) activity scalar across the filtered matched set,
        anchoring the table's potency ramp consistently across pages. None when no
        projection or no values."""
        if projection_id is None:
            return None
        stmt = self._scoped_join(
            select(func.min(SarActivityValueModel.scalar)).select_from(RGroupAssignmentModel),
            run_id,
            workspace_id,
        )
        stmt = self._activity_join(stmt, projection_id)
        stmt = _apply_filter(stmt, filter, projection_id=projection_id)
        value = (await self._uow.session.execute(stmt)).scalar_one_or_none()
        return float(value) if value is not None else None
```

- [ ] **Step 5: Extend the route (routes/sar_analysis.py)**

`DecompositionRowView` — trailing field:
```python
    activity_snapshot: dict[str, Any] | None = None
```
`DecompositionRowsResponse` — trailing field:
```python
    activity_reference: float | None = None
```
`_row_view` — add `activity_snapshot=row.activity_snapshot`. The `decomposition_rows` route returns the reference:
```python
    return DecompositionRowsResponse(
        rows=[_row_view(r) for r in out.rows],
        total=out.total,
        activity_reference=out.activity_reference,
    )
```

- [ ] **Step 6: Add an API test** — append to `backend/tests/api/test_sar_activity_projection_routes.py` (it already has `_seed_heatmap_fixture`):

```python
@pytest.mark.asyncio
async def test_rows_return_snapshot_and_reference(client, api_app, workspace_id) -> None:
    run_id, projection_id, potent = await _seed_heatmap_fixture(api_app, workspace_id)
    res = await client.post(
        f"/api/v1/sar/decomposition/{run_id}/rows",
        json={"offset": 0, "limit": 50, "projection_id": str(projection_id),
              "sort": [{"col": "activity", "dir": "asc"}]},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["activity_reference"] == pytest.approx(0.1)  # min across the set
    top = body["rows"][0]
    assert top["registration_number"] == "CV-POTENT"
    assert top["activity_snapshot"] == {"value": 0.1}  # the stored snapshot, per row
```

- [ ] **Step 7: Run + lint + commit**

Run: `cd backend && uv run pytest tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py tests/api/test_sar_activity_projection_routes.py tests/api/test_sar_analysis_routes.py -q && uv run lint-imports && uv run ruff check src/ && uv run ruff format --check src/cellar/application/sar_analysis/decomposition_rows.py src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/decomposition_row_reader.py src/cellar/interface/routes/sar_analysis.py`
Expected: all PASS; lint/ruff clean (pre-existing Part-1b ruff debt in *other* files is tracked in `docs/backlog/part1b-ruff-debt.md` — unrelated).

```bash
git commit -m "feat(sar): /rows per-row activity_snapshot + response activity_reference" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- backend/src/cellar/application/sar_analysis/decomposition_rows.py backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/decomposition_row_reader.py backend/src/cellar/interface/routes/sar_analysis.py backend/tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py backend/tests/api/test_sar_activity_projection_routes.py
```

---

## Task 3: Frontend — regenerate the orval API layer

**Files:** generated under `frontend/src/shared/lib/api/` (do not hand-edit).

- [ ] **Step 1: Regenerate** (backend must be up on `:8000` — see Task 0)

Run: `cd frontend && pnpm generate:api`
Expected: `model/` gains `decompositionRunResponse.ts`, `activityProjectionResponse.ts`, `heatmapResponse.ts`, `heatmapCellView.ts`, `startActivityProjectionRequest.ts`, `activityChannelRequest.ts`, `interceptKeyModel.ts`, and `decompositionRowView.ts`/`decompositionRowsRequest.ts` gain `activity`/`activity_snapshot`/`projection_id`/`activity_reference`/`filter`. A `sar-analysis/sar-analysis.ts` endpoint module gains the new functions.

- [ ] **Step 2: Review the diff + confirm the new symbols**

Run:
```bash
cd frontend && git status --short src/shared/lib/api/ && \
  grep -RoE "export (async function|const) [A-Za-z]*ActivityProjection[A-Za-z]*|[A-Za-z]*Heatmap[A-Za-z]*Post" src/shared/lib/api/sar-analysis/sar-analysis.ts | sort -u
```
Expected: the generated POST/GET function names for `start_activity_projection`, `get_activity_projection`, `cancel_activity_projection`, `decomposition_heatmap` exist. **Record the exact names** — the hooks in Tasks 6–9 lazy-import them (the predicted names below follow orval's `<operationId>Api...` convention; substitute the actual generated names if they differ).

- [ ] **Step 3: Typecheck + commit the generated layer**

Run: `cd frontend && pnpm exec tsc --noEmit`
Expected: clean (the generated model is internally consistent).

```bash
git add src/shared/lib/api && git commit -m "chore(api): regenerate orval for SAR activity-projection + heatmap + rows fields" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Frontend — `agFilterModelToParam` + shared col-key mapping

Map AG-Grid `filterModel` (and sort `colId`s) to the backend's `filter`/`sort` contract. One shared `colIdToBackendKey` for both.

**Files:**
- Create: `frontend/src/features/sar-analysis/lib/ag-filter-model.ts`
- Test: `frontend/src/features/sar-analysis/lib/ag-filter-model.test.ts`

- [ ] **Step 1: Write the failing test**

Create `ag-filter-model.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { agFilterModelToParam, colIdToBackendKey } from "./ag-filter-model";

describe("colIdToBackendKey", () => {
  it("maps physchem + activity + reg# + R-group col ids", () => {
    expect(colIdToBackendKey("mw")).toBe("molecular_weight");
    expect(colIdToBackendKey("clogp")).toBe("logp");
    expect(colIdToBackendKey("tpsa")).toBe("tpsa");
    expect(colIdToBackendKey("activity:value")).toBe("activity");
    expect(colIdToBackendKey("registration_number")).toBe("registration_number");
    expect(colIdToBackendKey("rg:R1")).toBe("R1");
    expect(colIdToBackendKey("structure")).toBeNull(); // not sortable/filterable
  });
});

describe("agFilterModelToParam", () => {
  it("maps a text 'contains' filter", () => {
    const out = agFilterModelToParam({
      "registration_number": { filterType: "text", type: "contains", filter: "CV" },
    });
    expect(out).toEqual({ registration_number: { kind: "text", op: "contains", value: "CV" } });
  });

  it("maps a number 'greaterThan' filter on physchem", () => {
    const out = agFilterModelToParam({ mw: { filterType: "number", type: "greaterThan", filter: 200 } });
    expect(out).toEqual({ molecular_weight: { kind: "number", op: "gt", value: 200 } });
  });

  it("maps inRange to between with value2", () => {
    const out = agFilterModelToParam({
      tpsa: { filterType: "number", type: "inRange", filter: 20, filterTo: 80 },
    });
    expect(out).toEqual({ tpsa: { kind: "number", op: "between", value: 20, value2: 80 } });
  });

  it("maps an R-group equals filter to the bare label key", () => {
    const out = agFilterModelToParam({ "rg:R1": { filterType: "text", type: "equals", filter: "F" } });
    expect(out).toEqual({ R1: { kind: "text", op: "eq", value: "F" } });
  });

  it("drops unknown columns, unsupported ops, and blank filters", () => {
    expect(
      agFilterModelToParam({
        nope: { filterType: "text", type: "contains", filter: "x" },
        mw: { filterType: "number", type: "blank", filter: null },
      }),
    ).toBeUndefined();
    expect(agFilterModelToParam(null)).toBeUndefined();
    expect(agFilterModelToParam({})).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run → fail**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/lib/ag-filter-model.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `ag-filter-model.ts`:
```ts
/**
 * Map AG-Grid Community `filterModel` (text + number filters) and sort `colId`s
 * to the backend `/rows` `filter`/`sort` contract. Set filter is Enterprise, so
 * R-group columns use a Text filter. One `colIdToBackendKey` serves both sort and
 * filter so the column ids and the backend keys stay in sync in one place.
 */

export type FilterClause =
  | { kind: "number"; op: "eq" | "neq" | "gt" | "gte" | "lt" | "lte" | "between"; value: number; value2?: number }
  | { kind: "text"; op: "contains" | "eq" | "startsWith" | "endsWith" | "neq"; value: string };

const COL_ID_TO_KEY: Record<string, string> = {
  registration_number: "registration_number",
  name: "name",
  mw: "molecular_weight",
  clogp: "logp",
  tpsa: "tpsa",
  "activity:value": "activity",
};

/** AG-Grid colId → backend filter/sort key, or null if not filterable/sortable. */
export function colIdToBackendKey(colId: string): string | null {
  if (colId in COL_ID_TO_KEY) return COL_ID_TO_KEY[colId];
  if (colId.startsWith("rg:")) return colId.slice(3); // "rg:R1" -> "R1"
  return null;
}

const TEXT_OPS: Record<string, FilterClause["op"]> = {
  contains: "contains",
  equals: "eq",
  notEqual: "neq",
  startsWith: "startsWith",
  endsWith: "endsWith",
};
const NUMBER_OPS: Record<string, "eq" | "neq" | "gt" | "gte" | "lt" | "lte"> = {
  equals: "eq",
  notEqual: "neq",
  greaterThan: "gt",
  greaterThanOrEqual: "gte",
  lessThan: "lt",
  lessThanOrEqual: "lte",
};

type AgFilter = { filterType?: string; type?: string; filter?: unknown; filterTo?: unknown };

export function agFilterModelToParam(
  filterModel: Record<string, AgFilter> | null | undefined,
): Record<string, FilterClause> | undefined {
  if (!filterModel) return undefined;
  const out: Record<string, FilterClause> = {};
  for (const [colId, model] of Object.entries(filterModel)) {
    const key = colIdToBackendKey(colId);
    if (!key || !model) continue;
    if (model.filterType === "text") {
      const op = model.type ? TEXT_OPS[model.type] : undefined;
      if (!op || model.filter == null) continue;
      out[key] = { kind: "text", op, value: String(model.filter) } as FilterClause;
    } else if (model.filterType === "number") {
      if (model.type === "inRange") {
        if (model.filter == null || model.filterTo == null) continue;
        out[key] = { kind: "number", op: "between", value: Number(model.filter), value2: Number(model.filterTo) };
      } else {
        const op = model.type ? NUMBER_OPS[model.type] : undefined;
        if (!op || model.filter == null) continue;
        out[key] = { kind: "number", op, value: Number(model.filter) };
      }
    }
  }
  return Object.keys(out).length ? out : undefined;
}
```

- [ ] **Step 4: Run → pass; commit**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/lib/ag-filter-model.test.ts && pnpm exec biome check src/features/sar-analysis/lib/ag-filter-model.ts`
Expected: PASS; biome clean.

```bash
git add src/features/sar-analysis/lib/ag-filter-model.ts src/features/sar-analysis/lib/ag-filter-model.test.ts && git commit -m "feat(sar): agFilterModelToParam + colIdToBackendKey (AG-Grid -> /rows contract)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Frontend — additive `datasource` prop on `DataGrid`

**Files:**
- Modify: `frontend/src/shared/components/data-grid/data-grid.tsx`
- Test: `frontend/src/shared/components/data-grid/data-grid.infinite.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `data-grid.infinite.test.tsx`:
```tsx
import { render } from "@testing-library/react";
import type { IDatasource } from "ag-grid-community";
import { describe, expect, it, vi } from "vitest";
import { DataGrid } from "./data-grid";

// AG Grid is heavy; assert the prop wiring via a mock of AgGridReact.
vi.mock("ag-grid-react", () => ({
  AgGridReact: (props: Record<string, unknown>) => {
    // expose the resolved props for assertions
    (globalThis as Record<string, unknown>).__agProps = props;
    return null;
  },
}));

describe("DataGrid datasource (infinite row model)", () => {
  it("enables infinite model + passes datasource, omits rowData", () => {
    const datasource: IDatasource = { getRows: vi.fn() };
    render(<DataGrid columnDefs={[{ field: "x" } as never]} rowData={undefined} datasource={datasource} />);
    const p = (globalThis as Record<string, unknown>).__agProps as Record<string, unknown>;
    expect(p.rowModelType).toBe("infinite");
    expect(p.datasource).toBe(datasource);
    expect(p.rowData).toBeUndefined();
  });

  it("stays client-side when no datasource", () => {
    render(<DataGrid columnDefs={[{ field: "x" } as never]} rowData={[{ x: 1 }]} />);
    const p = (globalThis as Record<string, unknown>).__agProps as Record<string, unknown>;
    expect(p.rowModelType).toBeUndefined();
    expect(p.rowData).toEqual([{ x: 1 }]);
  });
});
```

- [ ] **Step 2: Run → fail**

Run: `cd frontend && pnpm exec vitest run src/shared/components/data-grid/data-grid.infinite.test.tsx`
Expected: FAIL — `datasource` not wired (rowModelType undefined / rowData set).

- [ ] **Step 3: Implement the additive prop**

In `data-grid.tsx`:
1. Add `IDatasource` to the `ag-grid-community` type import: `type IDatasource,`.
2. Add the prop to `DataGridProps`:
```ts
  /** When provided, the grid uses AG-Grid's Infinite Row Model: rows stream from
   *  this datasource's getRows (server pagination/sort/filter) instead of client
   *  `rowData`. Additive — existing client-side consumers omit it. */
  datasource?: IDatasource;
```
3. Destructure `datasource` in the component params (alongside `rowData`).
4. Compute `const isInfinite = !!datasource;` near `selectionEnabled`.
5. Replace `const hasRows = !!rowData?.length;` with:
```ts
  // In infinite mode rowData is undefined and AG-Grid owns the no-rows overlay,
  // so never short-circuit to the client empty-state.
  const hasRows = isInfinite ? true : !!rowData?.length;
```
6. In the `<AgGridReact>` element, replace the `rowData` + `quickFilterText` lines and add the infinite props:
```tsx
          rowModelType={isInfinite ? "infinite" : undefined}
          datasource={isInfinite ? datasource : undefined}
          rowData={isInfinite ? undefined : (rowData ?? [])}
          quickFilterText={isInfinite ? undefined : quickFilter || undefined}
```
(Everything else — theme, columnDefs, selection, onRowClicked, getRowId passthrough via `...restWithoutSelection` — is unchanged. Selection in infinite mode operates over loaded rows.)

- [ ] **Step 4: Run → pass; commit**

Run: `cd frontend && pnpm exec vitest run src/shared/components/data-grid/data-grid.infinite.test.tsx && pnpm exec biome check src/shared/components/data-grid/data-grid.tsx`
Expected: PASS (both old + new); biome clean.

```bash
git add src/shared/components/data-grid/data-grid.tsx src/shared/components/data-grid/data-grid.infinite.test.tsx && git commit -m "feat(data-grid): additive datasource prop (infinite row model)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Frontend — `useDecompositionRun` hook

Clones `useScaffoldTree`. The decomposition `start` returns the **run header itself** (no `{result, job}` envelope): `{run_id, status, rgroup_labels, matched_count, unmatched_count, total_count}`, 200 ready / 202 pending. The header IS the job (`{id: run_id, status}`); poll `/jobs/{run_id}` until terminal.

**Files:**
- Create: `frontend/src/features/sar-analysis/hooks/use-decomposition-run.ts`
- Test: `frontend/src/features/sar-analysis/hooks/use-decomposition-run.test.ts`

- [ ] **Step 1: Write the failing test** (drive the hook via `startFn`/`pollFn` overrides + `renderHook`):

```ts
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { useDecompositionRun } from "./use-decomposition-run";

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

const READY = {
  run_id: "run-1", status: "ready", rgroup_labels: ["R1", "R2"],
  matched_count: 8, unmatched_count: 2, total_count: 10, error_message: null,
};

describe("useDecompositionRun", () => {
  it("returns the run header inline when start is ready", async () => {
    const startFn = vi.fn().mockResolvedValue(READY);
    const pollFn = vi.fn();
    const { result } = renderHook(
      () => useDecompositionRun({ collectionId: "c1", coreSmiles: "c1ccccc1", startFn, pollFn }),
      { wrapper: wrap() },
    );
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.runId).toBe("run-1");
    expect(result.current.labels).toEqual(["R1", "R2"]);
    expect(result.current.counts).toEqual({ matched: 8, unmatched: 2, total: 10 });
    expect(pollFn).not.toHaveBeenCalled();
  });

  it("polls a pending run until ready", async () => {
    const startFn = vi.fn().mockResolvedValue({ ...READY, status: "pending", rgroup_labels: [], matched_count: 0, unmatched_count: 0, total_count: 0 });
    const pollFn = vi.fn().mockResolvedValue(READY);
    const { result } = renderHook(
      () => useDecompositionRun({ collectionId: "c1", coreSmiles: "c1ccccc1", startFn, pollFn, pollIntervalMs: 5 }),
      { wrapper: wrap() },
    );
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.runId).toBe("run-1");
    expect(result.current.counts?.total).toBe(10);
    expect(pollFn).toHaveBeenCalled();
  });

  it("is disabled without a core", () => {
    const startFn = vi.fn();
    renderHook(() => useDecompositionRun({ collectionId: "c1", coreSmiles: null, startFn, pollFn: vi.fn() }), { wrapper: wrap() });
    expect(startFn).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run → fail**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/hooks/use-decomposition-run.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement** (mirror `use-scaffold-tree.ts`)

Create `use-decomposition-run.ts`:
```ts
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { useJobPoll } from "@/shared/hooks/use-job-poll";
import type { DecompositionRunResponse } from "@/shared/lib/api/model";
import { STALE_TIME } from "@/shared/lib/query-defaults";

type StartInput = { collection_id?: string; molecule_ids?: string[]; core_smiles: string };

export type UseDecompositionRunParams = {
  collectionId?: string;
  moleculeIds?: string[];
  coreSmiles: string | null;
  startFn?: (input: StartInput) => Promise<DecompositionRunResponse>;
  pollFn?: (runId: string) => Promise<DecompositionRunResponse>;
  pollIntervalMs?: number;
  enabled?: boolean;
};

export type UseDecompositionRunReturn = {
  runId: string | null;
  labels: string[];
  counts: { matched: number; unmatched: number; total: number } | null;
  status: string | null;
  isStarting: boolean;
  isPolling: boolean;
  error: Error | null;
};

const DEFAULT_POLL_MS = 1500;

function sortedKey(ids: string[]): string {
  return [...ids].sort().join(",");
}

export function useDecompositionRun(params: UseDecompositionRunParams): UseDecompositionRunReturn {
  const {
    collectionId,
    moleculeIds,
    coreSmiles,
    startFn = defaultStartFn,
    pollFn = defaultPollFn,
    pollIntervalMs = DEFAULT_POLL_MS,
    enabled = true,
  } = params;

  const sourceKey = collectionId ? `coll:${collectionId}` : `ids:${sortedKey(moleculeIds ?? [])}`;
  const key = `${sourceKey}|core:${coreSmiles ?? ""}`;
  const queryEnabled =
    enabled && !!coreSmiles && (collectionId !== undefined || (moleculeIds ?? []).length > 0);

  const start = useQuery({
    queryKey: ["decomposition-run", "start", key],
    queryFn: () =>
      startFn(
        collectionId
          ? { collection_id: collectionId, core_smiles: coreSmiles as string }
          : { molecule_ids: moleculeIds ?? [], core_smiles: coreSmiles as string },
      ),
    enabled: queryEnabled,
    staleTime: STALE_TIME.MEDIUM,
  });

  const startRun = start.data ?? null;
  const job = useMemo(
    () => (startRun ? { id: startRun.run_id, status: startRun.status } : null),
    [startRun],
  );

  const { result: polled, error: pollError } = useJobPoll<DecompositionRunResponse, DecompositionRunResponse>({
    job,
    pollFn,
    getStatus: (j) => j.status,
    getResult: (j) => (j.status === "ready" ? j : null),
    getError: (j) => {
      if (j.status === "failed") return j.error_message ?? "decomposition failed";
      if (j.status === "cancelled") return "decomposition cancelled";
      return null;
    },
    pollIntervalMs,
    queryKey: "decomposition-run-poll",
  });

  // The freshest known header: the polled ready run, else the inline-ready start,
  // else the (pending) start header.
  const ready = polled ?? (startRun?.status === "ready" ? startRun : null);
  const current = ready ?? startRun;

  return {
    runId: startRun?.run_id ?? null,
    labels: current?.rgroup_labels ?? [],
    counts: current
      ? { matched: current.matched_count, unmatched: current.unmatched_count, total: current.total_count }
      : null,
    status: current?.status ?? null,
    isStarting: start.isPending && queryEnabled,
    isPolling: job != null && ready === null && pollError === null,
    error: (pollError ? new Error(pollError) : null) ?? (start.error as Error | null) ?? null,
  };
}

async function defaultStartFn(input: StartInput): Promise<DecompositionRunResponse> {
  const { startDecompositionApiV1SarDecompositionPost } = await import(
    "@/shared/lib/api/sar-analysis/sar-analysis"
  );
  return startDecompositionApiV1SarDecompositionPost(input) as unknown as DecompositionRunResponse;
}

async function defaultPollFn(runId: string): Promise<DecompositionRunResponse> {
  const { getDecompositionRunApiV1SarDecompositionJobsRunIdGet } = await import(
    "@/shared/lib/api/sar-analysis/sar-analysis"
  );
  return getDecompositionRunApiV1SarDecompositionJobsRunIdGet(runId) as unknown as DecompositionRunResponse;
}
```
(Verify the two generated function names against `sar-analysis.ts` from Task 3; adjust the lazy imports if orval named them differently.)

- [ ] **Step 4: Run → pass; commit**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/hooks/use-decomposition-run.test.ts && pnpm exec biome check src/features/sar-analysis/hooks/use-decomposition-run.ts`
Expected: PASS; biome clean.

```bash
git add src/features/sar-analysis/hooks/use-decomposition-run.ts src/features/sar-analysis/hooks/use-decomposition-run.test.ts && git commit -m "feat(sar): useDecompositionRun job-poll hook" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Frontend — `useActivityProjection` hook

Same job-poll shape; `start` returns `{projection_id, status, value_count}`. Builds the `channel` from the FE `SarColorSpec` + `AggregationMode`. Enabled only when a `channel` is provided.

**Files:**
- Create: `frontend/src/features/sar-analysis/hooks/use-activity-projection.ts`
- Test: `frontend/src/features/sar-analysis/hooks/use-activity-projection.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { channelFromColorSpec, useActivityProjection } from "./use-activity-projection";

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

const SPEC = { protocolId: "p1", column: "drc:rd1", interceptKey: { kind: "ic", level: 50 }, source: "dr_curve", label: "EGFR · IC50" } as const;

describe("channelFromColorSpec", () => {
  it("maps a SarColorSpec + aggregation mode to the channel request", () => {
    expect(channelFromColorSpec(SPEC, "gmean")).toEqual({
      column: "drc:rd1",
      source: "dr_curve",
      intercept_key: { kind: "ic", level: 50 },
      selection_rule: "geometric_mean",
      protocol_id: "p1",
      label: "EGFR · IC50",
    });
  });
});

describe("useActivityProjection", () => {
  it("polls a pending projection to ready", async () => {
    const startFn = vi.fn().mockResolvedValue({ projection_id: "proj-1", status: "pending", value_count: 0 });
    const pollFn = vi.fn().mockResolvedValue({ projection_id: "proj-1", status: "ready", value_count: 7 });
    const { result } = renderHook(
      () => useActivityProjection({ collectionId: "c1", channel: channelFromColorSpec(SPEC, "latest"), startFn, pollFn, pollIntervalMs: 5 }),
      { wrapper: wrap() },
    );
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.projectionId).toBe("proj-1");
  });

  it("is disabled with no channel", () => {
    const startFn = vi.fn();
    renderHook(() => useActivityProjection({ collectionId: "c1", channel: null, startFn, pollFn: vi.fn() }), { wrapper: wrap() });
    expect(startFn).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run → fail.** `cd frontend && pnpm exec vitest run src/features/sar-analysis/hooks/use-activity-projection.test.ts` — module not found.

- [ ] **Step 3: Implement**

Create `use-activity-projection.ts`:
```ts
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import type { AggregationMode } from "@/features/research-organization/lib/use-aggregation-mode";
import { aggregationModeToWire } from "@/features/research-organization/lib/use-aggregation-mode";
import { useJobPoll } from "@/shared/hooks/use-job-poll";
import type { ActivityProjectionResponse } from "@/shared/lib/api/model";
import { STALE_TIME } from "@/shared/lib/query-defaults";
import type { SarColorSpec } from "../lib/sar-color-spec";

export type ActivityChannel = {
  column: string;
  source: "dr_curve" | "readout_data";
  intercept_key: { kind: string; level: number } | null;
  selection_rule: string;
  protocol_id: string;
  label: string;
};

/** SarColorSpec + aggregation mode → the server `ActivityChannelRequest`. */
export function channelFromColorSpec(spec: SarColorSpec, aggMode: AggregationMode): ActivityChannel {
  return {
    column: spec.column,
    source: spec.source,
    intercept_key: spec.interceptKey ? { kind: spec.interceptKey.kind, level: spec.interceptKey.level } : null,
    selection_rule: aggregationModeToWire(aggMode) as unknown as string,
    protocol_id: spec.protocolId,
    label: spec.label,
  };
}

type StartInput = { collection_id?: string; molecule_ids?: string[]; channel: ActivityChannel };

export type UseActivityProjectionParams = {
  collectionId?: string;
  moleculeIds?: string[];
  channel: ActivityChannel | null;
  startFn?: (input: StartInput) => Promise<ActivityProjectionResponse>;
  pollFn?: (id: string) => Promise<ActivityProjectionResponse>;
  pollIntervalMs?: number;
  enabled?: boolean;
};

export type UseActivityProjectionReturn = {
  projectionId: string | null;
  status: string | null;
  isStarting: boolean;
  isPolling: boolean;
  error: Error | null;
};

const DEFAULT_POLL_MS = 1500;

function sortedKey(ids: string[]): string {
  return [...ids].sort().join(",");
}

export function useActivityProjection(params: UseActivityProjectionParams): UseActivityProjectionReturn {
  const {
    collectionId,
    moleculeIds,
    channel,
    startFn = defaultStartFn,
    pollFn = defaultPollFn,
    pollIntervalMs = DEFAULT_POLL_MS,
    enabled = true,
  } = params;

  // Channel identity for the query key: the semantic fields that change the scalar.
  const channelKey = channel
    ? `${channel.column}|${channel.selection_rule}|${channel.intercept_key ? `${channel.intercept_key.kind}:${channel.intercept_key.level}` : ""}`
    : "";
  const sourceKey = collectionId ? `coll:${collectionId}` : `ids:${sortedKey(moleculeIds ?? [])}`;
  const queryEnabled =
    enabled && channel != null && (collectionId !== undefined || (moleculeIds ?? []).length > 0);

  const start = useQuery({
    queryKey: ["activity-projection", "start", sourceKey, channelKey],
    queryFn: () =>
      startFn(
        collectionId
          ? { collection_id: collectionId, channel: channel as ActivityChannel }
          : { molecule_ids: moleculeIds ?? [], channel: channel as ActivityChannel },
      ),
    enabled: queryEnabled,
    staleTime: STALE_TIME.MEDIUM,
  });

  const startProj = start.data ?? null;
  const job = useMemo(
    () => (startProj ? { id: startProj.projection_id, status: startProj.status } : null),
    [startProj],
  );

  const { result: polled, error: pollError } = useJobPoll<ActivityProjectionResponse, ActivityProjectionResponse>({
    job,
    pollFn,
    getStatus: (j) => j.status,
    getResult: (j) => (j.status === "ready" ? j : null),
    getError: (j) => {
      if (j.status === "failed") return j.error_message ?? "activity projection failed";
      if (j.status === "cancelled") return "activity projection cancelled";
      return null;
    },
    pollIntervalMs,
    queryKey: "activity-projection-poll",
  });

  const ready = polled ?? (startProj?.status === "ready" ? startProj : null);
  const current = ready ?? startProj;

  return {
    projectionId: startProj?.projection_id ?? null,
    status: current?.status ?? null,
    isStarting: start.isPending && queryEnabled,
    isPolling: job != null && ready === null && pollError === null,
    error: (pollError ? new Error(pollError) : null) ?? (start.error as Error | null) ?? null,
  };
}

async function defaultStartFn(input: StartInput): Promise<ActivityProjectionResponse> {
  const { startActivityProjectionApiV1SarActivityProjectionPost } = await import(
    "@/shared/lib/api/sar-analysis/sar-analysis"
  );
  return startActivityProjectionApiV1SarActivityProjectionPost(input) as unknown as ActivityProjectionResponse;
}

async function defaultPollFn(id: string): Promise<ActivityProjectionResponse> {
  const { getActivityProjectionApiV1SarActivityProjectionJobsIdGet } = await import(
    "@/shared/lib/api/sar-analysis/sar-analysis"
  );
  return getActivityProjectionApiV1SarActivityProjectionJobsIdGet(id) as unknown as ActivityProjectionResponse;
}
```
(Verify the generated function names + the `ActivityProjectionResponse.error_message` field against the orval output; adjust if needed. `aggregationModeToWire` already exists in `research-organization/lib/use-aggregation-mode`.)

- [ ] **Step 4: Run → pass; commit**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/hooks/use-activity-projection.test.ts && pnpm exec biome check src/features/sar-analysis/hooks/use-activity-projection.ts`

```bash
git add src/features/sar-analysis/hooks/use-activity-projection.ts src/features/sar-analysis/hooks/use-activity-projection.test.ts && git commit -m "feat(sar): useActivityProjection job-poll hook + channelFromColorSpec" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Frontend — `useHeatmapAggregation` hook

A plain React-Query POST keyed on `(runId, projectionId, axisY, axisX)` — axis re-swaps are instant from cache. Payload bounded (≤30×30 + `truncated`).

**Files:**
- Create: `frontend/src/features/sar-analysis/hooks/use-heatmap-aggregation.ts`
- Test: `frontend/src/features/sar-analysis/hooks/use-heatmap-aggregation.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { useHeatmapAggregation } from "./use-heatmap-aggregation";

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

const HEATMAP = { x_values: ["Cl"], y_values: ["F"], cells: [{ y: "F", x: "Cl", count: 2, best_scalar: 0.1, best_molecule_id: "m1", best_molecule_label: "CV-1", best_snapshot: {} }], y_total: 1, x_total: 1, truncated: false };

describe("useHeatmapAggregation", () => {
  it("fetches server cells when run + projection + axes set", async () => {
    const fetchFn = vi.fn().mockResolvedValue(HEATMAP);
    const { result } = renderHook(
      () => useHeatmapAggregation({ runId: "run-1", projectionId: "proj-1", axisY: "R1", axisX: "R2", fetchFn }),
      { wrapper: wrap() },
    );
    await waitFor(() => expect(result.current.data).not.toBeNull());
    expect(result.current.data?.cells[0].best_scalar).toBe(0.1);
    expect(fetchFn).toHaveBeenCalledWith("run-1", { axis_y: "R1", axis_x: "R2", projection_id: "proj-1" });
  });

  it("is disabled until run + projection + both axes are present", () => {
    const fetchFn = vi.fn();
    renderHook(() => useHeatmapAggregation({ runId: "run-1", projectionId: null, axisY: "R1", axisX: "R2", fetchFn }), { wrapper: wrap() });
    expect(fetchFn).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement**

Create `use-heatmap-aggregation.ts`:
```ts
import { useQuery } from "@tanstack/react-query";

import type { HeatmapResponse } from "@/shared/lib/api/model";
import { STALE_TIME } from "@/shared/lib/query-defaults";

type HeatmapBody = { axis_y: string; axis_x: string; projection_id: string };

export type UseHeatmapAggregationParams = {
  runId: string | null;
  projectionId: string | null;
  axisY: string;
  axisX: string;
  enabled?: boolean;
  fetchFn?: (runId: string, body: HeatmapBody) => Promise<HeatmapResponse>;
};

export function useHeatmapAggregation({
  runId,
  projectionId,
  axisY,
  axisX,
  enabled = true,
  fetchFn = defaultFetchFn,
}: UseHeatmapAggregationParams): { data: HeatmapResponse | null; isLoading: boolean; error: Error | null } {
  const queryEnabled = enabled && !!runId && !!projectionId && !!axisY && !!axisX;
  const query = useQuery({
    queryKey: ["sar-heatmap", runId, projectionId, axisY, axisX],
    queryFn: () =>
      fetchFn(runId as string, { axis_y: axisY, axis_x: axisX, projection_id: projectionId as string }),
    enabled: queryEnabled,
    staleTime: STALE_TIME.MEDIUM,
  });
  return { data: query.data ?? null, isLoading: query.isLoading && queryEnabled, error: (query.error as Error | null) ?? null };
}

async function defaultFetchFn(runId: string, body: HeatmapBody): Promise<HeatmapResponse> {
  const { decompositionHeatmapApiV1SarDecompositionRunIdHeatmapPost } = await import(
    "@/shared/lib/api/sar-analysis/sar-analysis"
  );
  return decompositionHeatmapApiV1SarDecompositionRunIdHeatmapPost(runId, body) as unknown as HeatmapResponse;
}
```

- [ ] **Step 4: Run → pass; commit**

```bash
git add src/features/sar-analysis/hooks/use-heatmap-aggregation.ts src/features/sar-analysis/hooks/use-heatmap-aggregation.test.ts && git commit -m "feat(sar): useHeatmapAggregation hook (server cells, axis-keyed cache)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Frontend — `useDecompositionRows` (Infinite Row Model datasource)

Returns a stable AG-Grid `IDatasource` whose `getRows` POSTs `/rows`, plus `activityReference` (captured from each response so the table shades consistently across pages). `RGroupRow` gains `activity` + `activitySnapshot`.

**Files:**
- Create: `frontend/src/features/sar-analysis/hooks/use-decomposition-rows.ts`
- Test: `frontend/src/features/sar-analysis/hooks/use-decomposition-rows.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { renderHook, waitFor } from "@testing-library/react";
import type { IGetRowsParams } from "ag-grid-community";
import { describe, expect, it, vi } from "vitest";
import { useDecompositionRows } from "./use-decomposition-rows";

const PAGE = {
  rows: [
    { molecule_id: "m1", smiles: "Fc1ccccc1", registration_number: "CV-1", name: null, rgroups: { R1: "F" }, mw: 96, clogp: 1.8, tpsa: 0, activity: 0.1, activity_snapshot: { value: 0.1 } },
  ],
  total: 1,
  activity_reference: 0.1,
};

function getRowsParams(over: Partial<IGetRowsParams> = {}): IGetRowsParams {
  return {
    startRow: 0, endRow: 100, sortModel: [], filterModel: {},
    successCallback: vi.fn(), failCallback: vi.fn(), context: {},
    ...over,
  } as unknown as IGetRowsParams;
}

describe("useDecompositionRows", () => {
  it("builds a datasource whose getRows POSTs /rows and maps server rows", async () => {
    const fetchFn = vi.fn().mockResolvedValue(PAGE);
    const { result } = renderHook(() => useDecompositionRows("run-1", "proj-1", { fetchFn }));
    const ds = result.current.datasource;
    expect(ds).not.toBeNull();
    const params = getRowsParams({ sortModel: [{ colId: "mw", sort: "asc" }] as never });
    await ds!.getRows(params);
    expect(fetchFn).toHaveBeenCalledWith("run-1", {
      offset: 0, limit: 100, sort: [{ col: "molecular_weight", dir: "asc" }], filter: undefined, projection_id: "proj-1",
    });
    expect(params.successCallback).toHaveBeenCalledWith([expect.objectContaining({ id: "m1", activity: 0.1 })], 1);
    await waitFor(() => expect(result.current.activityReference).toBe(0.1));
  });

  it("calls failCallback when the fetch throws", async () => {
    const fetchFn = vi.fn().mockRejectedValue(new Error("boom"));
    const { result } = renderHook(() => useDecompositionRows("run-1", null, { fetchFn }));
    const params = getRowsParams();
    await result.current.datasource!.getRows(params);
    expect(params.failCallback).toHaveBeenCalled();
  });

  it("returns a null datasource without a runId", () => {
    const { result } = renderHook(() => useDecompositionRows(null, null, { fetchFn: vi.fn() }));
    expect(result.current.datasource).toBeNull();
  });
});
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement**

Create `use-decomposition-rows.ts`:
```ts
import type { IDatasource, IGetRowsParams } from "ag-grid-community";
import { useMemo, useState } from "react";

import type { ActivityValue } from "@/features/research-organization/types";
import type { DecompositionRowsResponse } from "@/shared/lib/api/model";
import { colIdToBackendKey, agFilterModelToParam } from "../lib/ag-filter-model";

/** The table's row shape — server `/rows` row mapped to AG-Grid row data. */
export interface RGroupRow {
  id: string;
  registration_number: string | null;
  name: string | null;
  smiles: string | null;
  rgroups: Record<string, string>;
  mw: number | null;
  clogp: number | null;
  tpsa: number | null;
  activity: number | null;
  activitySnapshot: ActivityValue | null;
}

type RowsBody = {
  offset: number;
  limit: number;
  sort: { col: string; dir: "asc" | "desc" }[];
  filter: Record<string, unknown> | undefined;
  projection_id: string | undefined;
};

export type UseDecompositionRowsReturn = {
  datasource: IDatasource | null;
  activityReference: number | null;
};

export function useDecompositionRows(
  runId: string | null,
  projectionId?: string | null,
  opts?: { fetchFn?: (runId: string, body: RowsBody) => Promise<DecompositionRowsResponse> },
): UseDecompositionRowsReturn {
  const fetchFn = opts?.fetchFn ?? defaultFetchRows;
  const [activityReference, setActivityReference] = useState<number | null>(null);

  const datasource = useMemo<IDatasource | null>(() => {
    if (!runId) return null;
    return {
      getRows: async (params: IGetRowsParams) => {
        const body: RowsBody = {
          offset: params.startRow,
          limit: params.endRow - params.startRow,
          sort: params.sortModel
            .map((s) => ({ col: colIdToBackendKey(s.colId), dir: s.sort as "asc" | "desc" }))
            .filter((s): s is { col: string; dir: "asc" | "desc" } => s.col !== null),
          filter: agFilterModelToParam(params.filterModel as Record<string, never>),
          projection_id: projectionId ?? undefined,
        };
        try {
          const res = await fetchFn(runId, body);
          setActivityReference(res.activity_reference ?? null);
          params.successCallback(res.rows.map(toRow), res.total);
        } catch {
          params.failCallback();
        }
      },
    };
    // setActivityReference is stable; runId/projectionId/fetchFn are the real deps.
  }, [runId, projectionId, fetchFn]);

  return { datasource, activityReference };
}

function toRow(r: DecompositionRowsResponse["rows"][number]): RGroupRow {
  return {
    id: r.molecule_id,
    registration_number: r.registration_number ?? null,
    name: r.name ?? null,
    smiles: r.smiles ?? null,
    rgroups: r.rgroups,
    mw: r.mw ?? null,
    clogp: r.clogp ?? null,
    tpsa: r.tpsa ?? null,
    activity: r.activity ?? null,
    activitySnapshot: (r.activity_snapshot as ActivityValue | null) ?? null,
  };
}

async function defaultFetchRows(runId: string, body: RowsBody): Promise<DecompositionRowsResponse> {
  const { decompositionRowsApiV1SarDecompositionRunIdRowsPost } = await import(
    "@/shared/lib/api/sar-analysis/sar-analysis"
  );
  return decompositionRowsApiV1SarDecompositionRunIdRowsPost(runId, body) as unknown as DecompositionRowsResponse;
}
```

- [ ] **Step 4: Run → pass; commit**

```bash
git add src/features/sar-analysis/hooks/use-decomposition-rows.ts src/features/sar-analysis/hooks/use-decomposition-rows.test.ts && git commit -m "feat(sar): useDecompositionRows infinite datasource + activity_reference" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Frontend — rewrite `rgroup-table.tsx` (server datasource)

Keep every pure helper (`buildRGroupColumns`, `pickReference`, `potencyShade`, `snapshotFromActivity`) and the renderers; replace the data source. `RGroupRow` moves to `use-decomposition-rows.ts` (imported here). `buildActivityColumns` now reads the per-row server `activity` + `activitySnapshot` and the server `activity_reference`. Selection passes the selected rows (id + label) up so the save dialog no longer needs `props.molecules`.

**Files:**
- Modify (rewrite): `frontend/src/features/sar-analysis/components/rgroup-table.tsx`
- Test: `frontend/src/features/sar-analysis/components/rgroup-table.test.tsx` (replace the old buildRGroupRows test)

- [ ] **Step 1: Write the failing test** — `rgroup-table.test.tsx` (pure-helper coverage; the grid wiring is covered by the hook + E2E):

```tsx
import { describe, expect, it } from "vitest";
import { buildActivityColumns, pickReference, potencyShade } from "./rgroup-table";

const SPEC = { protocolId: "p", column: "drc:rd", interceptKey: null, source: "dr_curve", label: "IC50" } as const;

describe("rgroup-table pure helpers (kept)", () => {
  it("pickReference = min non-null (most potent)", () => {
    expect(pickReference([5, null, 0.2, 1])).toBe(0.2);
    expect(pickReference([null, null])).toBeNull();
  });

  it("potencyShade greens the reference, reds far-off", () => {
    expect(potencyShade(0.2, 0.2)).toContain("green");
    expect(potencyShade(50, 0.2)).toContain("red");
    expect(potencyShade(null, 0.2)).toBe("");
  });

  it("buildActivityColumns reads row.activity + shades dr_curve by the server reference", () => {
    const cols = buildActivityColumns(SPEC, 0.2);
    const valueCol = cols.find((c) => c.colId === "activity:value");
    expect(valueCol?.headerName).toBe("IC50");
    // value getter pulls the per-row scalar
    expect(valueCol?.valueGetter?.({ data: { activity: 1.0 } } as never)).toBe(1.0);
    // cellClass present for dr_curve (shading), absent for readout_data
    expect(valueCol?.cellClass).toBeDefined();
    const ro = buildActivityColumns({ ...SPEC, source: "readout_data" }, 0.2).find((c) => c.colId === "activity:value");
    expect(ro?.cellClass).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run → fail** (old test referenced `buildRGroupRows`; new signature for `buildActivityColumns`).

- [ ] **Step 3: Rewrite `rgroup-table.tsx`** — replace the whole file:

```tsx
"use client";

import { DoseResponseCell } from "@/features/research-organization/components/search/dose-response-cell";
import {
  CurveExpandDialog,
  type ExpandedCurve,
} from "@/features/screen-campaign/components/grid/curve-expand-dialog";
import type { CurveSnapshot } from "@/features/screening-assay/components/dose-response-figure";
import { structureColumn } from "@/features/screening-assay/components/grid-columns";
import type { ActivityValue } from "@/features/research-organization/types";
import { StructureThumbnail } from "@/shared/components/chemistry";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { Button } from "@/shared/components/ui/button";
import { formatMeasurementValue } from "@/shared/lib/format-number";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { useMemo, useState } from "react";
import { type RGroupRow, useDecompositionRows } from "../hooks/use-decomposition-rows";
import type { SarColorSpec } from "../lib/sar-color-spec";
import { fragmentDisplay } from "../lib/sar-fragment-label";

export interface RGroupTableProps {
  runId: string;
  projectionId?: string | null;
  labels: string[];
  colorSpec?: SarColorSpec | null;
  /** Receives the selected (loaded) rows so the save dialog can preview them
   *  without `props.molecules`. */
  onSaveSelection: (rows: { id: string; label: string }[]) => void;
}

/** Structure + Compound + one column per R-group + (optional) activity + physchem. */
export function buildRGroupColumns(
  labels: string[],
  activityColumns: ColDef<RGroupRow>[] = [],
): ColDef<RGroupRow>[] {
  const cols: ColDef<RGroupRow>[] = [structureColumn<RGroupRow>((r) => r.smiles)];
  cols.push({
    headerName: "Compound",
    colId: "registration_number",
    width: 130,
    valueGetter: (p) => p.data?.registration_number ?? "",
  });
  for (const label of labels) {
    cols.push({
      headerName: label,
      colId: `rg:${label}`,
      width: 160,
      // R-group sort + text filter are server-applied (mapped via colIdToBackendKey).
      sortable: true,
      valueGetter: (p) => p.data?.rgroups[label] ?? "",
      cellRenderer: (p: ICellRendererParams<RGroupRow>) => {
        const smi = p.data?.rgroups[label];
        if (!smi) return <span className="text-muted-foreground">—</span>;
        const frag = fragmentDisplay(smi);
        if (frag.isHydrogen) {
          return (
            <div className="flex h-full items-center" title={frag.title}>
              <span className="text-muted-foreground">{frag.label}</span>
            </div>
          );
        }
        return (
          <div className="flex h-full items-center gap-1.5" title={frag.title}>
            {frag.thumbnailSmiles && (
              <StructureThumbnail smiles={frag.thumbnailSmiles} size={64} className="shrink-0" />
            )}
            <span className="break-all text-[11px] font-medium">{frag.label}</span>
          </div>
        );
      },
    });
  }
  cols.push(...activityColumns);
  cols.push(
    {
      headerName: "MW",
      colId: "mw",
      width: 90,
      type: "numericColumn",
      valueGetter: (p) => p.data?.mw ?? null,
      valueFormatter: (p) => (p.value != null ? Number(p.value).toFixed(1) : "—"),
    },
    {
      headerName: "cLogP",
      colId: "clogp",
      width: 90,
      type: "numericColumn",
      valueGetter: (p) => p.data?.clogp ?? null,
      valueFormatter: (p) => (p.value != null ? Number(p.value).toFixed(2) : "—"),
    },
    {
      headerName: "TPSA",
      colId: "tpsa",
      width: 90,
      type: "numericColumn",
      valueGetter: (p) => p.data?.tpsa ?? null,
      valueFormatter: (p) => (p.value != null ? Number(p.value).toFixed(1) : "—"),
    },
  );
  return cols;
}

/** Most-potent (min) reference scalar — LOWER-is-better (dr_curve only). */
export function pickReference(scalars: (number | null)[]): number | null {
  let ref: number | null = null;
  for (const s of scalars) {
    if (s == null || !Number.isFinite(s)) continue;
    if (ref == null || s < ref) ref = s;
  }
  return ref;
}

/** Green→red potency ramp by fold-off from the most-potent reference (dr_curve only). */
export function potencyShade(scalar: number | null, reference: number | null): string {
  if (scalar == null || reference == null) return "";
  if (!Number.isFinite(scalar) || !Number.isFinite(reference) || reference <= 0) return "";
  const fold = scalar / reference;
  if (fold <= 1) return "bg-green-600/30 text-green-900 dark:text-green-100";
  if (fold <= 3) return "bg-green-500/20 text-green-900 dark:text-green-100";
  if (fold <= 10) return "bg-amber-500/20 text-amber-900 dark:text-amber-100";
  if (fold <= 100) return "bg-orange-500/25 text-orange-900 dark:text-orange-100";
  return "bg-red-600/30 text-red-900 dark:text-red-100";
}

/** Map a DR `ActivityValue` snapshot → the shared `CurveSnapshot` for expand. */
export function snapshotFromActivity(av: ActivityValue | undefined | null): CurveSnapshot | null {
  if (
    !av ||
    !av.raw_data ||
    av.raw_data.length === 0 ||
    av.source !== "dose_response" ||
    av.curve_params == null ||
    av.value == null
  ) {
    return null;
  }
  return {
    fitted_value: av.value,
    top: av.curve_params.top,
    bottom: av.curve_params.bottom,
    hill_slope: av.curve_params.hill_slope,
    r_squared: av.r_squared,
    curve_class: av.curve_params.curve_class ?? null,
    raw_data: av.raw_data,
    additional_curves: av.additional_curves ?? null,
    aggregate: av.aggregate ?? null,
  };
}

/**
 * Activity value + plot columns, fed from the server per-row `activity` /
 * `activitySnapshot` and the server `reference` (min scalar across the filtered
 * set). Shading is gated to `dr_curve` (lower-is-better); `readout_data` renders
 * the value uncolored.
 */
export function buildActivityColumns(
  colorSpec: SarColorSpec,
  reference: number | null,
): ColDef<RGroupRow>[] {
  const shadeByPotency = colorSpec.source === "dr_curve";
  return [
    {
      headerName: colorSpec.label,
      colId: "activity:value",
      width: 150,
      type: "numericColumn",
      valueGetter: (p) => p.data?.activity ?? null,
      valueFormatter: (p) => {
        if (p.value == null) return "—";
        const unit = p.data?.activitySnapshot?.unit ? ` ${p.data.activitySnapshot.unit}` : "";
        return `${formatMeasurementValue(p.value as number)}${unit}`;
      },
      cellClass: shadeByPotency ? (p) => potencyShade(p.data?.activity ?? null, reference) : undefined,
    },
    {
      headerName: "Plot",
      colId: "activity:plot",
      width: 240,
      sortable: false,
      filter: false,
      cellRenderer: (p: ICellRendererParams<RGroupRow>) => (
        <DoseResponseCell value={p.data?.activitySnapshot ?? undefined} />
      ),
    },
  ];
}

export function RGroupTable({ runId, projectionId, labels, colorSpec, onSaveSelection }: RGroupTableProps) {
  const [openCurve, setOpenCurve] = useState<ExpandedCurve | null>(null);
  const { datasource, activityReference } = useDecompositionRows(runId, projectionId ?? null);

  const columns = useMemo(() => {
    if (!colorSpec) return buildRGroupColumns(labels);
    return buildRGroupColumns(labels, buildActivityColumns(colorSpec, activityReference));
  }, [labels, colorSpec, activityReference]);

  const handleRowClick = colorSpec
    ? (row: RGroupRow) => {
        const snapshot = snapshotFromActivity(row.activitySnapshot);
        if (!snapshot) return;
        setOpenCurve({
          ...snapshot,
          unit: row.activitySnapshot?.unit ?? null,
          moleculeLabel: row.registration_number ?? row.name ?? row.id,
          channelLabel: colorSpec.label,
        });
      }
    : undefined;

  return (
    <>
      <DataGrid<RGroupRow>
        rowData={undefined}
        datasource={datasource ?? undefined}
        columnDefs={columns}
        height="70vh"
        rowHeight={112}
        getRowId={(params) => params.data.id}
        searchPlaceholder={false}
        onRowClick={handleRowClick}
        selectionToolbar={(selected) => (
          <Button
            size="sm"
            onClick={() =>
              onSaveSelection(
                selected.map((r) => ({ id: r.id, label: r.registration_number ?? r.name ?? r.id })),
              )
            }
          >
            Save as collection ({selected.length})
          </Button>
        )}
      />
      <CurveExpandDialog data={openCurve} onOpenChange={(open) => !open && setOpenCurve(null)} />
    </>
  );
}
```

- [ ] **Step 4: Run → pass; commit**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/components/rgroup-table.test.tsx && pnpm exec biome check src/features/sar-analysis/components/rgroup-table.tsx`

```bash
git add src/features/sar-analysis/components/rgroup-table.tsx src/features/sar-analysis/components/rgroup-table.test.tsx && git commit -m "feat(sar): server-driven RGroupTable (infinite datasource, server activity)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Frontend — rewrite `rgroup-heatmap.tsx` (server cells)

Replace `buildHeatmapGrid` + `bestMoleculeId` with `useHeatmapAggregation`. Keep `AxisFragment`, the grid table, gap cells, legend, `pickReference`/`potencyShade`/`snapshotFromActivity`. Add an honest "top 30 of N" banner when `truncated`.

**Files:**
- Modify (rewrite): `frontend/src/features/sar-analysis/components/rgroup-heatmap.tsx`
- Test: `frontend/src/features/sar-analysis/components/rgroup-heatmap.test.tsx`

- [ ] **Step 1: Write the failing test** (cell-lookup + reference helper):

```tsx
import { describe, expect, it } from "vitest";
import { cellKey, heatmapReference } from "./rgroup-heatmap";

describe("rgroup-heatmap helpers", () => {
  it("cellKey is stable + collision-free", () => {
    expect(cellKey("F", "Cl")).toBe(cellKey("F", "Cl"));
    expect(cellKey("F", "Cl")).not.toBe(cellKey("Cl", "F"));
  });
  it("heatmapReference = min best_scalar across cells", () => {
    expect(
      heatmapReference([
        { best_scalar: 5 },
        { best_scalar: 0.1 },
        { best_scalar: null },
      ] as never),
    ).toBe(0.1);
  });
});
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Rewrite `rgroup-heatmap.tsx`** — replace the whole file:

```tsx
"use client";

/**
 * 2-axis R-group heatmap — server-aggregated. Pick two R-positions → POST
 * /heatmap → a grid of (Ry × Rx) cells, each with the most-potent (argmin)
 * representative + count + a curve snapshot. Coloring reuses the table's
 * `pickReference`/`potencyShade` over the (small) returned cells, gated to
 * `dr_curve`. Click a cell → expand its representative's DR curve off the
 * server `best_snapshot`. Axes that exceed the server top-30 cap surface an
 * honest "top 30 of N" note.
 */

import {
  CurveExpandDialog,
  type ExpandedCurve,
} from "@/features/screen-campaign/components/grid/curve-expand-dialog";
import type { CurveSnapshot } from "@/features/screening-assay/components/dose-response-figure";
import { StructureThumbnail } from "@/shared/components/chemistry";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import type { HeatmapCellView } from "@/shared/lib/api/model";
import { formatMeasurementValue } from "@/shared/lib/format-number";
import { cn } from "@/shared/lib/utils";
import { useMemo, useState } from "react";
import { useHeatmapAggregation } from "../hooks/use-heatmap-aggregation";
import type { SarColorSpec } from "../lib/sar-color-spec";
import { fragmentDisplay } from "../lib/sar-fragment-label";
import { pickReference, potencyShade, snapshotFromActivity } from "./rgroup-table";

export interface RGroupHeatmapProps {
  runId: string;
  projectionId: string;
  labels: string[];
  colorSpec: SarColorSpec;
}

const GAP_CLASS =
  "bg-[repeating-linear-gradient(45deg,transparent,transparent_5px,var(--color-muted)_5px,var(--color-muted)_7px)]";

/** Stable, collision-free key for a (y, x) cell. */
export function cellKey(y: string, x: string): string {
  return JSON.stringify([y, x]);
}

/** Most-potent (min) best_scalar across the returned cells — the ramp anchor. */
export function heatmapReference(cells: Pick<HeatmapCellView, "best_scalar">[]): number | null {
  return pickReference(cells.map((c) => c.best_scalar));
}

function AxisFragment({ smiles, orientation }: { smiles: string; orientation: "col" | "row" }) {
  const frag = fragmentDisplay(smiles);
  return (
    <div
      className={cn(
        orientation === "col"
          ? "flex w-20 flex-col items-center gap-0.5"
          : "flex w-24 items-center gap-1",
      )}
      title={frag.title}
    >
      {frag.thumbnailSmiles && (
        <StructureThumbnail
          smiles={frag.thumbnailSmiles}
          size={32}
          className={orientation === "row" ? "shrink-0" : undefined}
        />
      )}
      <span className="break-all text-[9px] leading-tight text-muted-foreground">{frag.label}</span>
    </div>
  );
}

export function RGroupHeatmap({ runId, projectionId, labels, colorSpec }: RGroupHeatmapProps) {
  const [axisY, setAxisY] = useState<string>(() => labels[0] ?? "");
  const [axisX, setAxisX] = useState<string>(() => labels[1] ?? "");
  const [openCurve, setOpenCurve] = useState<ExpandedCurve | null>(null);

  const { data, isLoading } = useHeatmapAggregation({ runId, projectionId, axisY, axisX });

  const shadeByPotency = colorSpec.source === "dr_curve";
  const reference = useMemo(() => (data ? heatmapReference(data.cells) : null), [data]);
  const cellsByKey = useMemo(() => {
    const m = new Map<string, HeatmapCellView>();
    for (const c of data?.cells ?? []) m.set(cellKey(c.y, c.x), c);
    return m;
  }, [data]);

  if (labels.length < 2) {
    return <p className="text-xs text-muted-foreground">Need at least two R-group positions for a heatmap.</p>;
  }
  if (isLoading || !data) {
    return <p className="text-xs text-muted-foreground">Computing heatmap…</p>;
  }

  function handleCellClick(cell: HeatmapCellView) {
    const snapshot: CurveSnapshot | null = snapshotFromActivity(cell.best_snapshot as never);
    if (!snapshot) return;
    setOpenCurve({
      ...snapshot,
      unit: (cell.best_snapshot as { unit?: string | null })?.unit ?? null,
      moleculeLabel: cell.best_molecule_label,
      channelLabel: colorSpec.label,
    });
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-muted-foreground">Rows (Y):</span>
        <Select value={axisY} onValueChange={setAxisY}>
          <SelectTrigger className="h-7 w-28 text-xs" aria-label="Y axis position">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {labels.map((l) => (
              <SelectItem key={l} value={l} className="text-xs">{l}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-muted-foreground">Columns (X):</span>
        <Select value={axisX} onValueChange={setAxisX}>
          <SelectTrigger className="h-7 w-28 text-xs" aria-label="X axis position">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {labels.map((l) => (
              <SelectItem key={l} value={l} className="text-xs">{l}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        {axisY === axisX && (
          <span className="text-amber-700 dark:text-amber-300">Same position on both axes — diagonal only.</span>
        )}
        {data.truncated && (
          <span className="text-amber-700 dark:text-amber-300">
            Showing top {data.y_values.length} of {data.y_total} {axisY} × top {data.x_values.length} of {data.x_total} {axisX} (most-populated).
          </span>
        )}
      </div>

      <div className="overflow-auto">
        <table className="border-separate border-spacing-1 text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-background p-1 text-left align-bottom font-medium text-muted-foreground">
                {axisY} ↓ / {axisX} →
              </th>
              {data.x_values.map((x) => (
                <th key={x} className="p-1 align-bottom font-normal" scope="col">
                  <AxisFragment smiles={x} orientation="col" />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.y_values.map((y) => (
              <tr key={y}>
                <th scope="row" className="sticky left-0 z-10 bg-background p-1 text-left align-middle font-normal">
                  <AxisFragment smiles={y} orientation="row" />
                </th>
                {data.x_values.map((x) => {
                  const cell = cellsByKey.get(cellKey(y, x));
                  if (!cell) {
                    return (
                      <td
                        key={x}
                        className={cn(
                          "h-16 w-20 rounded border border-dashed border-muted-foreground/30 text-center align-middle text-muted-foreground/50",
                          GAP_CLASS,
                        )}
                        title="No compound with this combination — make?"
                      >
                        <span className="text-[10px]">make?</span>
                      </td>
                    );
                  }
                  const shade = shadeByPotency ? potencyShade(cell.best_scalar, reference) : "";
                  const unit = (cell.best_snapshot as { unit?: string | null })?.unit
                    ? ` ${(cell.best_snapshot as { unit?: string | null }).unit}`
                    : "";
                  const extra = cell.count - 1;
                  return (
                    <td key={x} className="p-0">
                      <button
                        type="button"
                        className={cn(
                          "flex h-16 w-20 cursor-pointer flex-col items-center justify-center gap-0.5 rounded border border-border text-center",
                          shade || "bg-muted/30",
                        )}
                        onClick={() => handleCellClick(cell)}
                        title={`${cell.count} compound(s)`}
                      >
                        <span className="font-medium tabular-nums">
                          {cell.best_scalar != null ? `${formatMeasurementValue(cell.best_scalar)}${unit}` : "—"}
                        </span>
                        {extra > 0 && (
                          <span className="rounded-full bg-foreground/10 px-1.5 text-[10px] text-muted-foreground">
                            +{extra}
                          </span>
                        )}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
        <span className="font-medium text-foreground">{colorSpec.label}</span>
        {shadeByPotency ? (
          <>
            <span>potent</span>
            <span className="h-3 w-5 rounded bg-green-600/30" />
            <span className="h-3 w-5 rounded bg-green-500/20" />
            <span className="h-3 w-5 rounded bg-amber-500/20" />
            <span className="h-3 w-5 rounded bg-orange-500/25" />
            <span className="h-3 w-5 rounded bg-red-600/30" />
            <span>weak</span>
          </>
        ) : (
          <span>higher-is-better readout — cells show the best value (uncolored).</span>
        )}
      </div>

      <CurveExpandDialog data={openCurve} onOpenChange={(open) => !open && setOpenCurve(null)} />
    </div>
  );
}
```

- [ ] **Step 4: Run → pass; commit**

```bash
git add src/features/sar-analysis/components/rgroup-heatmap.tsx src/features/sar-analysis/components/rgroup-heatmap.test.tsx && git commit -m "feat(sar): server-aggregated RGroupHeatmap (useHeatmapAggregation cells)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Frontend — rewrite `sar-view.tsx` orchestration

`core → useDecompositionRun`; `colorSpec → useActivityProjection`; **prefer `collectionId`** (full collection). Pass `runId`/`projectionId`/`labels` into the table/heatmap; gate on `status === "ready"`. Counts banner honest from the run header. Save dialog previews the selected rows (no `props.molecules`).

**Files:**
- Modify (rewrite): `frontend/src/features/sar-analysis/components/sar-view.tsx`
- Test: `frontend/src/features/sar-analysis/components/sar-view.test.tsx` (optional render smoke — keep light; logic lives in the hooks)

- [ ] **Step 1: Rewrite `sar-view.tsx`** — replace the whole file:

```tsx
"use client";

import type { Molecule } from "@/features/chemical-registration/types";
import { useCreateCollection } from "@/features/research-organization/hooks/use-collections";
import type { AggregationMode } from "@/features/research-organization/lib/use-aggregation-mode";
import { Button } from "@/shared/components/ui/button";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { showError } from "@/shared/lib/toast";
import { useState } from "react";
import { channelFromColorSpec, useActivityProjection } from "../hooks/use-activity-projection";
import { useDecompositionRun } from "../hooks/use-decomposition-run";
import type { SarColorSpec } from "../lib/sar-color-spec";
import { readSarHandoff } from "../lib/sar-handoff";
import { RGroupColorControl } from "./rgroup-color-control";
import { RGroupCorePicker } from "./rgroup-core-picker";
import { RGroupHeatmap } from "./rgroup-heatmap";
import { RGroupTable } from "./rgroup-table";
import { SaveSelectionDialog } from "./save-selection-dialog";

export interface SarViewProps {
  molecules: Molecule[];
  collectionId?: string;
  projects: { id: string; name: string }[];
  defaultProjectId: string | null;
  sourceLabel: string;
}

type SaveRow = { id: string; label: string };

export function SarView(props: SarViewProps) {
  // Prefer the collection (full membership, server-expanded) over the loaded page.
  const moleculeIds = props.molecules.map((m) => m.id);
  const source = props.collectionId
    ? { collectionId: props.collectionId }
    : { moleculeIds };

  const createCollection = useCreateCollection();
  const [core, setCore] = useState<string | null>(() => readSarHandoff()?.coreSmiles ?? null);
  const [saveRows, setSaveRows] = useState<SaveRow[] | null>(null);
  const [colorSpec, setColorSpec] = useState<SarColorSpec | null>(null);
  const [aggMode, setAggMode] = useState<AggregationMode>("latest");
  const [sub, setSub] = useState<"table" | "heatmap">("table");

  const run = useDecompositionRun({ ...source, coreSmiles: core });
  const channel = colorSpec ? channelFromColorSpec(colorSpec, aggMode) : null;
  const projection = useActivityProjection({ ...source, channel });

  const ready = run.status === "ready" && run.runId != null;
  const projectionReady = projection.status === "ready" && projection.projectionId != null;
  const heatmapEnabled = ready && run.labels.length >= 2 && colorSpec != null && projectionReady;
  const showHeatmap = sub === "heatmap" && heatmapEnabled;

  return (
    <div className="flex flex-col gap-3">
      <RGroupColorControl
        projectIds={undefined}
        value={colorSpec}
        onChange={setColorSpec}
        aggregationMode={aggMode}
        onAggregationChange={setAggMode}
      />

      <RGroupCorePicker
        collectionId={props.collectionId}
        moleculeIds={moleculeIds}
        coreSmiles={core}
        onCoreChange={setCore}
        matchedCount={run.counts?.matched}
        totalCount={run.counts?.total}
      />

      {(run.isStarting || run.isPolling) && (
        <p className="text-xs text-muted-foreground">Decomposing…</p>
      )}
      {colorSpec != null && (projection.isStarting || projection.isPolling) && (
        <p className="text-xs text-muted-foreground">Computing activity…</p>
      )}
      {run.error && <p className="text-xs text-destructive">Decomposition failed: {run.error.message}</p>}

      {ready && (
        <div
          role="group"
          aria-label="SAR result view"
          className="inline-flex items-center gap-1 self-start rounded-md border border-input p-0.5"
        >
          <Button
            type="button"
            variant={!showHeatmap ? "default" : "ghost"}
            size="sm"
            className="h-7 gap-1.5 px-2"
            aria-pressed={!showHeatmap}
            onClick={() => setSub("table")}
          >
            <span className="text-xs">Table</span>
          </Button>
          <Button
            type="button"
            variant={showHeatmap ? "default" : "ghost"}
            size="sm"
            className="h-7 gap-1.5 px-2"
            aria-pressed={showHeatmap}
            disabled={!heatmapEnabled}
            title={!heatmapEnabled ? "Pick an activity and a core with ≥2 R-positions" : undefined}
            onClick={() => setSub("heatmap")}
          >
            <span className="text-xs">Heatmap</span>
          </Button>
        </div>
      )}

      {ready && run.runId && (
        <p className="text-xs text-muted-foreground">
          {run.counts?.matched ?? 0} matched of {run.counts?.total ?? 0} ({run.counts?.unmatched ?? 0} unmatched)
        </p>
      )}

      {ready && run.runId &&
        (showHeatmap && colorSpec && projection.projectionId ? (
          <RGroupHeatmap
            runId={run.runId}
            projectionId={projection.projectionId}
            labels={run.labels}
            colorSpec={colorSpec}
          />
        ) : (
          <RGroupTable
            runId={run.runId}
            projectionId={projectionReady ? projection.projectionId : null}
            labels={run.labels}
            colorSpec={colorSpec}
            onSaveSelection={setSaveRows}
          />
        ))}

      <SaveSelectionDialog
        open={saveRows != null}
        onOpenChange={(o) => !o && setSaveRows(null)}
        onSave={async ({ name, projectId, moleculeIds: selectedIds }) => {
          const created = await new Promise<{ id: string }>((resolve, reject) =>
            createCollection.mutate(
              { name, project_id: projectId },
              { onSuccess: (c) => resolve(c as { id: string }), onError: (err) => reject(err) },
            ),
          );
          try {
            if (selectedIds.length > 0) {
              await customInstance({
                url: `${API_V1}/collections/${created.id}/molecules`,
                method: "POST",
                data: { references: selectedIds.map((id) => ({ value: id, ref_type: "uuid" })) },
              });
            }
            setSaveRows(null);
          } catch {
            showError("Collection created, but adding compounds failed. Please retry.");
          }
        }}
        selectedMolecules={(saveRows ?? []).map((r) => ({ id: r.id, registration_number: r.label, name: r.label }))}
        defaultName={`SAR selection from ${props.sourceLabel}`}
        projects={props.projects}
        defaultProjectId={props.defaultProjectId}
      />
    </div>
  );
}
```
(If `SaveSelectionDialog`'s `selectedMolecules` prop type (`MoleculeLite`) needs more fields, adapt the mapped object to its shape — the dialog only needs id + a display label.)

- [ ] **Step 2: Typecheck + commit**

Run: `cd frontend && pnpm exec tsc --noEmit && pnpm exec biome check src/features/sar-analysis/components/sar-view.tsx`
Expected: clean (resolve any `SaveSelectionDialog` prop-shape mismatch by adjusting the mapped object).

```bash
git add src/features/sar-analysis/components/sar-view.tsx && git commit -m "feat(sar): SarView orchestration over server run + projection (full collection)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: Frontend — delete the dead client-side compute

**Files (delete):**
- `frontend/src/features/sar-analysis/hooks/use-sar-activity.ts` (+ its test)
- `frontend/src/features/sar-analysis/hooks/use-rgroup-decomposition.ts` (+ its test)
- `frontend/src/features/sar-analysis/lib/rgroup-heatmap-grid.ts` (+ its test) — `buildHeatmapGrid`/`heatmapCellKey`

- [ ] **Step 1: Delete + find stragglers**

Run:
```bash
cd frontend
rm -f src/features/sar-analysis/hooks/use-sar-activity.ts \
      src/features/sar-analysis/hooks/use-rgroup-decomposition.ts \
      src/features/sar-analysis/lib/rgroup-heatmap-grid.ts
# delete their colocated tests if present:
git ls-files 'src/features/sar-analysis/**/*use-sar-activity*' 'src/features/sar-analysis/**/*use-rgroup-decomposition*' 'src/features/sar-analysis/**/*rgroup-heatmap-grid*' | xargs -r rm -f
# find any remaining importers (should be none after Tasks 10-12):
grep -Rn "use-sar-activity\|use-rgroup-decomposition\|rgroup-heatmap-grid\|buildRGroupRows\|buildHeatmapGrid\|bestMoleculeId" src/ || echo "no stragglers"
```
Expected: `no stragglers`. If any importer remains, it's a miss from Tasks 10–12 — fix it there.

- [ ] **Step 2: Prune the orval barrel if a schema was dropped**

Run: `cd frontend && grep -n "rGroupDecompositionResponse\|RGroupDecompositionResponse" src/shared/lib/api/model/index.ts || echo "barrel ok"`
If the old sync `RGroupDecompositionResponse` schema is gone from the backend OpenAPI (it was replaced in Unit A), orval leaves a dangling `export * from './rGroupDecompositionResponse'` — remove that one line by hand (orval never prunes the barrel).

- [ ] **Step 3: Typecheck + biome + commit**

Run: `cd frontend && pnpm exec tsc --noEmit && pnpm exec biome check src/features/sar-analysis`
Expected: clean.

```bash
git add -A src/features/sar-analysis src/shared/lib/api/model/index.ts && git commit -m "refactor(sar): delete client-side decomposition/activity/heatmap compute" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: E2E + final verification

- [ ] **Step 1: Playwright smoke** (optional but recommended) — create `frontend/tests/e2e/sar-workbench.spec.ts`:

A smoke flow against a seeded collection: open a collection's SAR view → a core auto-suggests (or draw one) → "Decomposing…" resolves → the table shows server rows + a footer count → pick an activity channel → "Computing activity…" resolves → the activity column appears → sort by activity + apply a number filter (rows update) → switch to Heatmap → cells render → click a cell → curve dialog opens. Mirror the existing Playwright setup in `frontend/tests/e2e/` (auth fixture, seeded data). If the project's E2E seeding can't easily produce activity data, assert the decomposition table + sort + filter (the activity-dependent steps can be a follow-up in Unit C's polish pass — note it).

Run: `cd frontend && pnpm exec playwright test sar-workbench`
Expected: PASS (or the reduced decomposition-only smoke if activity seeding is deferred — log what was skipped).

- [ ] **Step 2: Full FE gates**

Run:
```bash
cd frontend && pnpm exec vitest run src/features/sar-analysis src/shared/components/data-grid \
  && pnpm exec tsc --noEmit \
  && pnpm exec biome check src/features/sar-analysis src/shared/components/data-grid
```
Expected: all PASS; tsc clean; biome clean.

- [ ] **Step 3: Backend gates (no regression from Tasks 1–2)**

Run:
```bash
cd backend && uv run pytest tests/integration/persistence/sar_analysis tests/api/test_sar_analysis_routes.py tests/api/test_sar_activity_projection_routes.py -q \
  && uv run lint-imports && uv run ruff check src/ && uv run ruff format --check src/
```
Expected: all PASS; lint/import clean. (`ruff` flags only the pre-existing Part-1b files in `docs/backlog/part1b-ruff-debt.md` — unrelated; clear that backlog item in a separate commit if you want the gate fully green.)

- [ ] **Step 4: Manual smoke (optional) + push**

Bring the app up (`make dev`), open a large collection's SAR view, confirm: full-collection decomposition (footer "of N matched" exceeds one page), server sort + filter, activity coloring, heatmap axis swap + curve-expand, and "Save selected → collection". Then:

```bash
git push -u origin "$(git rev-parse --abbrev-ref HEAD)"
```

**Unit B complete.** Unit C remains: server-side "Save all N matched → collection" (`POST /sar/decomposition/{run_id}/save-collection`), loading/empty/cancel-state + honest-label copy polish, perf indexes (`rgroups->>'R1'` expression + join indexes), the domain-model deviation note (`RGroupDecompositionRun` + `SarActivityProjection` in `docs/domain-model/04-sar-analysis.md`), and the GitHub board update.

---

## Self-review notes (author)

- **Spec coverage:** the 4 hooks (§3) → Tasks 6–9; `DataGrid` datasource (§3) → Task 5; server-side filtering (§4) → Tasks 1 + 4 + 9; the table/heatmap/SarView swap (§5) → Tasks 10–12; delete list (§5) → Task 13; save staging + functional states (§6) → Tasks 12/14; E2E (§6) → Task 14. The §-refinement (`activity_snapshot` + `activity_reference` on `/rows`, needed for the table's plot column + shading under pagination) → Task 2.
- **Type consistency:** `RGroupRow` is defined once (in `use-decomposition-rows.ts`) and imported by `rgroup-table.tsx`; `colIdToBackendKey` is shared by the filter mapper (Task 4) and the sort mapping (Task 9); `channelFromColorSpec` (Task 7) is consumed by `SarView` (Task 12); the orval function names are predicted and explicitly flagged for verification in Tasks 3/6/7/8/9.
- **No placeholders:** every step has complete code or an exact command + expected output. The one judgement call (E2E activity-seeding depth) is explicitly bounded with a documented fallback.
- **Footgun coverage:** stable memoized `datasource` (Task 9) + memoized `job` refs (Tasks 6/7) address the grid-reset / poll-storm gotcha called out in the spec.
