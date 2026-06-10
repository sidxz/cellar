# SAR Workbench — Backend R-group Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a backend endpoint that decomposes a set of compounds against a chosen core into R-group columns (`POST /api/v1/sar/r-group-decomposition`), the data the Phase-1 SAR table + heatmap consume.

**Architecture:** DDD layers mirroring the existing scaffold-tree feature. A pure-data result VO in **domain**; a `Protocol` **port** + use case in **application**; a stateless RDKit wrapper in **infrastructure** (concrete impl of the port, wired by DI); a thin FastAPI route in **interface**. Activity columns are NOT part of this plan — the frontend reuses the existing `/search/execute` enrichment for those. Compute is synchronous (typical series are small); the scaffold-tree async job pattern is the fallback if needed later.

**Tech Stack:** Python 3.13 / RDKit (`rdkit.Chem.rdRGroupDecomposition`) / SQLAlchemy 2.0 async / FastAPI / Lagom DI / dry-python returns / pytest.

**Spec:** `docs/superpowers/specs/2026-06-09-sar-workbench-rgroup-design.md` (Phase 1).

**Verified facts (from codebase exploration):**
- RDKit wrappers live in `backend/src/cellar/infrastructure/rdkit/`, are **stateless**, type mols as `Chem.Mol | None` (NOT `object`), import `from rdkit import Chem`, log defensively via `structlog`, and never re-raise RDKit errors. Exemplar: `scaffold_calculator.py`.
- `rdkit.Chem.rdRGroupDecomposition.RGroupDecompose` and `RGroupDecompositionParameters` are available in the project's RDKit build (verified). `RGroupDecompose([core], mols, asSmiles=True, asRows=True)` returns `(rows, unmatched_indices)`; `rows` is one dict per **matched** mol in input order with keys `Core`, `R1`, `R2`, …; `unmatched_indices` is a list of indices into `mols`.
- The application-layer port pattern: `application/sar_analysis/scaffold_network.py` defines a frozen dataclass + a `Protocol` (e.g. `ScaffoldNetworkBuilder`) so application never imports infra; the concrete (same name) lives in `infrastructure/rdkit/` and is registered by DI. `import-linter` (`uv run lint-imports`) enforces this.
- Compute use cases (`BuildScaffoldNetwork`) return **plain frozen dataclasses**, not `returns.Result`. Read/validate use cases use `Result`/`Success`/`Failure`. This plan's decompose use case is compute → returns a plain VO.
- Molecule fetch: `SQLAlchemyMoleculeRepository.fetch_for_scaffold_tree(*, molecule_ids, workspace_id) -> list[tuple[UUID, str, str|None]]` (id, smiles, bemis_murcko_smiles), workspace-scoped, drops null-smiles. The `MoleculeFetcherForScaffoldTree` Protocol is defined in `application/sar_analysis/build_scaffold_network.py`. **Reuse both.**
- DI: `infrastructure/di/_sar_analysis.py::register_sar_analysis`. Pure wrappers → `Singleton(...)`; DB-touching use cases → per-resolve factory that mints a fresh `AsyncUnitOfWork(c[async_sessionmaker])` shared by the use case and its repos.
- Dep aliases: `interface/dependencies/_sar_analysis.py`, built from `_get_use_case(...)`. Auth via `AuthDep` (`auth.workspace_id`, `auth.user_id`).
- Routes register in `backend/src/cellar/interface/app.py` (~lines 286-288, alongside `scaffold_tree_router`) **and** in the API test app `backend/tests/api/conftest.py::_create_test_app`. The route input-validation + collection-expansion + serialization pattern is in `interface/routes/scaffold_tree.py`.
- Tests: unit (no Docker) `cd backend && uv run pytest tests/unit/...`; api (Docker) `cd backend && uv run pytest tests/api/...`. `asyncio_mode=auto`. API `client` fixture injects admin `FakeAuth` whose `workspace_id` comes from the `workspace_id` fixture. Architecture lint: `uv run lint-imports`.

---

## Task 1: Domain result value objects

