# SAR Unit C · Item 1 — Server-side "Save all N matched → collection" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a chemist save every matched compound — or every match under the current column filter — from the SAR table as a new collection in one click, resolved server-side over the full collection.

**Architecture:** New `POST /sar/decomposition/{run_id}/save-collection` resolves all matching `molecule_id`s via the existing row reader (same `_scoped_join` + `_activity_join` + `_apply_filter` the `/rows` endpoint uses), then reuses the `CreateCollection` + `AddMoleculesToCollection` application use cases (uuid refs) to create + populate the collection. The FE adds an always-visible toolbar action that passes the live AG-Grid `filterModel` (and `projection_id` when an activity filter is in play) so the saved set equals exactly what the table shows.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy 2.0 async / Lagom DI / dry-python returns · Next.js / React 19 / TypeScript / AG Grid Community / vitest. Spec: `docs/superpowers/specs/2026-06-15-sar-unit-c-item1-save-collection-design.md`.

**Conventions (every task):**
- Commit with explicit pathspec: `git commit -m "…" -- <paths>`; trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- BE gate (scope ruff to touched files — `src/`-wide has pre-existing debt): `cd backend && uv run pytest <paths> -q && uv run lint-imports && uv run ruff check <touched> && uv run ruff format --check <touched>`.
- FE gate: `cd frontend && pnpm exec biome check --write <files> && pnpm exec biome check <files> && pnpm exec vitest run <paths> && pnpm exec tsc --noEmit`. Verify by **exit code**, never piped output.

---

## Task 1: Reader `fetch_matched_ids` (id-only query)