**Files:**
- Create: `backend/src/cellar/domain/sar_analysis/rgroup_types.py`
- Test: `backend/tests/unit/domain/sar_analysis/test_rgroup_types.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/domain/sar_analysis/test_rgroup_types.py`:

```python
from __future__ import annotations

import uuid

import pytest

from cellar.domain.sar_analysis.rgroup_types import (
    RGroupAssignment,
    RGroupDecompositionResult,
)


def test_assignment_holds_molecule_and_rgroups():
    mid = uuid.uuid4()
    a = RGroupAssignment(molecule_id=mid, rgroups={"R1": "F[*:1]"})
    assert a.molecule_id == mid
    assert a.rgroups["R1"] == "F[*:1]"


def test_result_defaults_are_empty():
    r = RGroupDecompositionResult(core_smiles="c1ccccc1")
    assert r.core_smiles == "c1ccccc1"
    assert r.rgroup_labels == []
    assert r.assignments == []
    assert r.unmatched_ids == []


def test_result_is_frozen():
    r = RGroupDecompositionResult(core_smiles="c1ccccc1")
    with pytest.raises(Exception):
        r.core_smiles = "c1ccncc1"  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/domain/sar_analysis/test_rgroup_types.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cellar.domain.sar_analysis.rgroup_types'`.

- [ ] **Step 3: Create the value objects**

Create `backend/src/cellar/domain/sar_analysis/rgroup_types.py`:

```python
"""Pure-data result types for R-group decomposition.

Serializable to JSON. No behavior — compute lives in
``infrastructure.rdkit.rgroup_decomposer`` and the use case in
``application.sar_analysis.decompose_rgroups``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class RGroupAssignment:
    """One molecule's R-group substituents, as SMILES keyed by label (R1, R2…)."""

    molecule_id: UUID
    rgroups: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RGroupDecompositionResult:
    """Decomposition of a set of molecules against a single core.

    ``rgroup_labels`` are the discovered positions (e.g. ["R1", "R2"]) in
    ascending order. ``unmatched_ids`` are molecules that did not contain the
    core (or could not be parsed) — surfaced, never silently dropped.
    """

    core_smiles: str
    rgroup_labels: list[str] = field(default_factory=list)
    assignments: list[RGroupAssignment] = field(default_factory=list)
    unmatched_ids: list[UUID] = field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/domain/sar_analysis/test_rgroup_types.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/domain/sar_analysis/rgroup_types.py \
        backend/tests/unit/domain/sar_analysis/test_rgroup_types.py
git commit -m "feat(sar): R-group decomposition result value objects"
```

---

## Task 2: RDKit R-group decomposer (infrastructure)

**Files:**
- Create: `backend/src/cellar/infrastructure/rdkit/rgroup_decomposer.py`
- Test: `backend/tests/unit/infrastructure/rdkit/test_rgroup_decomposer.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/infrastructure/rdkit/test_rgroup_decomposer.py`:

```python
from __future__ import annotations

import uuid

import pytest

from cellar.infrastructure.rdkit.rgroup_decomposer import RGroupDecomposer


@pytest.fixture()
def decomposer():
    return RGroupDecomposer()


def test_monosubstituted_benzenes_decompose_against_benzene(decomposer):
    f_id, cl_id, me_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    result = decomposer.decompose(
        core_smiles="c1ccccc1",
        molecules=[(f_id, "Fc1ccccc1"), (cl_id, "Clc1ccccc1"), (me_id, "Cc1ccccc1")],
    )
    assert "R1" in result.rgroup_labels
    assert len(result.assignments) == 3
    assert result.unmatched_ids == []
    by_id = {a.molecule_id: a for a in result.assignments}
    # Each molecule's R-group set carries its substituent somewhere.
    assert any("F" in v for v in by_id[f_id].rgroups.values())
    assert any("Cl" in v for v in by_id[cl_id].rgroups.values())


def test_non_matching_molecule_is_unmatched(decomposer):
    benzene_sub, pyridine = uuid.uuid4(), uuid.uuid4()
    result = decomposer.decompose(
        core_smiles="c1ccccc1",
        molecules=[(benzene_sub, "Fc1ccccc1"), (pyridine, "c1ccncc1")],
    )
    assert pyridine in result.unmatched_ids
    assert benzene_sub not in result.unmatched_ids


def test_unparseable_core_returns_all_unmatched(decomposer):
    a = uuid.uuid4()
    result = decomposer.decompose(core_smiles="not-a-smiles", molecules=[(a, "c1ccccc1")])
    assert result.unmatched_ids == [a]
    assert result.assignments == []


def test_unparseable_molecule_is_unmatched(decomposer):
    good, bad = uuid.uuid4(), uuid.uuid4()
    result = decomposer.decompose(
        core_smiles="c1ccccc1",
        molecules=[(good, "Fc1ccccc1"), (bad, "Q!Q!Q")],
    )
    assert bad in result.unmatched_ids
    assert good not in result.unmatched_ids


def test_empty_molecules_returns_empty(decomposer):
    result = decomposer.decompose(core_smiles="c1ccccc1", molecules=[])
    assert result.assignments == []
    assert result.unmatched_ids == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/infrastructure/rdkit/test_rgroup_decomposer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cellar.infrastructure.rdkit.rgroup_decomposer'`.

- [ ] **Step 3: Implement the decomposer**

Create `backend/src/cellar/infrastructure/rdkit/rgroup_decomposer.py`:

```python
"""R-group decomposition. Stateless; wraps RDKit's rdRGroupDecomposition."""

from __future__ import annotations

from uuid import UUID

import structlog
from rdkit import Chem
from rdkit.Chem import rdRGroupDecomposition

from cellar.domain.sar_analysis.rgroup_types import (
    RGroupAssignment,
    RGroupDecompositionResult,
)

logger = structlog.get_logger(__name__)


class RGroupDecomposer:
    """Decompose a congeneric series against a core into R-group columns.

    Wraps ``rdkit.Chem.rdRGroupDecomposition.RGroupDecompose``. Stateless —
    safe to register as a DI Singleton. A bare Murcko ring scaffold (no
    explicit attachment points) is an acceptable core; RDKit assigns R-groups
    at the substituted ring positions. Molecules that do not contain the core,
    and unparseable SMILES, are returned as ``unmatched_ids`` — never dropped.
    """

    def decompose(
        self, *, core_smiles: str, molecules: list[tuple[UUID, str]]
    ) -> RGroupDecompositionResult:
        core = Chem.MolFromSmiles(core_smiles)
        if core is None:
            logger.warning("rgroup_core_unparseable", core=core_smiles)
            return RGroupDecompositionResult(
                core_smiles=core_smiles,
                unmatched_ids=[mid for mid, _ in molecules],
            )

        mol_ids: list[UUID] = []
        mols: list[Chem.Mol] = []
        bad_ids: list[UUID] = []
        for mid, smi in molecules:
            m = Chem.MolFromSmiles(smi) if smi else None
            if m is None:
                bad_ids.append(mid)
                continue
            mol_ids.append(mid)
            mols.append(m)

        if not mols:
            return RGroupDecompositionResult(core_smiles=core_smiles, unmatched_ids=bad_ids)

        try:
            rows, unmatched_idx = rdRGroupDecomposition.RGroupDecompose(
                [core], mols, asSmiles=True, asRows=True
            )
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("rgroup_decompose_failed", core=core_smiles, exc=str(exc))
            return RGroupDecompositionResult(
                core_smiles=core_smiles, unmatched_ids=[*mol_ids, *bad_ids]
            )

        unmatched_set = set(unmatched_idx)

        # Discover R-group labels across all rows (keys like "R1"; skip "Core").
        seen: set[str] = set()
        for row in rows:
            for key in row:
                if key.startswith("R") and key[1:].isdigit():
                    seen.add(key)
        labels = sorted(seen, key=lambda k: int(k[1:]))

        # rows align with matched mols in input order; unmatched indices skipped.
        assignments: list[RGroupAssignment] = []
        unmatched_ids: list[UUID] = list(bad_ids)
        row_iter = iter(rows)
        for i, mid in enumerate(mol_ids):
            if i in unmatched_set:
                unmatched_ids.append(mid)
                continue
            row = next(row_iter)
            rgroups = {k: row[k] for k in labels if k in row}
            assignments.append(RGroupAssignment(molecule_id=mid, rgroups=rgroups))

        return RGroupDecompositionResult(
            core_smiles=core_smiles,
            rgroup_labels=labels,
            assignments=assignments,
            unmatched_ids=unmatched_ids,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/infrastructure/rdkit/test_rgroup_decomposer.py -v`