**Files:**
- Modify: `backend/src/cellar/application/sar_analysis/decomposition_rows.py` (add to `DecompositionRowReader` Protocol)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/decomposition_row_reader.py`
- Test: `backend/tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py`

- [ ] **Step 1: Write the failing tests** — append to the integration test file (reuses the file's existing `_seed_org` / `_seed_molecule` / `_seed_ready_run` helpers + `uow` fixture + `RGroupAssignment`, `SQLAlchemyRGroupDecompositionRunReader` imports already at top):

```python
@pytest.mark.asyncio
async def test_fetch_matched_ids_returns_all_matched(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        a = await _seed_molecule(uow, ws, org, reg="CV-A", smiles="Fc1ccccc1")
        b = await _seed_molecule(uow, ws, org, reg="CV-B", smiles="Clc1ccccc1")
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.write_assignments(run.id, [
            RGroupAssignment(molecule_id=a, rgroups={"R1": "F"}),
            RGroupAssignment(molecule_id=b, rgroups={"R1": "Cl"}),
        ])
        await uow.commit()
    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        ids = await reader.fetch_matched_ids(run.id, workspace_id=ws)
    assert set(ids) == {a, b}


@pytest.mark.asyncio
async def test_fetch_matched_ids_applies_text_filter(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        a = await _seed_molecule(uow, ws, org, reg="CV-A", smiles="Fc1ccccc1")
        b = await _seed_molecule(uow, ws, org, reg="CV-B", smiles="Clc1ccccc1")
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.write_assignments(run.id, [
            RGroupAssignment(molecule_id=a, rgroups={"R1": "F"}),
            RGroupAssignment(molecule_id=b, rgroups={"R1": "Cl"}),
        ])
        await uow.commit()
    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        ids = await reader.fetch_matched_ids(
            run.id, workspace_id=ws, filter={"R1": {"kind": "text", "op": "eq", "value": "Cl"}}
        )
    assert ids == [b]


@pytest.mark.asyncio
async def test_fetch_matched_ids_excludes_merged_and_other_workspace(uow):
    ws = uuid.uuid4()
    other_ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        keep = await _seed_molecule(uow, ws, org, reg="CV-A", smiles="Fc1ccccc1")
        merged = await _seed_molecule(
            uow, ws, org, reg="CV-M", smiles="Clc1ccccc1", merged=keep
        )
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.write_assignments(run.id, [
            RGroupAssignment(molecule_id=keep, rgroups={"R1": "F"}),
            RGroupAssignment(molecule_id=merged, rgroups={"R1": "Cl"}),
        ])
        await uow.commit()
    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        ids = await reader.fetch_matched_ids(run.id, workspace_id=ws)
        wrong_ws = await reader.fetch_matched_ids(run.id, workspace_id=other_ws)
    assert ids == [keep]          # merged-into row excluded
    assert wrong_ws == []         # workspace-scoped
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py -k fetch_matched_ids -q`
Expected: FAIL — `AttributeError: 'SQLAlchemyDecompositionRowReader' object has no attribute 'fetch_matched_ids'`.

- [ ] **Step 3: Add the Protocol method** — in `decomposition_rows.py`, inside `class DecompositionRowReader(Protocol)`, after `count_rows`:

```python
    async def fetch_matched_ids(
        self,
        run_id: UUID,
        *,
        workspace_id: UUID,
        projection_id: UUID | None = None,
        filter: dict[str, Any] | None = None,
    ) -> list[UUID]: ...
```

- [ ] **Step 4: Implement** — in `decomposition_row_reader.py`, add a method to `SQLAlchemyDecompositionRowReader` (after `count_rows`):

```python
    async def fetch_matched_ids(
        self,
        run_id: UUID,
        *,
        workspace_id: UUID,
        projection_id: UUID | None = None,
        filter: dict[str, Any] | None = None,
    ) -> list[UUID]:
        # Identical scoped/activity joins + filter as count_rows, but project the
        # molecule_id instead of counting — so the resolved set equals exactly the
        # filtered total the table shows. One row per molecule per run.
        stmt = self._scoped_join(select(RGroupAssignmentModel.molecule_id), run_id, workspace_id)
        stmt = self._activity_join(stmt, projection_id)
        stmt = _apply_filter(stmt, filter, projection_id=projection_id)
        result = await self._uow.session.execute(stmt)
        return [row[0] for row in result.all()]
```

- [ ] **Step 5: Run to verify pass**

Run: `cd backend && uv run pytest tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py -k fetch_matched_ids -q`
Expected: PASS (3 tests).

- [ ] **Step 6: Gate + commit**

```bash
cd backend && uv run pytest tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py -q \
 && uv run lint-imports \
 && uv run ruff check src/cellar/application/sar_analysis/decomposition_rows.py src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/decomposition_row_reader.py tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py \
 && uv run ruff format --check src/cellar/application/sar_analysis/decomposition_rows.py src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/decomposition_row_reader.py tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py
git commit -m "feat(sar): fetch_matched_ids reader — resolve all matched molecule ids under filter

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/application/sar_analysis/decomposition_rows.py src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/decomposition_row_reader.py tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py
```

---

## Task 2: `SaveDecompositionCollection` use case

**Files:**
- Create: `backend/src/cellar/application/sar_analysis/save_decomposition_collection.py`
- Test: `backend/tests/unit/application/sar_analysis/test_save_decomposition_collection.py`

- [ ] **Step 1: Write the failing test** (fakes mirror the `FakeUoW`/`FakeRepo` style in `tests/unit/application/sar_analysis/test_get_cancel_activity_projection.py`):

```python
from __future__ import annotations

import uuid

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.collection_membership import MembershipResult
from cellar.application.shared.molecule_resolver import RefType
from cellar.application.sar_analysis.save_decomposition_collection import (
    SaveDecompositionCollection,
    SaveDecompositionCollectionInput,
)
from cellar.domain.shared.errors import NotFoundError, ValidationError


class FakeUoW:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeRunRepo:
    def __init__(self, exists=True):
        self._exists = exists

    async def find_by_id(self, run_id, *, workspace_id):
        return object() if self._exists else None


class FakeProjRepo:
    def __init__(self, exists=True):
        self._exists = exists

    async def find_by_id(self, projection_id, *, workspace_id):
        return object() if self._exists else None


class FakeReader:
    def __init__(self, ids):
        self.ids = ids
        self.calls = []

    async def fetch_matched_ids(self, run_id, *, workspace_id, projection_id=None, filter=None):
        self.calls.append((run_id, workspace_id, projection_id, filter))
        return self.ids


class FakeCreate:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def __call__(self, cmd, auth=None):
        self.calls.append(cmd)
        return self.result


class FakeCollection:
    def __init__(self, cid):
        self.id = cid


class FakeAdd:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def __call__(self, cmd, auth=None):
        self.calls.append(cmd)
        return self.result


def _input(**over):
    base = dict(
        run_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        requested_by=uuid.uuid4(),
        name="Series A",
        project_id=None,
        filter=None,
        projection_id=None,
    )
    base.update(over)
    return SaveDecompositionCollectionInput(**base)


def _uc(*, ids, run=True, proj=True, create=None, add=None):
    cid = uuid.uuid4()
    create = create if create is not None else Success(FakeCollection(cid))
    add = add if add is not None else Success(MembershipResult(added=list(ids), already_present=0, unresolved=[]))
    fc, fa = FakeCreate(create), FakeAdd(add)
    uc = SaveDecompositionCollection(
        run_repository=FakeRunRepo(run),
        projection_repository=FakeProjRepo(proj),
        reader=FakeReader(ids),
        create_collection=fc,
        add_molecules=fa,
        uow=FakeUoW(),
    )
    return uc, fc, fa, cid


@pytest.mark.asyncio
async def test_creates_collection_and_adds_matched_ids_as_uuid_refs():
    a, b = uuid.uuid4(), uuid.uuid4()
    uc, fc, fa, cid = _uc(ids=[a, b])
    out = await uc.execute(_input(), auth=None)
    assert isinstance(out, Success)
    assert out.unwrap() == cid
    assert len(fc.calls) == 1
    assert {r.ref_type for r in fa.calls[0].refs} == {RefType.UUID}
    assert {r.value for r in fa.calls[0].refs} == {str(a), str(b)}


@pytest.mark.asyncio
async def test_passes_filter_and_projection_to_reader():
    uc, fc, fa, cid = _uc(ids=[uuid.uuid4()])
    pid = uuid.uuid4()
    flt = {"R1": {"kind": "text", "op": "eq", "value": "Cl"}}
    await uc.execute(_input(filter=flt, projection_id=pid), auth=None)
    assert uc._reader.calls[0][2] == pid   # projection_id forwarded
    assert uc._reader.calls[0][3] == flt   # filter forwarded


@pytest.mark.asyncio
async def test_unknown_run_returns_not_found():
    uc, *_ = _uc(ids=[], run=False)
    out = await uc.execute(_input(), auth=None)
    assert isinstance(out, Failure)
    assert isinstance(out.failure(), NotFoundError)


@pytest.mark.asyncio
async def test_unknown_projection_returns_not_found():
    uc, *_ = _uc(ids=[], proj=False)
    out = await uc.execute(_input(projection_id=uuid.uuid4()), auth=None)
    assert isinstance(out, Failure)
    assert isinstance(out.failure(), NotFoundError)


@pytest.mark.asyncio
async def test_empty_match_set_creates_collection_skips_add():
    uc, fc, fa, cid = _uc(ids=[])
    out = await uc.execute(_input(), auth=None)
    assert isinstance(out, Success)
    assert out.unwrap() == cid
    assert fa.calls == []   # no add call when nothing matched


@pytest.mark.asyncio
async def test_propagates_create_failure():
    uc, fc, fa, _ = _uc(ids=[uuid.uuid4()], create=Failure(ValidationError("bad name")))
    out = await uc.execute(_input(), auth=None)
    assert isinstance(out, Failure)
    assert fa.calls == []
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis/test_save_decomposition_collection.py -q`
Expected: FAIL — `ModuleNotFoundError: …save_decomposition_collection`.

> Before writing, confirm `ValidationError` is exported from `cellar.domain.shared.errors` (`uv run python -c "from cellar.domain.shared.errors import ValidationError, NotFoundError"`). If `ValidationError` isn't present, substitute any concrete `DomainError` subclass that is (e.g. `NotFoundError`) in `test_propagates_create_failure`.

- [ ] **Step 3: Implement the use case**

```python
"""SaveDecompositionCollection — persist all matched molecules of a decomposition
run (optionally under the live grid filter) as a new collection.

Resolves the matched ``molecule_id``s via the same reader the ``/rows`` endpoint
uses (so the saved set equals the filtered total the table shows), then reuses the
``CreateCollection`` + ``AddMoleculesToCollection`` use cases (uuid refs). The
reused use cases enforce ``require_editor`` / workspace scoping.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from returns.pipeline import is_successful
from returns.result import Failure, Result, Success

from cellar.application.research_organization.collection_membership import (
    AddMoleculesToCollection,
    AddMoleculesToCollectionCommand,
)
from cellar.application.research_organization.create_collection import (
    CreateCollection,
    CreateCollectionCommand,
)
from cellar.application.sar_analysis.decomposition_rows import DecompositionRowReader
from cellar.application.sar_analysis.repositories import (
    RGroupDecompositionRunRepository,
    SarActivityProjectionRepository,
)
from cellar.application.shared.molecule_resolver import MoleculeReference, RefType
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True)
class SaveDecompositionCollectionInput:
    run_id: UUID
    workspace_id: UUID
    requested_by: UUID
    name: str
    project_id: UUID | None = None
    filter: dict[str, Any] | None = None
    projection_id: UUID | None = None


class SaveDecompositionCollection:
    def __init__(
        self,
        *,
        run_repository: RGroupDecompositionRunRepository,
        projection_repository: SarActivityProjectionRepository,
        reader: DecompositionRowReader,
        create_collection: CreateCollection,
        add_molecules: AddMoleculesToCollection,
        uow: UnitOfWork,
    ) -> None:
        self._repo = run_repository
        self._projections = projection_repository
        self._reader = reader
        self._create_collection = create_collection
        self._add_molecules = add_molecules
        self._uow = uow

    async def execute(
        self, payload: SaveDecompositionCollectionInput, auth: Any = None
    ) -> Result[UUID, DomainError]:
        async with self._uow:
            run = await self._repo.find_by_id(payload.run_id, workspace_id=payload.workspace_id)
            if run is None:
                return Failure(NotFoundError("RGroupDecompositionRun", str(payload.run_id)))
            # Validate projection ownership explicitly (mirrors FetchDecompositionRows)
            # so the activity-filter join never relies on UUID disjointness to stay
            # tenant-safe.
            if payload.projection_id is not None:
                projection = await self._projections.find_by_id(
                    payload.projection_id, workspace_id=payload.workspace_id
                )
                if projection is None:
                    return Failure(
                        NotFoundError("SarActivityProjection", str(payload.projection_id))
                    )
            ids = await self._reader.fetch_matched_ids(
                payload.run_id,
                workspace_id=payload.workspace_id,
                projection_id=payload.projection_id,
                filter=payload.filter,
            )

        create_result = await self._create_collection(
            CreateCollectionCommand(
                workspace_id=payload.workspace_id,
                name=payload.name,
                project_id=payload.project_id,
                created_by=payload.requested_by,
            ),
            auth=auth,
        )
        if not is_successful(create_result):
            return create_result  # propagate the DomainError Failure
        collection = create_result.unwrap()

        if ids:
            add_result = await self._add_molecules(
                AddMoleculesToCollectionCommand(
                    workspace_id=payload.workspace_id,
                    collection_id=collection.id,
                    refs=[MoleculeReference(value=str(i), ref_type=RefType.UUID) for i in ids],
                    added_by=payload.requested_by,
                ),
                auth=auth,
            )
            if not is_successful(add_result):
                return add_result  # propagate the DomainError Failure

        return Success(collection.id)
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis/test_save_decomposition_collection.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Gate + commit**

```bash
cd backend && uv run pytest tests/unit/application/sar_analysis/test_save_decomposition_collection.py -q \
 && uv run lint-imports \
 && uv run ruff check src/cellar/application/sar_analysis/save_decomposition_collection.py tests/unit/application/sar_analysis/test_save_decomposition_collection.py \
 && uv run ruff format --check src/cellar/application/sar_analysis/save_decomposition_collection.py tests/unit/application/sar_analysis/test_save_decomposition_collection.py
git commit -m "feat(sar): SaveDecompositionCollection use case (reuse CreateCollection + AddMolecules)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/application/sar_analysis/save_decomposition_collection.py tests/unit/application/sar_analysis/test_save_decomposition_collection.py
```

---

## Task 3: Route + DI wiring + API tests

**Files:**
- Modify: `backend/src/cellar/infrastructure/di/_sar_analysis.py` (register the use case)
- Modify: `backend/src/cellar/interface/dependencies/_sar_analysis.py` (add `SaveDecompositionCollectionDep`)
- Modify: `backend/src/cellar/interface/routes/sar_analysis.py` (request/response models + route)
- Test: `backend/tests/api/test_sar_analysis_routes.py`

- [ ] **Step 1: Write the failing API tests** — append (file already imports `uuid`, `pytest`, `AsyncClient`, `text`, `async_sessionmaker`, and has `_seed_two_molecules` + the `client`/`api_app`/`workspace_id` fixtures):

```python
async def _ready_run_id(client, ids) -> str:
    res = await client.post(
        "/api/v1/sar/decomposition",
        json={"molecule_ids": [str(i) for i in ids], "core_smiles": "c1ccccc1"},
    )
    assert res.status_code == 200, res.text
    return res.json()["run_id"]


@pytest.mark.asyncio
async def test_save_collection_creates_collection_with_all_matched(client, api_app, workspace_id):
    ids = await _seed_two_molecules(api_app, workspace_id)
    run_id = await _ready_run_id(client, ids)

    res = await client.post(
        f"/api/v1/sar/decomposition/{run_id}/save-collection",
        json={"name": "All matched"},
    )
    assert res.status_code == 201, res.text
    cid = res.json()["collection_id"]
    assert uuid.UUID(cid)

    members = await client.get(f"/api/v1/collections/{cid}/molecules")
    assert members.status_code == 200
    assert {uuid.UUID(m) for m in members.json()} == set(ids)


@pytest.mark.asyncio
async def test_save_collection_honors_rgroup_filter(client, api_app, workspace_id):
    ids = await _seed_two_molecules(api_app, workspace_id)  # CV-A=F core leaving …, CV-B=Cl
    run_id = await _ready_run_id(client, ids)
    # Filter to the bromo/chloro substituent of exactly one member via reg-number text filter.
    res = await client.post(
        f"/api/v1/sar/decomposition/{run_id}/save-collection",
        json={
            "name": "Filtered",
            "filter": {"registration_number": {"kind": "text", "op": "eq", "value": "CV-A"}},
        },
    )
    assert res.status_code == 201, res.text
    cid = res.json()["collection_id"]
    members = await client.get(f"/api/v1/collections/{cid}/molecules")
    assert {uuid.UUID(m) for m in members.json()} == {ids[0]}


@pytest.mark.asyncio
async def test_save_collection_rejects_empty_name(client, api_app, workspace_id):
    ids = await _seed_two_molecules(api_app, workspace_id)
    run_id = await _ready_run_id(client, ids)
    res = await client.post(
        f"/api/v1/sar/decomposition/{run_id}/save-collection", json={"name": "   "}
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_save_collection_unknown_run_404(client):
    res = await client.post(
        f"/api/v1/sar/decomposition/{uuid.uuid4()}/save-collection", json={"name": "x"}
    )
    assert res.status_code == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest tests/api/test_sar_analysis_routes.py -k save_collection -q`
Expected: FAIL — `404`/route-missing (and DI `KeyError` once the route exists but DI isn't wired).

- [ ] **Step 3: Register in DI** — in `infrastructure/di/_sar_analysis.py`:

Add imports (top, with the other application imports):
```python
from cellar.application.research_organization.collection_membership import AddMoleculesToCollection
from cellar.application.research_organization.create_collection import CreateCollection
from cellar.application.sar_analysis.save_decomposition_collection import SaveDecompositionCollection
```
Add a factory + define inside `register_sar_analysis`, right after the `container.define(FetchDecompositionRows, _fetch_decomposition_rows)` line:
```python
    def _save_decomposition_collection(c: Container) -> SaveDecompositionCollection:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SaveDecompositionCollection(
            run_repository=SQLAlchemyRGroupDecompositionRunRepository(uow),
            projection_repository=SQLAlchemySarActivityProjectionRepository(uow),
            reader=SQLAlchemyDecompositionRowReader(uow),
            create_collection=c[CreateCollection],
            add_molecules=c[AddMoleculesToCollection],
            uow=uow,
        )

    container.define(SaveDecompositionCollection, _save_decomposition_collection)
```

- [ ] **Step 4: Add the Dep** — in `interface/dependencies/_sar_analysis.py`:

Import: `from cellar.application.sar_analysis.save_decomposition_collection import SaveDecompositionCollection`.
Add `"SaveDecompositionCollectionDep",` to `__all__`.
Add the alias (near `FetchDecompositionRowsDep`):
```python
SaveDecompositionCollectionDep = Annotated[
    SaveDecompositionCollection, Depends(_get_use_case(SaveDecompositionCollection))
]
```

- [ ] **Step 5: Add the route** — in `interface/routes/sar_analysis.py`:

Import the use-case input + the dep:
```python
from cellar.application.sar_analysis.save_decomposition_collection import (
    SaveDecompositionCollectionInput,
)
```
Add `SaveDecompositionCollectionDep` to the existing `from cellar.interface.dependencies._sar_analysis import (...)` block.
Add models + handler (after `decomposition_rows`):
```python
class SaveCollectionRequest(BaseModel):
    name: str
    project_id: UUID | None = None
    filter: dict[str, Any] | None = None
    projection_id: UUID | None = None


class SaveCollectionResponse(BaseModel):
    collection_id: UUID


@router.post("/decomposition/{run_id}/save-collection", status_code=status.HTTP_201_CREATED)
async def save_decomposition_collection(
    run_id: UUID,
    payload: SaveCollectionRequest,
    auth: AuthDep,
    uc: SaveDecompositionCollectionDep,
) -> SaveCollectionResponse:
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="name must not be empty")
    collection_id = result_to_response(
        await uc.execute(
            SaveDecompositionCollectionInput(
                run_id=run_id,
                workspace_id=auth.workspace_id,
                requested_by=auth.user_id,
                name=payload.name.strip(),
                project_id=payload.project_id,
                filter=payload.filter,
                projection_id=payload.projection_id,
            ),
            auth=auth,
        )
    )
    return SaveCollectionResponse(collection_id=collection_id)
```

- [ ] **Step 6: Run to verify pass**

Run: `cd backend && uv run pytest tests/api/test_sar_analysis_routes.py -k save_collection -q`
Expected: PASS (4 tests). If `test_save_collection_honors_rgroup_filter` mis-asserts on which member matches the reg-number filter, the filter targets `registration_number == "CV-A"` (deterministic from `_seed_two_molecules`), so it must yield exactly `ids[0]`.

- [ ] **Step 7: Gate + commit**

```bash
cd backend && uv run pytest tests/api/test_sar_analysis_routes.py -q \
 && uv run lint-imports \
 && uv run ruff check src/cellar/infrastructure/di/_sar_analysis.py src/cellar/interface/dependencies/_sar_analysis.py src/cellar/interface/routes/sar_analysis.py tests/api/test_sar_analysis_routes.py \
 && uv run ruff format --check src/cellar/infrastructure/di/_sar_analysis.py src/cellar/interface/dependencies/_sar_analysis.py src/cellar/interface/routes/sar_analysis.py tests/api/test_sar_analysis_routes.py
git commit -m "feat(sar): POST /decomposition/{run_id}/save-collection (route + DI)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/infrastructure/di/_sar_analysis.py src/cellar/interface/dependencies/_sar_analysis.py src/cellar/interface/routes/sar_analysis.py tests/api/test_sar_analysis_routes.py
```

---

## Task 4: Regenerate orval types

**Files:**
- Modify: `frontend/src/shared/lib/api/model/*` + `frontend/src/shared/lib/api/sar-analysis/sar-analysis.ts` (generated)

- [ ] **Step 1: Confirm backend is up** — `curl -sf localhost:8000/openapi.json >/dev/null && echo up || echo START_BACKEND`. The new route auto-reloads; if down, start it.

- [ ] **Step 2: Regenerate** — `cd frontend && pnpm generate:api`

- [ ] **Step 3: Capture the generated names** (the FE hook in Task 6 uses these — generated fn names are not always the obvious slug; see the handoff gotcha):

Run: `cd frontend && grep -n "SaveCollection" src/shared/lib/api/sar-analysis/sar-analysis.ts; ls src/shared/lib/api/model | grep -i saveCollection`
Record the exact POST fn name (expected ≈ `saveDecompositionCollectionApiV1SarDecompositionRunIdSaveCollectionPost`) and the `SaveCollectionRequest` / `SaveCollectionResponse` model file names. Use these confirmed identifiers in Task 6.

- [ ] **Step 4: Review the diff** — `cd frontend && git status --short src/shared/lib/api && git diff --stat src/shared/lib/api`. Regen is additive; if `model/index.ts` gained the two new schemas and `sar-analysis.ts` gained the POST fn, proceed. (orval never prunes the barrel; nothing to hand-remove here.)

- [ ] **Step 5: Gate + commit**

```bash
cd frontend && pnpm exec tsc --noEmit
git -C /Users/sidx/workspace/chem-vault2 commit -m "chore(api): regenerate orval for save-collection route

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- frontend/src/shared/lib/api
```

---

## Task 5: `useDecompositionRows` — expose live `filterParam` + `total`

**Files:**
- Modify: `frontend/src/features/sar-analysis/hooks/use-decomposition-rows.ts`
- Test: `frontend/src/features/sar-analysis/hooks/use-decomposition-rows.test.ts`

- [ ] **Step 1: Write the failing test** — add to the existing `describe("useDecompositionRows")`:

```ts
it("exposes the live filterParam and total after a getRows call", async () => {
  const fetchFn = vi.fn().mockResolvedValue(PAGE);
  const { result } = renderHook(() => useDecompositionRows("run-1", "proj-1", { fetchFn }));
  const params = getRowsParams({
    filterModel: { mw: { filterType: "number", type: "greaterThan", filter: 400 } } as never,
  });
  await result.current.datasource?.getRows(params);
  await waitFor(() => expect(result.current.total).toBe(1));
  expect(result.current.filterParam).toEqual({
    molecular_weight: { kind: "number", op: "gt", value: 400 },
  });
});

it("filterParam is undefined when no column filter is active", async () => {
  const fetchFn = vi.fn().mockResolvedValue(PAGE);
  const { result } = renderHook(() => useDecompositionRows("run-1", null, { fetchFn }));
  await result.current.datasource?.getRows(getRowsParams());
  await waitFor(() => expect(result.current.total).toBe(1));
  expect(result.current.filterParam).toBeUndefined();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/hooks/use-decomposition-rows.test.ts`
Expected: FAIL — `result.current.total` / `filterParam` are `undefined` (not on the return type).

- [ ] **Step 3: Implement** — edit `use-decomposition-rows.ts`:

Extend the return type:
```ts
export type UseDecompositionRowsReturn = {
  datasource: IDatasource | null;
  activityReference: number | null;
  filterParam: Record<string, unknown> | undefined;
  total: number | null;
};
```
Add state next to `activityReference`:
```ts
  const [filterParam, setFilterParam] = useState<Record<string, unknown> | undefined>(undefined);
  const [total, setTotal] = useState<number | null>(null);
```
Inside `getRows`, after `const res = await fetchFn(runId, body);`:
```ts
        setActivityReference(res.activity_reference ?? null);
        setFilterParam(body.filter);
        setTotal(res.total);
```
Return all four:
```ts
  return { datasource, activityReference, filterParam, total };
```

- [ ] **Step 4: Run to verify pass**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/hooks/use-decomposition-rows.test.ts`
Expected: PASS.

- [ ] **Step 5: Gate + commit**

```bash
cd frontend && pnpm exec biome check --write src/features/sar-analysis/hooks/use-decomposition-rows.ts src/features/sar-analysis/hooks/use-decomposition-rows.test.ts \
 && pnpm exec biome check src/features/sar-analysis/hooks/use-decomposition-rows.ts src/features/sar-analysis/hooks/use-decomposition-rows.test.ts \
 && pnpm exec vitest run src/features/sar-analysis/hooks/use-decomposition-rows.test.ts \
 && pnpm exec tsc --noEmit
git -C /Users/sidx/workspace/chem-vault2 commit -m "feat(sar): useDecompositionRows exposes live filterParam + total

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- frontend/src/features/sar-analysis/hooks/use-decomposition-rows.ts frontend/src/features/sar-analysis/hooks/use-decomposition-rows.test.ts
```

---

## Task 6: `useSaveDecompositionCollection` hook

**Files:**
- Create: `frontend/src/features/sar-analysis/hooks/use-save-decomposition-collection.ts`
- Test: `frontend/src/features/sar-analysis/hooks/use-save-decomposition-collection.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useSaveDecompositionCollection } from "./use-save-decomposition-collection";

describe("useSaveDecompositionCollection", () => {
  it("posts name/project/filter/projection and returns the new collection id", async () => {
    const fetchFn = vi.fn().mockResolvedValue({ collection_id: "coll-9" });
    const { result } = renderHook(() => useSaveDecompositionCollection({ fetchFn }));
    const out = await result.current.saveAll({
      runId: "run-1",
      name: "Series A",
      projectId: "p1",
      filter: { molecular_weight: { kind: "number", op: "gt", value: 400 } },
      projectionId: "proj-1",
    });
    expect(out).toEqual({ collection_id: "coll-9" });
    expect(fetchFn).toHaveBeenCalledWith("run-1", {
      name: "Series A",
      project_id: "p1",
      filter: { molecular_weight: { kind: "number", op: "gt", value: 400 } },
      projection_id: "proj-1",
    });
  });

  it("omits filter/projection when not provided", async () => {
    const fetchFn = vi.fn().mockResolvedValue({ collection_id: "coll-1" });
    const { result } = renderHook(() => useSaveDecompositionCollection({ fetchFn }));
    await result.current.saveAll({ runId: "run-1", name: "All", projectId: null });
    expect(fetchFn).toHaveBeenCalledWith("run-1", {
      name: "All",
      project_id: null,
      filter: undefined,
      projection_id: undefined,
    });
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/hooks/use-save-decomposition-collection.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement** (mirrors `use-decomposition-rows.ts`'s `fetchFn` seam + dynamic import of the generated fn; **replace the generated fn name with the one confirmed in Task 4 Step 3**):

```ts
import { useCallback } from "react";

import type { SaveCollectionResponse } from "@/shared/lib/api/model";

export type SaveAllArgs = {
  runId: string;
  name: string;
  projectId: string | null;
  filter?: Record<string, unknown>;
  projectionId?: string | null;
};

type SaveBody = {
  name: string;
  project_id: string | null;
  filter: Record<string, unknown> | undefined;
  projection_id: string | undefined;
};

export function useSaveDecompositionCollection(opts?: {
  fetchFn?: (runId: string, body: SaveBody) => Promise<SaveCollectionResponse>;
}) {
  const fetchFn = opts?.fetchFn ?? defaultSave;
  const saveAll = useCallback(
    (args: SaveAllArgs): Promise<SaveCollectionResponse> =>
      fetchFn(args.runId, {
        name: args.name,
        project_id: args.projectId,
        filter: args.filter,
        projection_id: args.projectionId ?? undefined,
      }),
    [fetchFn],
  );
  return { saveAll };
}

async function defaultSave(runId: string, body: SaveBody): Promise<SaveCollectionResponse> {
  const { saveDecompositionCollectionApiV1SarDecompositionRunIdSaveCollectionPost } = await import(
    "@/shared/lib/api/sar-analysis/sar-analysis"
  );
  return saveDecompositionCollectionApiV1SarDecompositionRunIdSaveCollectionPost(
    runId,
    body as unknown as Parameters<
      typeof saveDecompositionCollectionApiV1SarDecompositionRunIdSaveCollectionPost
    >[1],
  ) as unknown as SaveCollectionResponse;
}
```

> If Task 4 reported a different generated fn name or response type alias, swap both occurrences here. If orval emitted the response as `SaveCollectionResponse` under a different barrel name, import that name instead.

- [ ] **Step 4: Run to verify pass + types**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/hooks/use-save-decomposition-collection.test.ts && pnpm exec tsc --noEmit`
Expected: PASS + tsc clean.

- [ ] **Step 5: Gate + commit**

```bash
cd frontend && pnpm exec biome check --write src/features/sar-analysis/hooks/use-save-decomposition-collection.ts src/features/sar-analysis/hooks/use-save-decomposition-collection.test.ts \
 && pnpm exec biome check src/features/sar-analysis/hooks/use-save-decomposition-collection.ts src/features/sar-analysis/hooks/use-save-decomposition-collection.test.ts \
 && pnpm exec vitest run src/features/sar-analysis/hooks/use-save-decomposition-collection.test.ts \
 && pnpm exec tsc --noEmit
git -C /Users/sidx/workspace/chem-vault2 commit -m "feat(sar): useSaveDecompositionCollection hook

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- frontend/src/features/sar-analysis/hooks/use-save-decomposition-collection.ts frontend/src/features/sar-analysis/hooks/use-save-decomposition-collection.test.ts
```

---

## Task 7: `SaveSelectionDialog` → name/project collector (count + optional preview) + adapt `SarView` selection path

**Files:**
- Modify: `frontend/src/features/sar-analysis/components/save-selection-dialog.tsx`
- Modify: `frontend/src/features/sar-analysis/components/sar-view.tsx` (keep the existing selection path working under the new dialog API — no all-matched wiring yet)
- Test: `frontend/src/features/sar-analysis/components/save-selection-dialog.test.tsx`

- [ ] **Step 1: Update the dialog test** — rewrite `save-selection-dialog.test.tsx` to the new contract (`count` drives title + gating, `preview` optional, `onSave({name, projectId})`). Read the current file first to preserve its render/setup helpers; the assertions become:

```ts
// title reflects `count`
expect(screen.getByText(/Save 3 compounds as a new collection/i)).toBeInTheDocument();
// onSave receives only name + projectId
fireEvent.click(screen.getByRole("button", { name: /save/i }));
await waitFor(() =>
  expect(onSave).toHaveBeenCalledWith({ name: expect.any(String), projectId: null }),
);
// save disabled when count === 0
// (render with count={0} → the save button is disabled)
```
Keep one case asserting the preview list renders when `preview` is passed, and is absent when omitted.

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/components/save-selection-dialog.test.tsx`
Expected: FAIL — prop/Type mismatch (`count`/`preview` not yet supported).

- [ ] **Step 3: Implement the dialog refactor** — `save-selection-dialog.tsx`:

```tsx
interface SaveSelectionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (args: { name: string; projectId: string | null }) => Promise<void>;
  count: number;
  preview?: MoleculeLite[];
  defaultName: string;
  projects: ProjectOption[];
  defaultProjectId: string | null;
}
```
- Title: `Save {count} compounds as a new collection`.
- Render the preview `<ul>` block only when `preview && preview.length > 0`.
- Save button `disabled={saving || !name.trim() || count === 0}`.
- onClick: `await onSave({ name: name.trim(), projectId });`.

- [ ] **Step 4: Adapt `SarView`'s existing selection path** — in `sar-view.tsx`, the dialog's `onSave` no longer returns `moleculeIds`. Keep the selection ids in `SarView` state (already there as `saveRows`) and read from it:

Change the `SaveSelectionDialog` usage:
```tsx
<SaveSelectionDialog
  open={saveRows != null}
  onOpenChange={(o) => !o && setSaveRows(null)}
  onSave={async ({ name, projectId }) => {
    const selectedIds = (saveRows ?? []).map((r) => r.id);
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
  count={(saveRows ?? []).length}
  preview={(saveRows ?? []).map((r) => ({ id: r.id, reg_number: r.label, name: r.label }))}
  defaultName={`SAR selection from ${props.sourceLabel}`}
  projects={props.projects}
  defaultProjectId={props.defaultProjectId}
/>
```

- [ ] **Step 5: Run to verify pass** (dialog test + the unchanged sar-view test — its dialog mock passes an extra `moleculeIds` which SarView now ignores, reading ids from `saveRows`):

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/components/save-selection-dialog.test.tsx src/features/sar-analysis/components/sar-view.test.tsx && pnpm exec tsc --noEmit`
Expected: PASS + tsc clean.

- [ ] **Step 6: Gate + commit**

```bash
cd frontend && pnpm exec biome check --write src/features/sar-analysis/components/save-selection-dialog.tsx src/features/sar-analysis/components/save-selection-dialog.test.tsx src/features/sar-analysis/components/sar-view.tsx \
 && pnpm exec biome check src/features/sar-analysis/components/save-selection-dialog.tsx src/features/sar-analysis/components/save-selection-dialog.test.tsx src/features/sar-analysis/components/sar-view.tsx \
 && pnpm exec vitest run src/features/sar-analysis/components/save-selection-dialog.test.tsx src/features/sar-analysis/components/sar-view.test.tsx \
 && pnpm exec tsc --noEmit
git -C /Users/sidx/workspace/chem-vault2 commit -m "refactor(sar): SaveSelectionDialog → name/project collector (count + optional preview)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- frontend/src/features/sar-analysis/components/save-selection-dialog.tsx frontend/src/features/sar-analysis/components/save-selection-dialog.test.tsx frontend/src/features/sar-analysis/components/sar-view.tsx
```

---

## Task 8: `RGroupTable` — always-visible "Save all/filtered" toolbar action

**Files:**
- Modify: `frontend/src/features/sar-analysis/components/rgroup-table.tsx`
- Test: `frontend/src/features/sar-analysis/components/rgroup-table.test.tsx`

- [ ] **Step 1: Write the failing pure-helper test** — append to `rgroup-table.test.tsx` (render-flow stays in E2E; unit-test the label/disabled logic, matching the file's pure-helper convention). Add `saveAllLabel`, `canSaveAll` to the import on line 2:

```ts
describe("save-all toolbar action helpers", () => {
  it("labels matched vs filtered by filter state", () => {
    expect(saveAllLabel(1234, false)).toBe("Save all 1234 matched");
    expect(saveAllLabel(320, true)).toBe("Save 320 filtered");
    expect(saveAllLabel(null, false)).toBe("Save all 0 matched");
  });
  it("canSaveAll gates null/zero", () => {
    expect(canSaveAll(5)).toBe(true);
    expect(canSaveAll(0)).toBe(false);
    expect(canSaveAll(null)).toBe(false);
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/components/rgroup-table.test.tsx`
Expected: FAIL — `saveAllLabel`/`canSaveAll` are not exported.

- [ ] **Step 3: Implement** — in `rgroup-table.tsx`:

Add exported helpers (next to the other exported helpers):
```ts
/** Toolbar label for the save-all action: matched (no filter) vs filtered. */
export function saveAllLabel(count: number | null, filterActive: boolean): string {
  const n = count ?? 0;
  return filterActive ? `Save ${n} filtered` : `Save all ${n} matched`;
}

/** Save-all is actionable only with a known, positive count. */
export function canSaveAll(count: number | null): boolean {
  return count != null && count > 0;
}
```
Extend `RGroupTableProps`:
```ts
  /** Total matched (pre-filter) baseline for the toolbar count before the first
   *  page returns; the live filtered `total` from the rows hook supersedes it. */
  matchedCount?: number;
  /** Save every matched compound under the current filter (server-resolved). */
  onSaveAll?: (args: {
    count: number;
    filter?: Record<string, unknown>;
    projectionId?: string | null;
  }) => void;
```
In the component body, pull the live filter + total from the hook and derive the action:
```ts
  const { datasource, activityReference, filterParam, total } = useDecompositionRows(
    runId,
    projectionId ?? null,
  );
  const filterActive = !!filterParam && Object.keys(filterParam).length > 0;
  const saveAllCount = total ?? matchedCount ?? null;
```
Pass a `toolbarActions` to `DataGrid` (renders even when empty/loading) when `onSaveAll` is provided:
```tsx
        toolbarActions={
          onSaveAll ? (
            <Button
              size="sm"
              variant="outline"
              disabled={!canSaveAll(saveAllCount)}
              onClick={() =>
                onSaveAll({
                  count: saveAllCount ?? 0,
                  filter: filterActive ? filterParam : undefined,
                  projectionId: projectionId ?? null,
                })
              }
            >
              {saveAllLabel(saveAllCount, filterActive)}
            </Button>
          ) : undefined
        }
```

- [ ] **Step 4: Run to verify pass**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/components/rgroup-table.test.tsx && pnpm exec tsc --noEmit`
Expected: PASS + tsc clean (existing `SarView` doesn't pass `onSaveAll` yet → button hidden, no behavior change).

- [ ] **Step 5: Gate + commit**

```bash
cd frontend && pnpm exec biome check --write src/features/sar-analysis/components/rgroup-table.tsx src/features/sar-analysis/components/rgroup-table.test.tsx \
 && pnpm exec biome check src/features/sar-analysis/components/rgroup-table.tsx src/features/sar-analysis/components/rgroup-table.test.tsx \
 && pnpm exec vitest run src/features/sar-analysis/components/rgroup-table.test.tsx \
 && pnpm exec tsc --noEmit
git -C /Users/sidx/workspace/chem-vault2 commit -m "feat(sar): RGroupTable save-all/filtered toolbar action (opt-in)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- frontend/src/features/sar-analysis/components/rgroup-table.tsx frontend/src/features/sar-analysis/components/rgroup-table.test.tsx
```

---

## Task 9: `SarView` — wire the all-matched save intent

**Files:**
- Modify: `frontend/src/features/sar-analysis/components/sar-view.tsx`
- Test: `frontend/src/features/sar-analysis/components/sar-view.test.tsx`

- [ ] **Step 1: Update the test** — in `sar-view.test.tsx`:

Add a mock for the new hook (top, with the other `vi.mock`s):
```ts
const mockSaveAll = vi.fn().mockResolvedValue({ collection_id: "all-coll" });
vi.mock("../hooks/use-save-decomposition-collection", () => ({
  useSaveDecompositionCollection: () => ({ saveAll: mockSaveAll }),
}));
```
Extend the `rgroup-table` mock to expose the all-matched trigger:
```tsx
vi.mock("./rgroup-table", () => ({
  RGroupTable: ({
    onSaveSelection,
    onSaveAll,
  }: {
    onSaveSelection: (rows: { id: string; label: string }[]) => void;
    onSaveAll?: (a: { count: number; filter?: Record<string, unknown>; projectionId?: string | null }) => void;
  }) => (
    <div data-testid="rgroup-table">
      <button type="button" data-testid="save-selection" onClick={() => onSaveSelection([{ id: "m1", label: "CV-1" }])}>
        save
      </button>
      <button
        type="button"
        data-testid="save-all"
        onClick={() => onSaveAll?.({ count: 8, filter: { molecular_weight: { kind: "number", op: "gt", value: 400 } }, projectionId: "proj-1" })}
      >
        save all
      </button>
    </div>
  ),
}));
```
Update the `save-selection-dialog` mock's `onSave` to the new signature `({ name, projectId })` and clear `mockSaveAll` in `beforeEach`. Add a test:
```ts
it("saves all matched via the server endpoint with the live filter + projection", async () => {
  renderSarView();
  fireEvent.click(screen.getByTestId("save-all"));
  fireEvent.click(await screen.findByTestId("confirm-save"));
  await waitFor(() =>
    expect(mockSaveAll).toHaveBeenCalledWith({
      runId: "run-1",
      name: "Series A",
      projectId: null,
      filter: { molecular_weight: { kind: "number", op: "gt", value: 400 } },
      projectionId: "proj-1",
    }),
  );
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/components/sar-view.test.tsx`
Expected: FAIL — `mockSaveAll` never called (no all-matched wiring).

- [ ] **Step 3: Implement** — in `sar-view.tsx`:

Import the hook: `import { useSaveDecompositionCollection } from "../hooks/use-save-decomposition-collection";`
Replace the `SaveRow[] | null` state with a discriminated intent:
```ts
type SaveIntent =
  | { mode: "selection"; rows: SaveRow[] }
  | { mode: "all"; count: number; filter?: Record<string, unknown>; projectionId?: string | null };
```
```ts
  const [saveIntent, setSaveIntent] = useState<SaveIntent | null>(null);
  const saveCollection = useSaveDecompositionCollection();
```
Pass the new props to `RGroupTable` (in the `ready && run.runId && (...)` table branch):
```tsx
          <RGroupTable
            runId={run.runId}
            projectionId={projectionReady ? projection.projectionId : null}
            labels={run.labels}
            colorSpec={colorSpec}
            matchedCount={run.counts?.matched}
            onSaveSelection={(rows) => setSaveIntent({ mode: "selection", rows })}
            onSaveAll={({ count, filter, projectionId }) =>
              setSaveIntent({ mode: "all", count, filter, projectionId })
            }
          />
```
Replace the `SaveSelectionDialog` block with the intent-driven version:
```tsx
      <SaveSelectionDialog
        open={saveIntent != null}
        onOpenChange={(o) => !o && setSaveIntent(null)}
        onSave={async ({ name, projectId }) => {
          if (saveIntent?.mode === "all") {
            try {
              await saveCollection.saveAll({
                runId: run.runId as string,
                name,
                projectId,
                filter: saveIntent.filter,
                projectionId: saveIntent.projectionId,
              });
              setSaveIntent(null);
            } catch {
              showError("Could not save the collection. Please retry.");
            }
            return;
          }
          const selectedIds = saveIntent?.mode === "selection" ? saveIntent.rows.map((r) => r.id) : [];
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
            setSaveIntent(null);
          } catch {
            showError("Collection created, but adding compounds failed. Please retry.");
          }
        }}
        count={
          saveIntent?.mode === "all"
            ? saveIntent.count
            : saveIntent?.mode === "selection"
              ? saveIntent.rows.length
              : 0
        }
        preview={
          saveIntent?.mode === "selection"
            ? saveIntent.rows.map((r) => ({ id: r.id, reg_number: r.label, name: r.label }))
            : undefined
        }
        defaultName={`SAR selection from ${props.sourceLabel}`}
        projects={props.projects}
        defaultProjectId={props.defaultProjectId}
      />
```
Remove the now-unused `saveRows`/`setSaveRows` state and the old `SaveRow[]` usage (keep the `SaveRow` type — referenced by `SaveIntent`).

- [ ] **Step 4: Run to verify pass**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/components/sar-view.test.tsx && pnpm exec tsc --noEmit`
Expected: PASS (incl. the existing selection-save test) + tsc clean.

- [ ] **Step 5: Gate + commit**

```bash
cd frontend && pnpm exec biome check --write src/features/sar-analysis/components/sar-view.tsx src/features/sar-analysis/components/sar-view.test.tsx \
 && pnpm exec biome check src/features/sar-analysis/components/sar-view.tsx src/features/sar-analysis/components/sar-view.test.tsx \
 && pnpm exec vitest run src/features/sar-analysis/components/sar-view.test.tsx \
 && pnpm exec tsc --noEmit
git -C /Users/sidx/workspace/chem-vault2 commit -m "feat(sar): SarView wires save-all-matched via server endpoint

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- frontend/src/features/sar-analysis/components/sar-view.tsx frontend/src/features/sar-analysis/components/sar-view.test.tsx
```

---

## Task 10: Full-slice verification

- [ ] **Step 1: BE — run all touched suites + global checks**

Run:
```bash
cd backend && uv run pytest tests/unit/application/sar_analysis/test_save_decomposition_collection.py tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py tests/api/test_sar_analysis_routes.py -q \
 && uv run lint-imports
```
Expected: all PASS; import contracts kept.

- [ ] **Step 2: FE — run the SAR feature suite + global tsc/biome on touched files**

Run:
```bash
cd frontend && pnpm exec vitest run src/features/sar-analysis \
 && pnpm exec tsc --noEmit \
 && pnpm exec biome check src/features/sar-analysis/hooks/use-decomposition-rows.ts src/features/sar-analysis/hooks/use-save-decomposition-collection.ts src/features/sar-analysis/components/save-selection-dialog.tsx src/features/sar-analysis/components/rgroup-table.tsx src/features/sar-analysis/components/sar-view.tsx
```
Expected: all PASS; tsc clean; biome exit 0.

- [ ] **Step 3: Manual smoke (optional but recommended)** — with backend + frontend up, open SAR over a collection, draw/pick a core, let "Decomposing…" resolve, confirm the toolbar shows "Save all N matched", click → name/project dialog → save → the new collection exists with N members. Apply a column filter and confirm the label switches to "Save N filtered" and saves the filtered subset.

- [ ] **Step 4: Update the handoff** — tick item 1 in `docs/superpowers/specs/2026-06-15-sar-unit-c-handoff.md` (mark done with the commit range). Commit:
```bash
git -C /Users/sidx/workspace/chem-vault2 add -f docs/superpowers/specs/2026-06-15-sar-unit-c-handoff.md
git -C /Users/sidx/workspace/chem-vault2 commit -m "docs(sar): mark Unit C item 1 (save-all-matched) done

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- docs/superpowers/specs/2026-06-15-sar-unit-c-handoff.md
```

---

## Self-review notes (coverage)
- **Spec → tasks:** reader `fetch_matched_ids` (T1) · use case w/ projection validation + reuse (T2) · route+DI+API incl. filter/404/empty-name (T3) · orval (T4) · hook filterParam/total (T5) · save hook (T6) · dialog count/preview (T7) · toolbar action label/disabled (T8) · SarView intent + filter-aware save (T9) · verification + edge smoke (T10). Activity-filter correctness rides on `projection_id` being forwarded (T2 `test_passes_filter_and_projection_to_reader` + reader reusing `_activity_join`/`_apply_filter` already covered by `count_rows` activity tests).
- **Type consistency:** `saveAll({runId,name,projectId,filter?,projectionId?})` (T6) ↔ RGroupTable `onSaveAll({count,filter?,projectionId?})` (T8) ↔ SarView intent `{mode:"all",count,filter?,projectionId?}` (T9); dialog `onSave({name,projectId})` + `count` + `preview?` consistent across T7/T9; backend `SaveCollectionRequest{name,project_id?,filter?,projection_id?}` ↔ hook body mapping (T6).
- **Deferred (not this slice):** full component render-flow → E2E (handoff item 6); navigate-to-new-collection after save (applies to both paths; revisit separately).