Expected: PASS (5 passed). If RDKit assigns a substituent to a label other than `R1` for the symmetric-benzene case, the `"R1" in result.rgroup_labels` assertion still holds (mono-substituted benzene yields exactly one R-group); the `any(... in v for v in rgroups.values())` assertions are label-agnostic by design.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/rdkit/rgroup_decomposer.py \
        backend/tests/unit/infrastructure/rdkit/test_rgroup_decomposer.py
git commit -m "feat(sar): RDKit R-group decomposer wrapper"
```

---

## Task 3: Application port + decompose use case

**Files:**
- Create: `backend/src/cellar/application/sar_analysis/rgroup_decomposition.py` (port Protocol)
- Create: `backend/src/cellar/application/sar_analysis/decompose_rgroups.py` (use case)
- Test: `backend/tests/unit/application/sar_analysis/test_decompose_rgroups.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/application/sar_analysis/test_decompose_rgroups.py`:

```python
from __future__ import annotations

import uuid

import pytest

from cellar.application.sar_analysis.decompose_rgroups import (
    DecomposeRGroups,
    DecomposeRGroupsInput,
)
from cellar.infrastructure.rdkit.rgroup_decomposer import RGroupDecomposer


class _NullUoW:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def commit(self):
        return []

    async def rollback(self):
        pass

    @property
    def is_active(self):
        return True


class _FakeFetcher:
    """Returns (id, smiles, bemis_murcko_smiles) triples like the real repo."""

    def __init__(self, rows):
        self._rows = rows

    async def fetch_for_scaffold_tree(self, *, molecule_ids, workspace_id):
        wanted = set(molecule_ids)
        return [r for r in self._rows if r[0] in wanted]


@pytest.mark.asyncio
async def test_decompose_uses_fetched_smiles():
    f_id, cl_id = uuid.uuid4(), uuid.uuid4()
    uc = DecomposeRGroups(
        molecule_fetcher=_FakeFetcher(
            [
                (f_id, "Fc1ccccc1", "c1ccccc1"),
                (cl_id, "Clc1ccccc1", "c1ccccc1"),
            ]
        ),
        decomposer=RGroupDecomposer(),
        uow=_NullUoW(),
    )
    result = await uc.execute(
        DecomposeRGroupsInput(
            molecule_ids=[f_id, cl_id],
            workspace_id=uuid.uuid4(),
            core_smiles="c1ccccc1",
        )
    )
    assert "R1" in result.rgroup_labels
    assert {a.molecule_id for a in result.assignments} == {f_id, cl_id}


@pytest.mark.asyncio
async def test_empty_set_returns_empty_result():
    uc = DecomposeRGroups(
        molecule_fetcher=_FakeFetcher([]),
        decomposer=RGroupDecomposer(),
        uow=_NullUoW(),
    )
    result = await uc.execute(
        DecomposeRGroupsInput(
            molecule_ids=[], workspace_id=uuid.uuid4(), core_smiles="c1ccccc1"
        )
    )
    assert result.assignments == []
    assert result.unmatched_ids == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis/test_decompose_rgroups.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cellar.application.sar_analysis.decompose_rgroups'`.

- [ ] **Step 3: Create the application port**

Create `backend/src/cellar/application/sar_analysis/rgroup_decomposition.py`:

```python
"""Application-layer port for R-group decomposition.

The concrete impl lives in
``cellar.infrastructure.rdkit.rgroup_decomposer.RGroupDecomposer`` and is wired
via DI. The application layer depends only on this Protocol + the domain result
VO so the layer-dependency rule (application MUST NOT import infrastructure) is
preserved.
"""

from __future__ import annotations

from typing import Any, Protocol

from cellar.domain.sar_analysis.rgroup_types import RGroupDecompositionResult


class RGroupDecomposer(Protocol):
    """Decomposes ``(id, smiles)`` molecules against a core SMILES.

    The element type of ``molecules`` is left loose (``Any`` id) so the
    application layer doesn't pin an rdkit/UUID dependency at the boundary.
    """

    def decompose(
        self, *, core_smiles: str, molecules: list[tuple[Any, str]]
    ) -> RGroupDecompositionResult: ...
```

- [ ] **Step 4: Create the use case**

Create `backend/src/cellar/application/sar_analysis/decompose_rgroups.py`:

```python
"""Decompose a set of molecules against a core into R-group columns."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from cellar.application.sar_analysis.build_scaffold_network import (
    MoleculeFetcherForScaffoldTree,
)
from cellar.application.sar_analysis.rgroup_decomposition import RGroupDecomposer
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.rgroup_types import RGroupDecompositionResult


@dataclass(frozen=True)
class DecomposeRGroupsInput:
    molecule_ids: list[UUID]
    workspace_id: UUID
    core_smiles: str


class DecomposeRGroups:
    """Fetch the set's (id, smiles), then decompose against the given core."""

    def __init__(
        self,
        *,
        molecule_fetcher: MoleculeFetcherForScaffoldTree,
        decomposer: RGroupDecomposer,
        uow: UnitOfWork,
    ) -> None:
        self._fetcher = molecule_fetcher
        self._decomposer = decomposer
        self._uow = uow

    async def execute(
        self, payload: DecomposeRGroupsInput
    ) -> RGroupDecompositionResult:
        async with self._uow:
            rows = await self._fetcher.fetch_for_scaffold_tree(
                molecule_ids=payload.molecule_ids, workspace_id=payload.workspace_id
            )
        molecules = [(mid, smiles) for (mid, smiles, _bms) in rows if smiles]
        return self._decomposer.decompose(
            core_smiles=payload.core_smiles, molecules=molecules
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis/test_decompose_rgroups.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Verify architecture boundaries**

Run: `cd backend && uv run lint-imports`
Expected: PASS — the use case imports only application + domain; the port is a Protocol; no application→infrastructure import. (The unit test importing the infra `RGroupDecomposer` directly is allowed — tests are outside the linted `src` contract.)

- [ ] **Step 7: Commit**

```bash
git add backend/src/cellar/application/sar_analysis/rgroup_decomposition.py \
        backend/src/cellar/application/sar_analysis/decompose_rgroups.py \
        backend/tests/unit/application/sar_analysis/test_decompose_rgroups.py
git commit -m "feat(sar): decompose-rgroups use case + application port"
```

---

## Task 4: API endpoint + DI wiring + registration

**Files:**
- Create: `backend/src/cellar/interface/routes/sar_analysis.py`
- Modify: `backend/src/cellar/infrastructure/di/_sar_analysis.py` (register decomposer + use case)
- Modify: `backend/src/cellar/interface/dependencies/_sar_analysis.py` (add `DecomposeRGroupsDep`)
- Modify: `backend/src/cellar/interface/app.py` (include the router, ~line 286-288)
- Modify: `backend/tests/api/conftest.py` (include the router in `_create_test_app`)
- Test: `backend/tests/api/test_sar_analysis_routes.py`

- [ ] **Step 1: Write the failing API tests**

Create `backend/tests/api/test_sar_analysis_routes.py`:

```python
"""API tests for POST /api/v1/sar/r-group-decomposition."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_rejects_both_inputs(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/sar/r-group-decomposition",
        json={
            "molecule_ids": [],
            "collection_id": str(uuid.uuid4()),
            "core_smiles": "c1ccccc1",
        },
    )
    assert res.status_code == 400
    assert "exactly one" in res.json()["detail"]


@pytest.mark.asyncio
async def test_rejects_neither_input(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/sar/r-group-decomposition",
        json={"core_smiles": "c1ccccc1"},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_rejects_empty_core(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/sar/r-group-decomposition",
        json={"molecule_ids": [], "core_smiles": "   "},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_empty_molecule_ids_returns_empty_result(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/sar/r-group-decomposition",
        json={"molecule_ids": [], "core_smiles": "c1ccccc1"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["core_smiles"] == "c1ccccc1"
    assert body["assignments"] == []
    assert body["unmatched_ids"] == []
    assert body["rgroup_labels"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/api/test_sar_analysis_routes.py -v`
Expected: FAIL — the 200 case returns 404 (route not registered); the 400 cases also 404. (Requires Docker for the API test DB.)

- [ ] **Step 3: Create the route**

Create `backend/src/cellar/interface/routes/sar_analysis.py`:

```python
"""SAR analysis HTTP routes — R-group decomposition (Phase 1)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from cellar.application.research_organization.collection_membership import (
    ListCollectionMoleculesQuery,
)
from cellar.application.sar_analysis.decompose_rgroups import DecomposeRGroupsInput
from cellar.domain.sar_analysis.rgroup_types import RGroupDecompositionResult
from cellar.interface.dependencies import AuthDep
from cellar.interface.dependencies._research_organization import (
    ListCollectionMoleculesDep,
)
from cellar.interface.dependencies._sar_analysis import DecomposeRGroupsDep
from cellar.interface.error_handlers import result_to_response
from cellar.interface.pagination import COLLECTION_EXPANSION_LIMIT

router = APIRouter(prefix="/api/v1/sar", tags=["sar-analysis"])


class RGroupDecompositionRequest(BaseModel):
    molecule_ids: list[UUID] | None = None
    collection_id: UUID | None = None
    core_smiles: str


class RGroupAssignmentView(BaseModel):
    molecule_id: UUID
    rgroups: dict[str, str]


class RGroupDecompositionResponse(BaseModel):
    core_smiles: str
    rgroup_labels: list[str]
    assignments: list[RGroupAssignmentView]
    unmatched_ids: list[UUID]


def _serialize(result: RGroupDecompositionResult) -> RGroupDecompositionResponse:
    return RGroupDecompositionResponse(
        core_smiles=result.core_smiles,
        rgroup_labels=result.rgroup_labels,
        assignments=[
            RGroupAssignmentView(molecule_id=a.molecule_id, rgroups=a.rgroups)
            for a in result.assignments
        ],
        unmatched_ids=result.unmatched_ids,
    )


@router.post("/r-group-decomposition", status_code=status.HTTP_200_OK)
async def decompose_rgroups(
    payload: RGroupDecompositionRequest,
    auth: AuthDep,
    uc: DecomposeRGroupsDep,
    list_collection_members: ListCollectionMoleculesDep,
) -> RGroupDecompositionResponse:
    if (payload.molecule_ids is None) == (payload.collection_id is None):
        raise HTTPException(
            status_code=400,
            detail="exactly one of molecule_ids or collection_id must be set",
        )
    if not payload.core_smiles.strip():
        raise HTTPException(status_code=400, detail="core_smiles must not be empty")

    if payload.collection_id is not None:
        molecule_ids = result_to_response(
            await list_collection_members(
                ListCollectionMoleculesQuery(
                    workspace_id=auth.workspace_id,
                    collection_id=payload.collection_id,
                    offset=0,
                    limit=COLLECTION_EXPANSION_LIMIT,
                ),
                auth=auth,
            )
        )
    else:
        molecule_ids = list(payload.molecule_ids or [])

    result = await uc.execute(
        DecomposeRGroupsInput(
            molecule_ids=molecule_ids,
            workspace_id=auth.workspace_id,
            core_smiles=payload.core_smiles,
        )
    )
    return _serialize(result)
```

- [ ] **Step 4: Register the decomposer + use case in DI**

In `backend/src/cellar/infrastructure/di/_sar_analysis.py`, add these imports alongside the existing ones:

```python
from cellar.application.sar_analysis.decompose_rgroups import DecomposeRGroups
from cellar.infrastructure.rdkit.rgroup_decomposer import RGroupDecomposer
```

Then, inside `register_sar_analysis(container)`, add (next to the `ScaffoldNetworkBuilder` Singleton and the `_build_scaffold_network` factory):

```python
    # --- Pure RDKit wrapper, no deps → Singleton ---
    container.define(RGroupDecomposer, Singleton(RGroupDecomposer))

    # --- Use case: fresh UoW per resolve, shared by the use case and its repo ---
    def _decompose_rgroups(c: Container) -> DecomposeRGroups:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DecomposeRGroups(
            molecule_fetcher=SQLAlchemyMoleculeRepository(uow),
            decomposer=c[RGroupDecomposer],
            uow=uow,
        )

    container.define(DecomposeRGroups, _decompose_rgroups)
```

(`Container`, `Singleton`, `async_sessionmaker`, `AsyncUnitOfWork`, and `SQLAlchemyMoleculeRepository` are already imported in this file for the scaffold wiring.)

- [ ] **Step 5: Add the dependency alias**

In `backend/src/cellar/interface/dependencies/_sar_analysis.py`, add the import and alias next to the scaffold ones:

```python
from cellar.application.sar_analysis.decompose_rgroups import DecomposeRGroups
# ...
DecomposeRGroupsDep = Annotated[
    DecomposeRGroups, Depends(_get_use_case(DecomposeRGroups))
]
```

- [ ] **Step 6: Register the router in the app and the test app**

In `backend/src/cellar/interface/app.py`, next to the scaffold-tree registration (~line 286-288):

```python
    from cellar.interface.routes.sar_analysis import router as sar_analysis_router

    app.include_router(sar_analysis_router)
```

In `backend/tests/api/conftest.py`, inside `_create_test_app`, next to `app.include_router(scaffold_tree_router)`:

```python
    from cellar.interface.routes.sar_analysis import router as sar_analysis_router

    app.include_router(sar_analysis_router)
```

- [ ] **Step 7: Run the API tests to verify they pass**

Run: `cd backend && uv run pytest tests/api/test_sar_analysis_routes.py -v`
Expected: PASS (4 passed). Requires Docker (`make up` not needed; testcontainers starts its own Postgres+RDKit).

- [ ] **Step 8: Verify architecture lint still passes**

Run: `cd backend && uv run lint-imports`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/src/cellar/interface/routes/sar_analysis.py \
        backend/src/cellar/infrastructure/di/_sar_analysis.py \
        backend/src/cellar/interface/dependencies/_sar_analysis.py \
        backend/src/cellar/interface/app.py \
        backend/tests/api/conftest.py \
        backend/tests/api/test_sar_analysis_routes.py
git commit -m "feat(sar): R-group decomposition API endpoint + DI wiring"
```

---

## Backend Done — verification

- [ ] `cd backend && uv run pytest tests/unit/domain/sar_analysis/test_rgroup_types.py tests/unit/infrastructure/rdkit/test_rgroup_decomposer.py tests/unit/application/sar_analysis/test_decompose_rgroups.py -v` — green (no Docker).
- [ ] `cd backend && uv run pytest tests/api/test_sar_analysis_routes.py -v` — green (Docker).
- [ ] `cd backend && uv run lint-imports` — green.
- [ ] `cd backend && uv run ruff check src/ && uv run ruff format --check src/` — green.
- [ ] Manually sanity-check the endpoint shape (optional, with the dev server up on :8000): a POST with a small `molecule_ids` list of a known benzene series + `"core_smiles": "c1ccccc1"` returns `assignments` with `R*` keys.
- [ ] Update the GitHub project board (SAR workbench — backend R-group decomposition done): https://github.com/users/sidxz/projects/4/views/1
- [ ] **Next plan:** the frontend SAR view-mode (core picker + table + heatmap + activity reuse) consumes this endpoint. Regenerate orval types (`cd frontend && pnpm generate:api` with the backend up) as the first step of that plan so the FE picks up `RGroupDecompositionResponse`.
