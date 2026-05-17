# Scaffold Tree V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the V2 scaffold-tree view mode on `/collections/{id}` — Bemis-Murcko at registration + on-demand `rdScaffoldNetwork` (sync ≤500 mols, async via Temporal otherwise) + a split-pane `ScaffoldTreeView` (tree left, existing `CardGrid` right).

**Architecture:** New `sar_analysis` bounded context (first member). Per-mol `bemis_murcko_smiles` column written at registration (mirrors fingerprint pattern). `scaffold_tree_jobs` table doubles as Postgres-backed cache via `ids_hash` + `result_json` JSONB. Async pipeline mirrors the export-job pipeline shipped on 2026-05-16.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy async / RDKit `rdScaffoldNetwork` / Temporal / Lagom DI / Next.js 16 / React Query / TanStack Virtual / shadcn `Resizable` (via `react-resizable-panels`).

**Parent spec:** `docs/superpowers/specs/2026-05-17-scaffold-tree-v2-design.md`.

---

## Task ordering at a glance

| # | Task | Layer |
|---|---|---|
| 1 | Migration 037 — `bemis_murcko_smiles` column | BE-data |
| 2 | `Molecule.bemis_murcko_smiles` field | BE-data |
| 3 | `MoleculeModel` column + repo round-trip | BE-data |
| 4 | `MurckoScaffoldCalculator` infra | BE-data |
| 5 | `StructureProcessor` + `ProcessedStructureDTO` extension | BE-data |
| 6 | Wire scaffold into `RegisterMolecule` + DI | BE-data |
| 7 | `backfill_bemis_murcko.py` one-shot script | BE-data |
| 8 | Migration 038 — `scaffold_tree_jobs` table | BE-async |
| 9 | `ScaffoldTreeResult` + `ScaffoldTreeNode` + `ScaffoldTreeEdge` dataclasses | BE-compute |
| 10 | `ScaffoldTreeJob` aggregate + state machine | BE-async |
| 11 | `ScaffoldTreeJobRepository` (CRUD + cache lookup) | BE-async |
| 12 | `ScaffoldNetworkBuilder` infra (rdScaffoldNetwork wrapper) | BE-compute |
| 13 | `BuildScaffoldNetwork` use case (cache-aware) | BE-compute |
| 14 | `StartScaffoldTreeJob` (sync/async dispatch) | BE-async |
| 15 | `ScaffoldTreeWorkflow` + activity + orchestrator | BE-async |
| 16 | `GetScaffoldTreeJob` + `CancelScaffoldTreeJob` | BE-async |
| 17 | DI wiring (`_sar_analysis.py` + container) | BE-async |
| 18 | API routes (`scaffold_tree.py` + register) | BE-API |
| 19 | Regenerate orval FE client | FE-types |
| 20 | Install shadcn `Resizable` primitive | FE-deps |
| 21 | FE wire types | FE-types |
| 22 | `scaffold-tree-math.ts` (subtree helpers) | FE-compute |
| 23 | `scaffold-rollup.ts` (activity rollup) | FE-compute |
| 24 | `useScaffoldTree` hook (sync + poll) | FE-data |
| 25 | `<ScaffoldColorPicker />` | FE-component |
| 26 | `<ScaffoldTreeNode />` | FE-component |
| 27 | `<ScaffoldTreeView />` (split-pane composition) | FE-component |
| 28 | Wire third view mode into `ResultsSurface` + toggle + URL | FE-wire |

Manual smoke checklist at the end of this doc covers verification after Task 28.

---

## Conventions used by every task

- **Tests-first:** every task starts with a failing test, ends with a green test, then commits. Code blocks in the steps are complete enough to paste.
- **Commit subject:** `<type>(<scope>): <summary>` — match the existing repo cadence (`feat(scaffold-tree): ...`, `fix(scaffold-tree): ...`).
- **BE test commands:**
  - Unit: `cd backend && uv run pytest tests/unit/<path> -v`
  - Integration: `cd backend && uv run pytest tests/integration/<path> -v` (requires docker compose stack up)
  - API: `cd backend && uv run pytest tests/api/<path> -v` (testcontainers-based)
- **FE test command:** `cd frontend && pnpm vitest run <path>`
- **Type check:** `cd frontend && pnpm exec tsc --noEmit`
- **Lint:** the repo runs lint via pre-commit hooks; don't `--no-verify`.
- **Workspace scoping:** every repo method that returns molecules takes a `workspace_id` filter. Mirror the existing patterns; never query molecules cross-workspace.

---

See the per-task sections below for the actual TDD steps and code.

---

## Wave 1 — BE data layer (Tasks 1–7)

### Task 1: Migration 037 — `bemis_murcko_smiles` column

**Files:**
- Create: `backend/alembic/versions/037_bemis_murcko_smiles.py`
- Test: `backend/tests/integration/persistence/test_migration_037.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/persistence/test_migration_037.py
from __future__ import annotations
import pytest
from sqlalchemy import inspect

@pytest.mark.asyncio
async def test_molecule_has_bemis_murcko_smiles_column(async_engine):
    async with async_engine.connect() as conn:
        cols = await conn.run_sync(
            lambda sync_conn: {c["name"]: c for c in inspect(sync_conn).get_columns("molecule")}
        )
    assert "bemis_murcko_smiles" in cols
    assert cols["bemis_murcko_smiles"]["nullable"] is True
    assert str(cols["bemis_murcko_smiles"]["type"]).upper().startswith("TEXT")
```

- [ ] **Step 2: Run the test — expect failure (column missing)**

```bash
cd backend && uv run pytest tests/integration/persistence/test_migration_037.py -v
```
Expected: FAIL with `assert "bemis_murcko_smiles" in cols`.

- [ ] **Step 3: Create the migration**

```python
# backend/alembic/versions/037_bemis_murcko_smiles.py
"""037 — bemis_murcko_smiles on molecule.

Per-molecule Bemis-Murcko scaffold SMILES, populated at registration.
NULL distinguishes "not yet computed" from "" (acyclic — RDKit convention).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "037_bemis_murcko_smiles"
down_revision: str | None = "036_export_jobs"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.add_column(
        "molecule",
        sa.Column("bemis_murcko_smiles", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("molecule", "bemis_murcko_smiles")
```

- [ ] **Step 4: Apply the migration + re-run the test — expect pass**

```bash
cd backend && uv run alembic upgrade head
cd backend && uv run pytest tests/integration/persistence/test_migration_037.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/037_bemis_murcko_smiles.py \
        backend/tests/integration/persistence/test_migration_037.py
git commit -m "feat(scaffold-tree): migration 037 — bemis_murcko_smiles on molecule"
```

---

### Task 2: `Molecule.bemis_murcko_smiles` field on the domain aggregate

**Files:**
- Modify: `backend/src/cellar/domain/chemical_registration/molecule.py` (add field)
- Test: `backend/tests/unit/domain/chemical_registration/test_molecule_scaffold_field.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/domain/chemical_registration/test_molecule_scaffold_field.py
from __future__ import annotations
from cellar.domain.chemical_registration.molecule import Molecule


def test_molecule_default_bemis_murcko_is_none(make_minimal_molecule):
    mol = make_minimal_molecule()
    assert mol.bemis_murcko_smiles is None


def test_molecule_accepts_scaffold_smiles(make_minimal_molecule):
    mol = make_minimal_molecule(bemis_murcko_smiles="c1ccccc1")
    assert mol.bemis_murcko_smiles == "c1ccccc1"


def test_molecule_accepts_empty_string_for_acyclic(make_minimal_molecule):
    mol = make_minimal_molecule(bemis_murcko_smiles="")
    assert mol.bemis_murcko_smiles == ""
```

`make_minimal_molecule` is the existing conftest fixture that builds the smallest valid `Molecule`. If it doesn't already accept `**kwargs` pass-through, modify it to do so in the same test file's conftest. Pattern reference: existing `make_minimal_molecule` in `backend/tests/unit/domain/chemical_registration/conftest.py`.

- [ ] **Step 2: Run the test — expect failure**

```bash
cd backend && uv run pytest tests/unit/domain/chemical_registration/test_molecule_scaffold_field.py -v
```
Expected: FAIL with `AttributeError: 'Molecule' object has no attribute 'bemis_murcko_smiles'`.

- [ ] **Step 3: Add the field to the dataclass**

In `backend/src/cellar/domain/chemical_registration/molecule.py`, find the section of the `Molecule` dataclass where structural descriptors live (next to `morgan_fp`) and add:

```python
    bemis_murcko_smiles: str | None = None
```

- [ ] **Step 4: Re-run — expect pass**

```bash
cd backend && uv run pytest tests/unit/domain/chemical_registration/test_molecule_scaffold_field.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/domain/chemical_registration/molecule.py \
        backend/tests/unit/domain/chemical_registration/test_molecule_scaffold_field.py
git commit -m "feat(scaffold-tree): Molecule.bemis_murcko_smiles field"
```

---

### Task 3: `MoleculeModel` column + repo round-trip

**Files:**
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/models.py` (add column)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_repository.py` (round-trip in `to_domain` + persistence)
- Test: `backend/tests/integration/persistence/test_molecule_repo_scaffold_field.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/persistence/test_molecule_repo_scaffold_field.py
from __future__ import annotations
import pytest


@pytest.mark.asyncio
async def test_round_trip_bemis_murcko_smiles(make_persisted_molecule, molecule_repository):
    mol = await make_persisted_molecule(bemis_murcko_smiles="c1ccccc1")
    fetched = await molecule_repository.find_by_id(mol.id, workspace_id=mol.workspace_id)
    assert fetched.bemis_murcko_smiles == "c1ccccc1"


@pytest.mark.asyncio
async def test_round_trip_none_scaffold(make_persisted_molecule, molecule_repository):
    mol = await make_persisted_molecule(bemis_murcko_smiles=None)
    fetched = await molecule_repository.find_by_id(mol.id, workspace_id=mol.workspace_id)
    assert fetched.bemis_murcko_smiles is None


@pytest.mark.asyncio
async def test_round_trip_acyclic_empty_string(make_persisted_molecule, molecule_repository):
    mol = await make_persisted_molecule(bemis_murcko_smiles="")
    fetched = await molecule_repository.find_by_id(mol.id, workspace_id=mol.workspace_id)
    assert fetched.bemis_murcko_smiles == ""
```

- [ ] **Step 2: Run — expect failure (`bemis_murcko_smiles` not round-tripped)**

```bash
cd backend && uv run pytest tests/integration/persistence/test_molecule_repo_scaffold_field.py -v
```
Expected: FAIL with `AttributeError` on `mol.bemis_murcko_smiles` during round-trip OR persisted value is always `None`.

- [ ] **Step 3: Add column + round-trip wiring**

In `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/models.py`, add to the `MoleculeModel` class next to `fp_morgan`:

```python
    bemis_murcko_smiles: Mapped[str | None] = mapped_column(Text, nullable=True)
```

In `molecule_repository.py`, find `_to_domain` (or equivalent) and add the field to the returned `Molecule(...)` kwargs:

```python
    bemis_murcko_smiles=model.bemis_murcko_smiles,
```

Find the save/insert path (likely `_to_model` or `save`) and persist the new field:

```python
    bemis_murcko_smiles=mol.bemis_murcko_smiles,
```

- [ ] **Step 4: Re-run — expect pass**

```bash
cd backend && uv run pytest tests/integration/persistence/test_molecule_repo_scaffold_field.py -v
```
Expected: PASS (all three tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/models.py \
        backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_repository.py \
        backend/tests/integration/persistence/test_molecule_repo_scaffold_field.py
git commit -m "feat(scaffold-tree): MoleculeModel bemis_murcko_smiles + repo round-trip"
```

---

### Task 4: `MurckoScaffoldCalculator` infra wrapper

**Files:**
- Create: `backend/src/cellar/infrastructure/rdkit/scaffold_calculator.py`
- Test: `backend/tests/unit/infrastructure/rdkit/test_scaffold_calculator.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/infrastructure/rdkit/test_scaffold_calculator.py
from __future__ import annotations
import pytest
from rdkit import Chem
from cellar.infrastructure.rdkit.scaffold_calculator import MurckoScaffoldCalculator


@pytest.fixture()
def calc():
    return MurckoScaffoldCalculator()


def test_benzene_scaffold_is_benzene(calc):
    mol = Chem.MolFromSmiles("c1ccccc1")
    assert calc.compute(mol) == "c1ccccc1"


def test_ibuprofen_scaffold_is_benzene(calc):
    mol = Chem.MolFromSmiles("CC(C)Cc1ccc(cc1)C(C)C(=O)O")
    assert calc.compute(mol) == "c1ccccc1"


def test_acyclic_returns_empty_string(calc):
    mol = Chem.MolFromSmiles("CCCCC")
    assert calc.compute(mol) == ""


def test_biaryl_scaffold(calc):
    mol = Chem.MolFromSmiles("c1ccc(-c2ccccc2)cc1")
    assert calc.compute(mol) == "c1ccc(-c2ccccc2)cc1"


def test_fused_ring_naphthalene(calc):
    mol = Chem.MolFromSmiles("c1ccc2ccccc2c1")
    assert calc.compute(mol) == "c1ccc2ccccc2c1"


def test_diphenhydramine_keeps_ether_link(calc):
    # The Murcko scaffold keeps the linker; aromatic rings + ether.
    mol = Chem.MolFromSmiles("c1ccc(C(OCCN(C)C)c2ccccc2)cc1")
    scaffold = calc.compute(mol)
    assert scaffold is not None
    assert "c1ccccc1" in scaffold or scaffold.count("c1ccccc1") >= 1


def test_invalid_mol_returns_none(calc):
    # Calling compute with None should be defensive — returns None, logs.
    assert calc.compute(None) is None  # type: ignore[arg-type]
```

- [ ] **Step 2: Run — expect failure (module missing)**

```bash
cd backend && uv run pytest tests/unit/infrastructure/rdkit/test_scaffold_calculator.py -v
```
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the calculator**

```python
# backend/src/cellar/infrastructure/rdkit/scaffold_calculator.py
"""Bemis-Murcko scaffold computation. Stateless; wraps RDKit."""

from __future__ import annotations

import structlog
from rdkit import Chem
from rdkit.Chem.Scaffolds import MurckoScaffold

logger = structlog.get_logger(__name__)


class MurckoScaffoldCalculator:
    """Compute the Bemis-Murcko scaffold SMILES for an RDKit mol.

    Returns:
        - canonical SMILES of the scaffold for ringed molecules
        - "" for acyclic molecules (RDKit convention)
        - None on parse / compute failure (logs at warning level)
    """

    def compute(self, mol: Chem.Mol | None) -> str | None:
        if mol is None:
            logger.warning("scaffold_compute_called_with_none")
            return None
        try:
            return MurckoScaffold.MurckoScaffoldSmiles(mol=mol)
        except Exception as exc:  # pragma: no cover — defensive
            try:
                source = Chem.MolToSmiles(mol)
            except Exception:
                source = "<unrenderable>"
            logger.warning("scaffold_compute_failed", smiles=source, exc=str(exc))
            return None
```

- [ ] **Step 4: Re-run — expect pass**

```bash
cd backend && uv run pytest tests/unit/infrastructure/rdkit/test_scaffold_calculator.py -v
```
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/rdkit/scaffold_calculator.py \
        backend/tests/unit/infrastructure/rdkit/test_scaffold_calculator.py
git commit -m "feat(scaffold-tree): MurckoScaffoldCalculator infra wrapper"
```

---

### Task 5: `StructureProcessor` + `ProcessedStructureDTO` extension

**Files:**
- Modify: `backend/src/cellar/infrastructure/rdkit/structure_processor.py` (add scaffold step + DTO field)
- Test: `backend/tests/unit/infrastructure/rdkit/test_structure_processor_scaffold.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/infrastructure/rdkit/test_structure_processor_scaffold.py
from __future__ import annotations
import pytest
from cellar.infrastructure.rdkit.structure_processor import StructureProcessor
from cellar.infrastructure.rdkit.scaffold_calculator import MurckoScaffoldCalculator


@pytest.fixture()
def processor(default_standardizer, default_descriptor_calculator, default_fingerprint_generator):
    # Reuse the existing processor fixture pattern; pass an explicit scaffold calc.
    return StructureProcessor(
        standardizer=default_standardizer,
        descriptor_calculator=default_descriptor_calculator,
        fingerprint_generator=default_fingerprint_generator,
        scaffold_calculator=MurckoScaffoldCalculator(),
    )


def test_processed_structure_includes_scaffold(processor):
    processed = processor.process("CC(C)Cc1ccc(cc1)C(C)C(=O)O")  # ibuprofen
    assert processed.bemis_murcko_smiles == "c1ccccc1"


def test_acyclic_smiles_yields_empty_scaffold(processor):
    processed = processor.process("CCCCC")
    assert processed.bemis_murcko_smiles == ""
```

The existing fixtures `default_standardizer`, `default_descriptor_calculator`, `default_fingerprint_generator` come from `backend/tests/unit/infrastructure/rdkit/conftest.py`. If not present, mirror the existing pattern from `test_structure_processor.py`.

- [ ] **Step 2: Run — expect failure (`scaffold_calculator` kwarg unknown OR DTO missing field)**

```bash
cd backend && uv run pytest tests/unit/infrastructure/rdkit/test_structure_processor_scaffold.py -v
```
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'scaffold_calculator'` (or DTO attribute error).

- [ ] **Step 3: Extend processor + DTO**

In `backend/src/cellar/infrastructure/rdkit/structure_processor.py`:

1. Add `bemis_murcko_smiles: str | None = None` to `ProcessedStructureDTO`.
2. Add `scaffold_calculator: MurckoScaffoldCalculator` to `StructureProcessor.__init__` (keep as positional-or-keyword, default `None` for backward compatibility ONLY in this commit — the DI wiring task tightens it).
3. In `process(...)`, after the existing standardization step, compute scaffold:

```python
        scaffold = (
            self._scaffold_calculator.compute(processed_mol)
            if self._scaffold_calculator is not None
            else None
        )
        # ...
        return ProcessedStructureDTO(
            # ...existing fields...
            bemis_murcko_smiles=scaffold,
        )
```

Add the import:
```python
from cellar.infrastructure.rdkit.scaffold_calculator import MurckoScaffoldCalculator
```

- [ ] **Step 4: Re-run — expect pass**

```bash
cd backend && uv run pytest tests/unit/infrastructure/rdkit/test_structure_processor_scaffold.py -v
```
Expected: PASS.

Also re-run the full processor suite to confirm no regression:

```bash
cd backend && uv run pytest tests/unit/infrastructure/rdkit/test_structure_processor.py -v
```
Expected: still green.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/rdkit/structure_processor.py \
        backend/tests/unit/infrastructure/rdkit/test_structure_processor_scaffold.py
git commit -m "feat(scaffold-tree): StructureProcessor emits bemis_murcko_smiles"
```

---

### Task 6: Wire scaffold into `RegisterMolecule` + DI

**Files:**
- Modify: `backend/src/cellar/application/chemical_registration/register_molecule.py` (one line in `_register_disclosed`)
- Modify: `backend/src/cellar/infrastructure/di/_core.py` (or wherever `StructureProcessor` is constructed — bind `MurckoScaffoldCalculator` and pass it)
- Test: `backend/tests/integration/application/chemical_registration/test_register_molecule_scaffold.py`

- [ ] **Step 1: Write the failing integration test**

```python
# backend/tests/integration/application/chemical_registration/test_register_molecule_scaffold.py
from __future__ import annotations
import pytest


@pytest.mark.asyncio
async def test_register_molecule_persists_scaffold(register_molecule_use_case, registration_input_for):
    out = await register_molecule_use_case.execute(
        registration_input_for(smiles="CC(C)Cc1ccc(cc1)C(C)C(=O)O")  # ibuprofen
    )
    assert out.is_success()
    mol = out.unwrap().molecule
    assert mol.bemis_murcko_smiles == "c1ccccc1"


@pytest.mark.asyncio
async def test_register_acyclic_records_empty_scaffold(register_molecule_use_case, registration_input_for):
    out = await register_molecule_use_case.execute(registration_input_for(smiles="CCCCC"))
    assert out.is_success()
    assert out.unwrap().molecule.bemis_murcko_smiles == ""
```

`register_molecule_use_case` and `registration_input_for` are reused from existing integration fixtures (see `backend/tests/integration/application/chemical_registration/conftest.py`).

- [ ] **Step 2: Run — expect failure (scaffold is `None` because DI doesn't pass the calculator yet)**

```bash
cd backend && uv run pytest tests/integration/application/chemical_registration/test_register_molecule_scaffold.py -v
```
Expected: FAIL with `assert None == "c1ccccc1"`.

- [ ] **Step 3: Wire DI + RegisterMolecule**

In `backend/src/cellar/infrastructure/di/_core.py` (or whichever module constructs `StructureProcessor`):

```python
from cellar.infrastructure.rdkit.scaffold_calculator import MurckoScaffoldCalculator

# In configure(container):
container.define(MurckoScaffoldCalculator, Singleton(MurckoScaffoldCalculator))

# Wherever StructureProcessor is defined — add the new dependency:
container.define(
    StructureProcessor,
    lambda c: StructureProcessor(
        standardizer=c[Standardizer],
        descriptor_calculator=c[DescriptorCalculator],
        fingerprint_generator=c[FingerprintGenerator],
        scaffold_calculator=c[MurckoScaffoldCalculator],
    ),
)
```

In `backend/src/cellar/application/chemical_registration/register_molecule.py`, locate `_register_disclosed` near the `mol.morgan_fp = processed.fingerprints.morgan` assignment (around line 334 per the spec) and add immediately after it:

```python
        mol.bemis_murcko_smiles = processed.bemis_murcko_smiles
```

Now drop the `= None` default on `StructureProcessor.__init__`'s `scaffold_calculator` parameter — it's required from this point on.

- [ ] **Step 4: Re-run — expect pass**

```bash
cd backend && uv run pytest tests/integration/application/chemical_registration/test_register_molecule_scaffold.py -v
cd backend && uv run pytest tests/integration/application/chemical_registration/ -v   # regression sweep
```
Expected: PASS on new tests; no regressions.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/application/chemical_registration/register_molecule.py \
        backend/src/cellar/infrastructure/di/_core.py \
        backend/src/cellar/infrastructure/rdkit/structure_processor.py \
        backend/tests/integration/application/chemical_registration/test_register_molecule_scaffold.py
git commit -m "feat(scaffold-tree): RegisterMolecule writes bemis_murcko_smiles"
```

---

### Task 7: One-shot `backfill_bemis_murcko.py` script

**Files:**
- Create: `backend/scripts/backfill_bemis_murcko.py`
- Test: `backend/tests/integration/scripts/test_backfill_bemis_murcko.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/scripts/test_backfill_bemis_murcko.py
from __future__ import annotations
import pytest
from cellar.scripts.backfill_bemis_murcko import backfill_batch


@pytest.mark.asyncio
async def test_backfill_populates_null_rows(async_session, make_persisted_molecule):
    # Seed: 3 mols with NULL scaffold, 1 already populated.
    seeded = []
    for smi in ["c1ccccc1", "CC(C)Cc1ccc(cc1)C(C)C(=O)O", "CCCCC"]:
        m = await make_persisted_molecule(smiles=smi, bemis_murcko_smiles=None)
        seeded.append(m)
    pre_filled = await make_persisted_molecule(
        smiles="c1ccc2ccccc2c1", bemis_murcko_smiles="c1ccc2ccccc2c1"
    )

    stats = await backfill_batch(session=async_session, batch_size=10)
    assert stats.processed == 3
    assert stats.skipped == 0
    assert stats.failed == 0

    # Re-fetch and assert
    refreshed = {m.id: await _refetch(async_session, m.id) for m in seeded}
    assert refreshed[seeded[0].id].bemis_murcko_smiles == "c1ccccc1"
    assert refreshed[seeded[1].id].bemis_murcko_smiles == "c1ccccc1"
    assert refreshed[seeded[2].id].bemis_murcko_smiles == ""

    # Pre-filled row untouched
    untouched = await _refetch(async_session, pre_filled.id)
    assert untouched.bemis_murcko_smiles == "c1ccc2ccccc2c1"


@pytest.mark.asyncio
async def test_backfill_idempotent(async_session, make_persisted_molecule):
    await make_persisted_molecule(smiles="c1ccccc1", bemis_murcko_smiles=None)
    first = await backfill_batch(session=async_session, batch_size=10)
    second = await backfill_batch(session=async_session, batch_size=10)
    assert first.processed == 1
    assert second.processed == 0


async def _refetch(session, mol_id):
    # tiny helper — adjust to repo conventions if a helper already exists
    from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import MoleculeModel
    from sqlalchemy import select
    res = await session.execute(select(MoleculeModel).where(MoleculeModel.id == mol_id))
    return res.scalar_one()
```

- [ ] **Step 2: Run — expect failure (script doesn't exist)**

```bash
cd backend && uv run pytest tests/integration/scripts/test_backfill_bemis_murcko.py -v
```
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the script**

```python
# backend/scripts/backfill_bemis_murcko.py
"""One-shot backfill — populate Molecule.bemis_murcko_smiles for legacy rows.

Idempotent: skips rows where bemis_murcko_smiles IS NOT NULL.
Batches of 500 by default. Run via:

    cd backend && uv run python -m cellar.scripts.backfill_bemis_murcko --batch-size 500
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import logging

import structlog
from rdkit import Chem
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import MoleculeModel
from cellar.infrastructure.persistence.sqlalchemy.session import async_session_factory  # adjust
from cellar.infrastructure.rdkit.scaffold_calculator import MurckoScaffoldCalculator

logger = structlog.get_logger(__name__)


@dataclasses.dataclass
class BatchStats:
    processed: int = 0
    skipped: int = 0
    failed: int = 0


async def backfill_batch(session: AsyncSession, batch_size: int) -> BatchStats:
    calc = MurckoScaffoldCalculator()
    stats = BatchStats()

    result = await session.execute(
        select(MoleculeModel)
        .where(MoleculeModel.bemis_murcko_smiles.is_(None))
        .limit(batch_size)
    )
    rows = list(result.scalars())

    for row in rows:
        try:
            mol = Chem.MolFromSmiles(row.smiles)
            if mol is None:
                stats.failed += 1
                logger.warning("backfill_parse_failed", mol_id=str(row.id), smiles=row.smiles)
                continue
            row.bemis_murcko_smiles = calc.compute(mol) or ""
            stats.processed += 1
        except Exception as exc:
            stats.failed += 1
            logger.warning("backfill_compute_failed", mol_id=str(row.id), exc=str(exc))

    await session.commit()
    return stats


async def run_until_empty(batch_size: int) -> None:
    total = BatchStats()
    while True:
        async with async_session_factory() as session:
            stats = await backfill_batch(session, batch_size)
        total.processed += stats.processed
        total.failed += stats.failed
        if stats.processed == 0 and stats.failed == 0:
            break
        logger.info("backfill_batch_done", **dataclasses.asdict(stats))
    logger.info("backfill_complete", **dataclasses.asdict(total))


def _cli() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_until_empty(args.batch_size))


if __name__ == "__main__":
    _cli()
```

If `async_session_factory`'s import path is different in this repo, adjust to whatever the existing scripts (`rebuild_campaign_curve_snapshots.py`) use. Same for the package path of `scripts/`. If `scripts/` isn't an importable package, add an empty `__init__.py` to `backend/src/cellar/scripts/` and move the script there — the existing rebuild script will tell you the convention.

- [ ] **Step 4: Re-run — expect pass**

```bash
cd backend && uv run pytest tests/integration/scripts/test_backfill_bemis_murcko.py -v
```
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/backfill_bemis_murcko.py \
        backend/tests/integration/scripts/test_backfill_bemis_murcko.py
git commit -m "feat(scaffold-tree): one-shot backfill_bemis_murcko script"
```

---

## Wave 2 — BE compute + async scaffolding (Tasks 8–13)

### Task 8: Migration 038 — `scaffold_tree_jobs` table

**Files:**
- Create: `backend/alembic/versions/038_scaffold_tree_jobs.py`
- Test: `backend/tests/integration/persistence/test_migration_038.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/persistence/test_migration_038.py
from __future__ import annotations
import pytest
from sqlalchemy import inspect


@pytest.mark.asyncio
async def test_scaffold_tree_jobs_table_exists(async_engine):
    async with async_engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
    assert "scaffold_tree_jobs" in tables


@pytest.mark.asyncio
async def test_scaffold_tree_jobs_columns(async_engine):
    async with async_engine.connect() as conn:
        cols = await conn.run_sync(
            lambda c: {col["name"]: col for col in inspect(c).get_columns("scaffold_tree_jobs")}
        )
    expected = {
        "id", "workspace_id", "requested_by", "ids_hash", "requested_at",
        "status", "started_at", "completed_at", "error_message",
        "result_json", "version",
    }
    assert expected.issubset(set(cols))
    assert cols["result_json"]["nullable"] is True
    assert str(cols["result_json"]["type"]).upper() in {"JSONB", "JSON"}


@pytest.mark.asyncio
async def test_scaffold_tree_jobs_cache_index(async_engine):
    async with async_engine.connect() as conn:
        indexes = await conn.run_sync(
            lambda c: inspect(c).get_indexes("scaffold_tree_jobs")
        )
    names = {idx["name"] for idx in indexes}
    assert "scaffold_tree_jobs_cache" in names
```

- [ ] **Step 2: Run — expect failure**

```bash
cd backend && uv run pytest tests/integration/persistence/test_migration_038.py -v
```

- [ ] **Step 3: Write the migration**

```python
# backend/alembic/versions/038_scaffold_tree_jobs.py
"""038 — scaffold_tree_jobs table.

Persisted ScaffoldTreeJob aggregate. The result_json column doubles as the
Postgres-backed cache; the partial index on (ids_hash, completed_at) WHERE
status='ready' serves the 1-hour TTL lookup.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "038_scaffold_tree_jobs"
down_revision: str | None = "037_bemis_murcko_smiles"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "scaffold_tree_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("ids_hash", sa.Text(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("result_json", postgresql.JSONB, nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index(
        "scaffold_tree_jobs_workspace_status",
        "scaffold_tree_jobs",
        ["workspace_id", "status"],
    )
    op.create_index(
        "scaffold_tree_jobs_requested_by_at",
        "scaffold_tree_jobs",
        ["requested_by", sa.text("requested_at DESC")],
    )
    op.create_index(
        "scaffold_tree_jobs_cache",
        "scaffold_tree_jobs",
        ["ids_hash", sa.text("completed_at DESC")],
        postgresql_where=sa.text("status = 'ready'"),
    )


def downgrade() -> None:
    op.drop_index("scaffold_tree_jobs_cache", table_name="scaffold_tree_jobs")
    op.drop_index("scaffold_tree_jobs_requested_by_at", table_name="scaffold_tree_jobs")
    op.drop_index("scaffold_tree_jobs_workspace_status", table_name="scaffold_tree_jobs")
    op.drop_table("scaffold_tree_jobs")
```

- [ ] **Step 4: Apply + re-run — expect pass**

```bash
cd backend && uv run alembic upgrade head
cd backend && uv run pytest tests/integration/persistence/test_migration_038.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/038_scaffold_tree_jobs.py \
        backend/tests/integration/persistence/test_migration_038.py
git commit -m "feat(scaffold-tree): migration 038 — scaffold_tree_jobs (table + cache index)"
```

---

### Task 9: `ScaffoldTreeResult` + node/edge/stats dataclasses

**Files:**
- Create: `backend/src/cellar/domain/sar_analysis/__init__.py`
- Create: `backend/src/cellar/domain/sar_analysis/scaffold_tree_types.py`
- Test: `backend/tests/unit/domain/sar_analysis/test_scaffold_tree_types.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/domain/sar_analysis/test_scaffold_tree_types.py
from __future__ import annotations
import uuid
from cellar.domain.sar_analysis.scaffold_tree_types import (
    ScaffoldTreeNode,
    ScaffoldTreeEdge,
    ScaffoldTreeResult,
    ScaffoldTreeStats,
    NO_SCAFFOLD_SENTINEL,
)


def test_no_scaffold_sentinel_value():
    assert NO_SCAFFOLD_SENTINEL == "__no_scaffold__"


def test_node_round_trip_dict():
    mid = uuid.uuid4()
    node = ScaffoldTreeNode(
        scaffold_smiles="c1ccccc1",
        molecule_ids=[mid],
        molecule_count=1,
        subtree_molecule_count=1,
    )
    assert node.scaffold_smiles == "c1ccccc1"
    assert node.molecule_ids == [mid]


def test_result_has_nodes_edges_stats():
    result = ScaffoldTreeResult(
        nodes=[],
        edges=[],
        stats=ScaffoldTreeStats(node_count=0, elapsed_ms=10, cache_hit=False),
    )
    assert result.nodes == []
    assert result.stats.cache_hit is False


def test_edge_parent_child():
    e = ScaffoldTreeEdge(parent_smiles="c1ccccc1", child_smiles="c1ccc2ccccc2c1")
    assert e.parent_smiles == "c1ccccc1"
    assert e.child_smiles == "c1ccc2ccccc2c1"
```

- [ ] **Step 2: Run — expect failure**

```bash
cd backend && uv run pytest tests/unit/domain/sar_analysis/test_scaffold_tree_types.py -v
```

- [ ] **Step 3: Write the dataclasses**

```python
# backend/src/cellar/domain/sar_analysis/__init__.py
```
(empty file)

```python
# backend/src/cellar/domain/sar_analysis/scaffold_tree_types.py
"""Pure-data result types for the scaffold tree view.

Serializable to JSON (round-trip via dataclasses.asdict / FastAPI).
No behavior — see application.sar_analysis.build_scaffold_network for the compute side.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

NO_SCAFFOLD_SENTINEL = "__no_scaffold__"


@dataclass(frozen=True)
class ScaffoldTreeNode:
    scaffold_smiles: str  # canonical SMILES or NO_SCAFFOLD_SENTINEL
    molecule_ids: list[UUID]
    molecule_count: int
    subtree_molecule_count: int


@dataclass(frozen=True)
class ScaffoldTreeEdge:
    parent_smiles: str
    child_smiles: str


@dataclass(frozen=True)
class ScaffoldTreeStats:
    node_count: int
    elapsed_ms: int
    cache_hit: bool
    truncated: bool = False


@dataclass(frozen=True)
class ScaffoldTreeResult:
    nodes: list[ScaffoldTreeNode] = field(default_factory=list)
    edges: list[ScaffoldTreeEdge] = field(default_factory=list)
    stats: ScaffoldTreeStats = field(
        default_factory=lambda: ScaffoldTreeStats(node_count=0, elapsed_ms=0, cache_hit=False)
    )
```

Add an empty `backend/tests/unit/domain/sar_analysis/__init__.py` and `backend/tests/unit/domain/sar_analysis/conftest.py` if pytest needs it (the existing test convention will dictate; if other sibling directories don't have `__init__.py`, skip it).

- [ ] **Step 4: Re-run — expect pass**

```bash
cd backend && uv run pytest tests/unit/domain/sar_analysis/test_scaffold_tree_types.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/domain/sar_analysis/__init__.py \
        backend/src/cellar/domain/sar_analysis/scaffold_tree_types.py \
        backend/tests/unit/domain/sar_analysis/test_scaffold_tree_types.py
git commit -m "feat(scaffold-tree): domain types — ScaffoldTreeNode/Edge/Result/Stats"
```

---

### Task 10: `ScaffoldTreeJob` aggregate + state machine

**Files:**
- Create: `backend/src/cellar/domain/sar_analysis/scaffold_tree_job.py`
- Test: `backend/tests/unit/domain/sar_analysis/test_scaffold_tree_job.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/domain/sar_analysis/test_scaffold_tree_job.py
from __future__ import annotations
import uuid
from datetime import datetime, timezone

import pytest

from cellar.domain.sar_analysis.scaffold_tree_job import (
    ScaffoldTreeJob,
    ScaffoldTreeJobStatus,
    InvalidScaffoldTreeJobTransition,
)
from cellar.domain.sar_analysis.scaffold_tree_types import (
    ScaffoldTreeResult,
    ScaffoldTreeStats,
)


def _new_job() -> ScaffoldTreeJob:
    return ScaffoldTreeJob.create(
        workspace_id=uuid.uuid4(),
        requested_by=uuid.uuid4(),
        ids_hash="abc",
        now=datetime(2026, 5, 17, tzinfo=timezone.utc),
    )


def test_create_starts_in_pending_status():
    job = _new_job()
    assert job.status == ScaffoldTreeJobStatus.PENDING
    assert job.started_at is None
    assert job.result is None


def test_pending_to_running():
    job = _new_job()
    now = datetime(2026, 5, 17, 0, 1, tzinfo=timezone.utc)
    running = job.mark_running(now)
    assert running.status == ScaffoldTreeJobStatus.RUNNING
    assert running.started_at == now


def test_running_to_ready():
    job = _new_job().mark_running(datetime(2026, 5, 17, 0, 1, tzinfo=timezone.utc))
    result = ScaffoldTreeResult(
        nodes=[], edges=[],
        stats=ScaffoldTreeStats(node_count=0, elapsed_ms=10, cache_hit=False),
    )
    ready = job.mark_ready(result, datetime(2026, 5, 17, 0, 2, tzinfo=timezone.utc))
    assert ready.status == ScaffoldTreeJobStatus.READY
    assert ready.result is result
    assert ready.completed_at is not None


def test_cannot_mark_ready_from_pending():
    job = _new_job()
    with pytest.raises(InvalidScaffoldTreeJobTransition):
        job.mark_ready(
            ScaffoldTreeResult(),
            datetime(2026, 5, 17, 0, 1, tzinfo=timezone.utc),
        )


def test_running_to_failed():
    job = _new_job().mark_running(datetime(2026, 5, 17, 0, 1, tzinfo=timezone.utc))
    failed = job.mark_failed("boom", datetime(2026, 5, 17, 0, 2, tzinfo=timezone.utc))
    assert failed.status == ScaffoldTreeJobStatus.FAILED
    assert failed.error_message == "boom"


def test_pending_or_running_to_cancelled():
    pending = _new_job()
    c1 = pending.mark_cancelled(datetime(2026, 5, 17, 0, 1, tzinfo=timezone.utc))
    assert c1.status == ScaffoldTreeJobStatus.CANCELLED

    running = _new_job().mark_running(datetime(2026, 5, 17, 0, 1, tzinfo=timezone.utc))
    c2 = running.mark_cancelled(datetime(2026, 5, 17, 0, 2, tzinfo=timezone.utc))
    assert c2.status == ScaffoldTreeJobStatus.CANCELLED


def test_ready_is_terminal():
    job = (
        _new_job()
        .mark_running(datetime(2026, 5, 17, 0, 1, tzinfo=timezone.utc))
        .mark_ready(
            ScaffoldTreeResult(),
            datetime(2026, 5, 17, 0, 2, tzinfo=timezone.utc),
        )
    )
    with pytest.raises(InvalidScaffoldTreeJobTransition):
        job.mark_failed("oops", datetime(2026, 5, 17, 0, 3, tzinfo=timezone.utc))
```

- [ ] **Step 2: Run — expect failure**

```bash
cd backend && uv run pytest tests/unit/domain/sar_analysis/test_scaffold_tree_job.py -v
```

- [ ] **Step 3: Write the aggregate**

```python
# backend/src/cellar/domain/sar_analysis/scaffold_tree_job.py
"""ScaffoldTreeJob — persisted unit of async scaffold-network compute.

State machine:  pending -> running -> {ready | failed | cancelled}
                pending             ->  cancelled
                running             ->  cancelled

`ready` / `failed` / `cancelled` are terminal.
"""

from __future__ import annotations

import dataclasses
import enum
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import UUID

from cellar.domain.sar_analysis.scaffold_tree_types import ScaffoldTreeResult


class ScaffoldTreeJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InvalidScaffoldTreeJobTransition(Exception):
    pass


_TERMINAL = {ScaffoldTreeJobStatus.READY, ScaffoldTreeJobStatus.FAILED, ScaffoldTreeJobStatus.CANCELLED}


@dataclass(frozen=True)
class ScaffoldTreeJob:
    id: UUID
    workspace_id: UUID
    requested_by: UUID
    ids_hash: str
    requested_at: datetime
    status: ScaffoldTreeJobStatus = ScaffoldTreeJobStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    result: ScaffoldTreeResult | None = None
    version: int = 1

    @classmethod
    def create(
        cls, *, workspace_id: UUID, requested_by: UUID, ids_hash: str, now: datetime
    ) -> "ScaffoldTreeJob":
        return cls(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            requested_by=requested_by,
            ids_hash=ids_hash,
            requested_at=now,
        )

    def mark_running(self, now: datetime) -> "ScaffoldTreeJob":
        if self.status != ScaffoldTreeJobStatus.PENDING:
            raise InvalidScaffoldTreeJobTransition(
                f"Cannot mark RUNNING from {self.status}"
            )
        return replace(self, status=ScaffoldTreeJobStatus.RUNNING, started_at=now)

    def mark_ready(self, result: ScaffoldTreeResult, now: datetime) -> "ScaffoldTreeJob":
        if self.status != ScaffoldTreeJobStatus.RUNNING:
            raise InvalidScaffoldTreeJobTransition(
                f"Cannot mark READY from {self.status}"
            )
        return replace(
            self,
            status=ScaffoldTreeJobStatus.READY,
            completed_at=now,
            result=result,
        )

    def mark_failed(self, error: str, now: datetime) -> "ScaffoldTreeJob":
        if self.status not in {ScaffoldTreeJobStatus.PENDING, ScaffoldTreeJobStatus.RUNNING}:
            raise InvalidScaffoldTreeJobTransition(
                f"Cannot mark FAILED from {self.status}"
            )
        return replace(
            self,
            status=ScaffoldTreeJobStatus.FAILED,
            completed_at=now,
            error_message=error,
        )

    def mark_cancelled(self, now: datetime) -> "ScaffoldTreeJob":
        if self.status in _TERMINAL:
            raise InvalidScaffoldTreeJobTransition(
                f"Cannot CANCEL terminal {self.status}"
            )
        return replace(self, status=ScaffoldTreeJobStatus.CANCELLED, completed_at=now)
```

- [ ] **Step 4: Re-run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/domain/sar_analysis/scaffold_tree_job.py \
        backend/tests/unit/domain/sar_analysis/test_scaffold_tree_job.py
git commit -m "feat(scaffold-tree): ScaffoldTreeJob aggregate + state machine"
```

---

### Task 11: `ScaffoldTreeJobRepository` (CRUD + cache lookup)

**Files:**
- Create: `backend/src/cellar/application/sar_analysis/__init__.py`
- Create: `backend/src/cellar/application/sar_analysis/repositories.py` (Protocol)
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/__init__.py`
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/models.py`
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/scaffold_tree_job_repository.py`
- Test: `backend/tests/integration/persistence/sar_analysis/test_scaffold_tree_job_repository.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/integration/persistence/sar_analysis/test_scaffold_tree_job_repository.py
from __future__ import annotations
import uuid
from datetime import datetime, timezone, timedelta

import pytest

from cellar.domain.sar_analysis.scaffold_tree_job import (
    ScaffoldTreeJob,
    ScaffoldTreeJobStatus,
)
from cellar.domain.sar_analysis.scaffold_tree_types import (
    ScaffoldTreeResult,
    ScaffoldTreeStats,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.scaffold_tree_job_repository import (
    SQLAlchemyScaffoldTreeJobRepository,
)


@pytest.fixture()
def repo(async_session):
    return SQLAlchemyScaffoldTreeJobRepository(session=async_session)


@pytest.mark.asyncio
async def test_save_and_find_by_id(repo):
    workspace_id = uuid.uuid4()
    job = ScaffoldTreeJob.create(
        workspace_id=workspace_id,
        requested_by=uuid.uuid4(),
        ids_hash="hash-1",
        now=datetime.now(timezone.utc),
    )
    await repo.save(job)
    fetched = await repo.find_by_id(job.id, workspace_id=workspace_id)
    assert fetched is not None
    assert fetched.id == job.id
    assert fetched.status == ScaffoldTreeJobStatus.PENDING


@pytest.mark.asyncio
async def test_save_updates_status_and_result(repo):
    workspace_id = uuid.uuid4()
    job = ScaffoldTreeJob.create(
        workspace_id=workspace_id,
        requested_by=uuid.uuid4(),
        ids_hash="hash-2",
        now=datetime.now(timezone.utc),
    )
    await repo.save(job)

    running = job.mark_running(datetime.now(timezone.utc))
    await repo.save(running)

    result = ScaffoldTreeResult(
        nodes=[], edges=[],
        stats=ScaffoldTreeStats(node_count=0, elapsed_ms=42, cache_hit=False),
    )
    ready = running.mark_ready(result, datetime.now(timezone.utc))
    await repo.save(ready)

    fetched = await repo.find_by_id(job.id, workspace_id=workspace_id)
    assert fetched.status == ScaffoldTreeJobStatus.READY
    assert fetched.result is not None
    assert fetched.result.stats.elapsed_ms == 42


@pytest.mark.asyncio
async def test_find_cached_within_ttl_returns_result(repo):
    workspace_id = uuid.uuid4()
    job = (
        ScaffoldTreeJob.create(
            workspace_id=workspace_id,
            requested_by=uuid.uuid4(),
            ids_hash="cache-key-A",
            now=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        .mark_running(datetime.now(timezone.utc) - timedelta(minutes=4))
        .mark_ready(
            ScaffoldTreeResult(
                nodes=[], edges=[],
                stats=ScaffoldTreeStats(node_count=0, elapsed_ms=10, cache_hit=False),
            ),
            datetime.now(timezone.utc) - timedelta(minutes=3),
        )
    )
    await repo.save(job)

    cached = await repo.find_cached(ids_hash="cache-key-A", ttl_seconds=3600)
    assert cached is not None
    assert cached.stats.elapsed_ms == 10


@pytest.mark.asyncio
async def test_find_cached_beyond_ttl_returns_none(repo):
    job = (
        ScaffoldTreeJob.create(
            workspace_id=uuid.uuid4(),
            requested_by=uuid.uuid4(),
            ids_hash="cache-key-B",
            now=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        .mark_running(datetime.now(timezone.utc) - timedelta(hours=2))
        .mark_ready(
            ScaffoldTreeResult(
                stats=ScaffoldTreeStats(node_count=0, elapsed_ms=10, cache_hit=False)
            ),
            datetime.now(timezone.utc) - timedelta(hours=2),
        )
    )
    await repo.save(job)

    cached = await repo.find_cached(ids_hash="cache-key-B", ttl_seconds=3600)
    assert cached is None


@pytest.mark.asyncio
async def test_find_cached_ignores_non_ready_jobs(repo):
    job = ScaffoldTreeJob.create(
        workspace_id=uuid.uuid4(),
        requested_by=uuid.uuid4(),
        ids_hash="cache-key-C",
        now=datetime.now(timezone.utc),
    )
    await repo.save(job)  # status = pending
    cached = await repo.find_cached(ids_hash="cache-key-C", ttl_seconds=3600)
    assert cached is None
```

- [ ] **Step 2: Run — expect failure**

```bash
cd backend && uv run pytest tests/integration/persistence/sar_analysis/test_scaffold_tree_job_repository.py -v
```

- [ ] **Step 3: Implement the protocol, model, and repository**

```python
# backend/src/cellar/application/sar_analysis/__init__.py
```
(empty)

```python
# backend/src/cellar/application/sar_analysis/repositories.py
"""Repository protocols for the sar_analysis context."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from cellar.domain.sar_analysis.scaffold_tree_job import ScaffoldTreeJob
from cellar.domain.sar_analysis.scaffold_tree_types import ScaffoldTreeResult


class ScaffoldTreeJobRepository(Protocol):
    async def save(self, job: ScaffoldTreeJob) -> None: ...
    async def find_by_id(self, job_id: UUID, *, workspace_id: UUID) -> ScaffoldTreeJob | None: ...
    async def find_cached(self, *, ids_hash: str, ttl_seconds: int) -> ScaffoldTreeResult | None: ...
```

```python
# backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/__init__.py
```
(empty)

```python
# backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/models.py
"""SQLAlchemy model for scaffold_tree_jobs."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from cellar.infrastructure.persistence.sqlalchemy.base import Base  # adjust import per repo


class ScaffoldTreeJobModel(Base):
    __tablename__ = "scaffold_tree_jobs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    ids_hash: Mapped[str] = mapped_column(Text, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
```

```python
# backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/scaffold_tree_job_repository.py
"""SQLAlchemy implementation of ScaffoldTreeJobRepository."""

from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cellar.domain.sar_analysis.scaffold_tree_job import (
    ScaffoldTreeJob,
    ScaffoldTreeJobStatus,
)
from cellar.domain.sar_analysis.scaffold_tree_types import (
    ScaffoldTreeEdge,
    ScaffoldTreeNode,
    ScaffoldTreeResult,
    ScaffoldTreeStats,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.models import (
    ScaffoldTreeJobModel,
)


class SQLAlchemyScaffoldTreeJobRepository:
    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    async def save(self, job: ScaffoldTreeJob) -> None:
        values = {
            "id": job.id,
            "workspace_id": job.workspace_id,
            "requested_by": job.requested_by,
            "ids_hash": job.ids_hash,
            "requested_at": job.requested_at,
            "status": job.status.value,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "error_message": job.error_message,
            "result_json": _serialize_result(job.result) if job.result else None,
            "version": job.version,
        }
        stmt = pg_insert(ScaffoldTreeJobModel).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[ScaffoldTreeJobModel.id],
            set_={k: v for k, v in values.items() if k != "id"},
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def find_by_id(self, job_id: UUID, *, workspace_id: UUID) -> ScaffoldTreeJob | None:
        res = await self._session.execute(
            select(ScaffoldTreeJobModel).where(
                ScaffoldTreeJobModel.id == job_id,
                ScaffoldTreeJobModel.workspace_id == workspace_id,
            )
        )
        row = res.scalar_one_or_none()
        return _to_domain(row) if row else None

    async def find_cached(
        self, *, ids_hash: str, ttl_seconds: int
    ) -> ScaffoldTreeResult | None:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)
        res = await self._session.execute(
            select(ScaffoldTreeJobModel)
            .where(
                ScaffoldTreeJobModel.ids_hash == ids_hash,
                ScaffoldTreeJobModel.status == ScaffoldTreeJobStatus.READY.value,
                ScaffoldTreeJobModel.completed_at > cutoff,
            )
            .order_by(ScaffoldTreeJobModel.completed_at.desc())
            .limit(1)
        )
        row = res.scalar_one_or_none()
        if row is None or row.result_json is None:
            return None
        return _deserialize_result(row.result_json)


def _to_domain(row: ScaffoldTreeJobModel) -> ScaffoldTreeJob:
    return ScaffoldTreeJob(
        id=row.id,
        workspace_id=row.workspace_id,
        requested_by=row.requested_by,
        ids_hash=row.ids_hash,
        requested_at=row.requested_at,
        status=ScaffoldTreeJobStatus(row.status),
        started_at=row.started_at,
        completed_at=row.completed_at,
        error_message=row.error_message,
        result=_deserialize_result(row.result_json) if row.result_json else None,
        version=row.version,
    )


def _serialize_result(result: ScaffoldTreeResult) -> dict:
    return {
        "nodes": [
            {
                "scaffold_smiles": n.scaffold_smiles,
                "molecule_ids": [str(mid) for mid in n.molecule_ids],
                "molecule_count": n.molecule_count,
                "subtree_molecule_count": n.subtree_molecule_count,
            }
            for n in result.nodes
        ],
        "edges": [
            {"parent_smiles": e.parent_smiles, "child_smiles": e.child_smiles}
            for e in result.edges
        ],
        "stats": dataclasses.asdict(result.stats),
    }


def _deserialize_result(payload: dict) -> ScaffoldTreeResult:
    return ScaffoldTreeResult(
        nodes=[
            ScaffoldTreeNode(
                scaffold_smiles=n["scaffold_smiles"],
                molecule_ids=[uuid.UUID(mid) for mid in n["molecule_ids"]],
                molecule_count=n["molecule_count"],
                subtree_molecule_count=n["subtree_molecule_count"],
            )
            for n in payload.get("nodes", [])
        ],
        edges=[
            ScaffoldTreeEdge(parent_smiles=e["parent_smiles"], child_smiles=e["child_smiles"])
            for e in payload.get("edges", [])
        ],
        stats=ScaffoldTreeStats(**payload.get("stats", {})),
    )
```

- [ ] **Step 4: Re-run — expect pass**

```bash
cd backend && uv run pytest tests/integration/persistence/sar_analysis/test_scaffold_tree_job_repository.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/application/sar_analysis/ \
        backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/ \
        backend/tests/integration/persistence/sar_analysis/
git commit -m "feat(scaffold-tree): ScaffoldTreeJobRepository with cache lookup"
```

---

### Task 12: `ScaffoldNetworkBuilder` infra wrapper

**Files:**
- Create: `backend/src/cellar/infrastructure/rdkit/scaffold_network_builder.py`
- Test: `backend/tests/unit/infrastructure/rdkit/test_scaffold_network_builder.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/infrastructure/rdkit/test_scaffold_network_builder.py
from __future__ import annotations
import pytest
from rdkit import Chem
from cellar.infrastructure.rdkit.scaffold_network_builder import (
    ScaffoldNetworkBuilder,
    RawScaffoldNetwork,
)


@pytest.fixture()
def builder():
    return ScaffoldNetworkBuilder()


def test_empty_list_returns_empty_network(builder):
    net = builder.build([])
    assert net.node_smiles == []
    assert net.edges == []


def test_single_benzene_yields_benzene_node(builder):
    net = builder.build([Chem.MolFromSmiles("c1ccccc1")])
    assert "c1ccccc1" in net.node_smiles


def test_two_related_aromatics_share_parent(builder):
    mols = [
        Chem.MolFromSmiles("c1ccc2ccccc2c1"),       # naphthalene
        Chem.MolFromSmiles("c1ccc(-c2ccccc2)cc1"),  # biphenyl
    ]
    net = builder.build(mols)
    # Both should share benzene as an ancestor at some depth
    assert "c1ccccc1" in net.node_smiles
    # Naphthalene present as its own node
    assert any("c1ccc2ccccc2c1" == n for n in net.node_smiles)
    # At least one parent->child edge
    assert any(e[0] == "c1ccccc1" for e in net.edges)


def test_skips_unparseable_mols(builder):
    mols = [Chem.MolFromSmiles("c1ccccc1"), None]
    net = builder.build(mols)
    assert "c1ccccc1" in net.node_smiles
```

- [ ] **Step 2: Run — expect failure**

- [ ] **Step 3: Implement**

```python
# backend/src/cellar/infrastructure/rdkit/scaffold_network_builder.py
"""Wraps RDKit rdScaffoldNetwork.CreateScaffoldNetwork into a pure-data result.

Returns a RawScaffoldNetwork that's easy to walk in the use case layer —
the use case is responsible for mapping nodes back to owning molecule IDs.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from rdkit import Chem
from rdkit.Chem.Scaffolds import rdScaffoldNetwork

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RawScaffoldNetwork:
    node_smiles: list[str]
    edges: list[tuple[str, str]]  # (parent_smiles, child_smiles)


class ScaffoldNetworkBuilder:
    def __init__(self) -> None:
        # Default ScaffoldNetworkParams() — Schuffenhauer-style hierarchy.
        # Pin params explicitly so RDKit upgrades can't silently shift behavior.
        self._params = rdScaffoldNetwork.ScaffoldNetworkParams()

    def build(self, mols: list[Chem.Mol | None]) -> RawScaffoldNetwork:
        ringed = [m for m in mols if m is not None and m.GetRingInfo().NumRings() > 0]
        if not ringed:
            return RawScaffoldNetwork(node_smiles=[], edges=[])
        try:
            net = rdScaffoldNetwork.CreateScaffoldNetwork(ringed, self._params)
        except Exception as exc:
            logger.warning("scaffold_network_build_failed", exc=str(exc))
            return RawScaffoldNetwork(node_smiles=[], edges=[])
        node_smiles = [str(n) for n in net.nodes]
        edges: list[tuple[str, str]] = []
        for edge in net.edges:
            try:
                parent = node_smiles[edge.beginIdx]
                child = node_smiles[edge.endIdx]
            except IndexError:  # pragma: no cover
                continue
            edges.append((parent, child))
        return RawScaffoldNetwork(node_smiles=node_smiles, edges=edges)
```

- [ ] **Step 4: Re-run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/rdkit/scaffold_network_builder.py \
        backend/tests/unit/infrastructure/rdkit/test_scaffold_network_builder.py
git commit -m "feat(scaffold-tree): ScaffoldNetworkBuilder infra wrapper"
```

---

### Task 13: `BuildScaffoldNetwork` use case (cache-aware)

**Files:**
- Create: `backend/src/cellar/application/sar_analysis/build_scaffold_network.py`
- Test: `backend/tests/unit/application/sar_analysis/test_build_scaffold_network.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/application/sar_analysis/test_build_scaffold_network.py
from __future__ import annotations
import uuid
from datetime import datetime, timezone

import pytest

from cellar.application.sar_analysis.build_scaffold_network import (
    BuildScaffoldNetwork,
    BuildScaffoldNetworkInput,
    compute_ids_hash,
)
from cellar.domain.sar_analysis.scaffold_tree_types import (
    NO_SCAFFOLD_SENTINEL,
    ScaffoldTreeResult,
)


class _FakeMoleculeFetcher:
    def __init__(self, mols):
        # mols: list of tuples (id, smiles, bemis_murcko_smiles)
        self._mols = mols

    async def fetch_for_scaffold_tree(
        self, *, molecule_ids, workspace_id
    ):
        wanted = set(molecule_ids)
        return [m for m in self._mols if m[0] in wanted]


class _NeverCachingRepo:
    async def find_cached(self, *, ids_hash, ttl_seconds):
        return None


@pytest.mark.asyncio
async def test_empty_input_returns_empty_result():
    uc = BuildScaffoldNetwork(
        molecule_fetcher=_FakeMoleculeFetcher([]),
        job_repository=_NeverCachingRepo(),
        cache_ttl_seconds=3600,
    )
    out = await uc.execute(
        BuildScaffoldNetworkInput(
            molecule_ids=[], workspace_id=uuid.uuid4()
        )
    )
    assert out.nodes == []
    assert out.edges == []
    assert out.stats.cache_hit is False


@pytest.mark.asyncio
async def test_acyclic_mols_grouped_under_no_scaffold_bucket():
    workspace_id = uuid.uuid4()
    m1 = uuid.uuid4()
    m2 = uuid.uuid4()
    uc = BuildScaffoldNetwork(
        molecule_fetcher=_FakeMoleculeFetcher([(m1, "CCCC", ""), (m2, "CCCCO", "")]),
        job_repository=_NeverCachingRepo(),
        cache_ttl_seconds=3600,
    )
    out = await uc.execute(
        BuildScaffoldNetworkInput(molecule_ids=[m1, m2], workspace_id=workspace_id)
    )
    bucket = [n for n in out.nodes if n.scaffold_smiles == NO_SCAFFOLD_SENTINEL]
    assert len(bucket) == 1
    assert set(bucket[0].molecule_ids) == {m1, m2}


@pytest.mark.asyncio
async def test_ringed_mols_yield_network_with_member_counts():
    workspace_id = uuid.uuid4()
    m1 = uuid.uuid4()
    m2 = uuid.uuid4()
    uc = BuildScaffoldNetwork(
        molecule_fetcher=_FakeMoleculeFetcher([
            (m1, "c1ccccc1", "c1ccccc1"),
            (m2, "CC(C)Cc1ccc(cc1)C(C)C(=O)O", "c1ccccc1"),  # ibuprofen
        ]),
        job_repository=_NeverCachingRepo(),
        cache_ttl_seconds=3600,
    )
    out = await uc.execute(
        BuildScaffoldNetworkInput(molecule_ids=[m1, m2], workspace_id=workspace_id)
    )
    benzene_node = next(n for n in out.nodes if n.scaffold_smiles == "c1ccccc1")
    assert benzene_node.molecule_count == 2
    assert set(benzene_node.molecule_ids) == {m1, m2}


@pytest.mark.asyncio
async def test_cache_hit_short_circuits():
    workspace_id = uuid.uuid4()

    class _AlwaysCacheHitRepo:
        async def find_cached(self, *, ids_hash, ttl_seconds):
            from cellar.domain.sar_analysis.scaffold_tree_types import (
                ScaffoldTreeStats, ScaffoldTreeResult,
            )
            return ScaffoldTreeResult(
                nodes=[], edges=[],
                stats=ScaffoldTreeStats(node_count=0, elapsed_ms=999, cache_hit=False),
            )

    fetched_calls = []
    class _SpyFetcher:
        async def fetch_for_scaffold_tree(self, *, molecule_ids, workspace_id):
            fetched_calls.append((tuple(molecule_ids), workspace_id))
            return []

    uc = BuildScaffoldNetwork(
        molecule_fetcher=_SpyFetcher(),
        job_repository=_AlwaysCacheHitRepo(),
        cache_ttl_seconds=3600,
    )
    out = await uc.execute(
        BuildScaffoldNetworkInput(
            molecule_ids=[uuid.uuid4()], workspace_id=workspace_id
        )
    )
    assert out.stats.cache_hit is True
    assert fetched_calls == []  # fetcher untouched


def test_ids_hash_stable_under_reorder():
    a = uuid.uuid4()
    b = uuid.uuid4()
    assert compute_ids_hash([a, b]) == compute_ids_hash([b, a])
```

- [ ] **Step 2: Run — expect failure**

- [ ] **Step 3: Implement**

```python
# backend/src/cellar/application/sar_analysis/build_scaffold_network.py
"""BuildScaffoldNetwork — pure-structural scaffold tree builder.

Pipeline:
1. compute_ids_hash → stable cache key.
2. job repository cache lookup → short-circuit on hit.
3. fetch (id, smiles, bemis_murcko_smiles) tuples scoped to workspace.
4. partition into ringed (network) vs acyclic (NO_SCAFFOLD bucket).
5. ScaffoldNetworkBuilder builds the raw network.
6. Map node SMILES → owning molecule_ids by their stored bemis_murcko_smiles.
7. Compute subtree counts via DFS from each node down the edge graph.
8. Return ScaffoldTreeResult (caller persists if it wants caching).
"""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from rdkit import Chem

from cellar.application.sar_analysis.repositories import ScaffoldTreeJobRepository
from cellar.domain.sar_analysis.scaffold_tree_types import (
    NO_SCAFFOLD_SENTINEL,
    ScaffoldTreeEdge,
    ScaffoldTreeNode,
    ScaffoldTreeResult,
    ScaffoldTreeStats,
)
from cellar.infrastructure.rdkit.scaffold_network_builder import ScaffoldNetworkBuilder


@dataclass(frozen=True)
class BuildScaffoldNetworkInput:
    molecule_ids: list[UUID]
    workspace_id: UUID


class MoleculeFetcherForScaffoldTree(Protocol):
    async def fetch_for_scaffold_tree(
        self, *, molecule_ids: list[UUID], workspace_id: UUID
    ) -> list[tuple[UUID, str, str | None]]: ...


def compute_ids_hash(ids: list[UUID]) -> str:
    payload = ",".join(sorted(str(i) for i in ids))
    return hashlib.sha256(payload.encode()).hexdigest()


class BuildScaffoldNetwork:
    def __init__(
        self,
        *,
        molecule_fetcher: MoleculeFetcherForScaffoldTree,
        job_repository: ScaffoldTreeJobRepository,
        cache_ttl_seconds: int = 3600,
        network_builder: ScaffoldNetworkBuilder | None = None,
    ) -> None:
        self._fetcher = molecule_fetcher
        self._repo = job_repository
        self._ttl = cache_ttl_seconds
        self._builder = network_builder or ScaffoldNetworkBuilder()

    async def execute(self, payload: BuildScaffoldNetworkInput) -> ScaffoldTreeResult:
        ids_hash = compute_ids_hash(payload.molecule_ids)

        cached = await self._repo.find_cached(ids_hash=ids_hash, ttl_seconds=self._ttl)
        if cached is not None:
            return ScaffoldTreeResult(
                nodes=cached.nodes,
                edges=cached.edges,
                stats=ScaffoldTreeStats(
                    node_count=cached.stats.node_count,
                    elapsed_ms=cached.stats.elapsed_ms,
                    cache_hit=True,
                    truncated=cached.stats.truncated,
                ),
            )

        started = time.perf_counter()
        rows = await self._fetcher.fetch_for_scaffold_tree(
            molecule_ids=payload.molecule_ids, workspace_id=payload.workspace_id
        )
        if not rows:
            return _empty_result(started)

        ringed_rows: list[tuple[UUID, Chem.Mol, str]] = []
        acyclic_ids: list[UUID] = []
        scaffold_to_mol_ids: dict[str, list[UUID]] = defaultdict(list)
        for mid, smi, scaffold in rows:
            if scaffold == "":
                acyclic_ids.append(mid)
                continue
            if scaffold is None:
                continue  # not yet computed — exclude silently
            mol = Chem.MolFromSmiles(smi)
            if mol is None:
                continue
            ringed_rows.append((mid, mol, scaffold))
            scaffold_to_mol_ids[scaffold].append(mid)

        network = self._builder.build([mol for _, mol, _ in ringed_rows])

        # subtree counts via DFS down child edges
        children: dict[str, list[str]] = defaultdict(list)
        for parent, child in network.edges:
            children[parent].append(child)

        memo: dict[str, int] = {}

        def subtree_count(node: str) -> int:
            if node in memo:
                return memo[node]
            own = len(scaffold_to_mol_ids.get(node, []))
            total = own + sum(subtree_count(c) for c in children.get(node, []))
            memo[node] = total
            return total

        nodes: list[ScaffoldTreeNode] = []
        for scaffold in network.node_smiles:
            members = scaffold_to_mol_ids.get(scaffold, [])
            nodes.append(
                ScaffoldTreeNode(
                    scaffold_smiles=scaffold,
                    molecule_ids=list(members),
                    molecule_count=len(members),
                    subtree_molecule_count=subtree_count(scaffold),
                )
            )

        if acyclic_ids:
            nodes.append(
                ScaffoldTreeNode(
                    scaffold_smiles=NO_SCAFFOLD_SENTINEL,
                    molecule_ids=list(acyclic_ids),
                    molecule_count=len(acyclic_ids),
                    subtree_molecule_count=len(acyclic_ids),
                )
            )

        edges = [
            ScaffoldTreeEdge(parent_smiles=p, child_smiles=c)
            for p, c in network.edges
        ]

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return ScaffoldTreeResult(
            nodes=nodes,
            edges=edges,
            stats=ScaffoldTreeStats(
                node_count=len(nodes),
                elapsed_ms=elapsed_ms,
                cache_hit=False,
            ),
        )


def _empty_result(started: float) -> ScaffoldTreeResult:
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return ScaffoldTreeResult(
        nodes=[],
        edges=[],
        stats=ScaffoldTreeStats(
            node_count=0, elapsed_ms=elapsed_ms, cache_hit=False
        ),
    )
```

- [ ] **Step 4: Re-run — expect pass**

```bash
cd backend && uv run pytest tests/unit/application/sar_analysis/test_build_scaffold_network.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/application/sar_analysis/build_scaffold_network.py \
        backend/tests/unit/application/sar_analysis/test_build_scaffold_network.py
git commit -m "feat(scaffold-tree): BuildScaffoldNetwork use case (cache-aware, NO_SCAFFOLD bucket)"
```

---

## Wave 3 — Async pipeline + API (Tasks 14–19)

### Task 14: `StartScaffoldTreeJob` (sync-or-async dispatch)

**Files:**
- Create: `backend/src/cellar/application/sar_analysis/start_scaffold_tree_job.py`
- Test: `backend/tests/unit/application/sar_analysis/test_start_scaffold_tree_job.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/application/sar_analysis/test_start_scaffold_tree_job.py
from __future__ import annotations
import uuid
from datetime import datetime, timezone

import pytest

from cellar.application.sar_analysis.start_scaffold_tree_job import (
    StartScaffoldTreeJob,
    StartScaffoldTreeJobInput,
    StartScaffoldTreeJobOutput,
)
from cellar.application.sar_analysis.build_scaffold_network import compute_ids_hash
from cellar.domain.sar_analysis.scaffold_tree_types import (
    ScaffoldTreeResult,
    ScaffoldTreeStats,
)


class _CacheHitBuilder:
    async def execute(self, payload):
        return ScaffoldTreeResult(
            nodes=[], edges=[],
            stats=ScaffoldTreeStats(node_count=0, elapsed_ms=10, cache_hit=True),
        )


class _CacheMissBuilder:
    async def execute(self, payload):
        return ScaffoldTreeResult(
            nodes=[], edges=[],
            stats=ScaffoldTreeStats(node_count=0, elapsed_ms=10, cache_hit=False),
        )


class _InMemoryRepo:
    def __init__(self):
        self.saved = []

    async def save(self, job):
        self.saved.append(job)

    async def find_by_id(self, job_id, *, workspace_id):
        for j in self.saved:
            if j.id == job_id and j.workspace_id == workspace_id:
                return j
        return None

    async def find_cached(self, *, ids_hash, ttl_seconds):
        return None


class _StubOrchestrator:
    def __init__(self):
        self.scheduled = []

    async def schedule(self, *, job_id, molecule_ids):
        self.scheduled.append((job_id, list(molecule_ids)))

    async def cancel(self, *, job_id):
        pass


@pytest.mark.asyncio
async def test_cache_hit_returns_inline_no_job():
    out = await StartScaffoldTreeJob(
        builder=_CacheHitBuilder(),
        repository=_InMemoryRepo(),
        orchestrator=_StubOrchestrator(),
        sync_limit=500,
    ).execute(
        StartScaffoldTreeJobInput(
            molecule_ids=[uuid.uuid4()],
            workspace_id=uuid.uuid4(),
            requested_by=uuid.uuid4(),
            now=datetime.now(timezone.utc),
        )
    )
    assert out.tree is not None
    assert out.job is None
    assert out.tree.stats.cache_hit is True


@pytest.mark.asyncio
async def test_small_set_runs_sync_no_job():
    repo = _InMemoryRepo()
    orchestrator = _StubOrchestrator()
    out = await StartScaffoldTreeJob(
        builder=_CacheMissBuilder(),
        repository=repo,
        orchestrator=orchestrator,
        sync_limit=500,
    ).execute(
        StartScaffoldTreeJobInput(
            molecule_ids=[uuid.uuid4() for _ in range(5)],
            workspace_id=uuid.uuid4(),
            requested_by=uuid.uuid4(),
            now=datetime.now(timezone.utc),
        )
    )
    assert out.tree is not None
    assert out.job is None
    # The sync path persists a READY job so the result is cached for next time
    assert any(j.status.value == "ready" for j in repo.saved)
    assert orchestrator.scheduled == []  # never scheduled async


@pytest.mark.asyncio
async def test_large_set_creates_job_and_schedules():
    repo = _InMemoryRepo()
    orchestrator = _StubOrchestrator()
    workspace_id = uuid.uuid4()
    molecule_ids = [uuid.uuid4() for _ in range(501)]
    out = await StartScaffoldTreeJob(
        builder=_CacheMissBuilder(),  # builder not called on async path
        repository=repo,
        orchestrator=orchestrator,
        sync_limit=500,
    ).execute(
        StartScaffoldTreeJobInput(
            molecule_ids=molecule_ids,
            workspace_id=workspace_id,
            requested_by=uuid.uuid4(),
            now=datetime.now(timezone.utc),
        )
    )
    assert out.tree is None
    assert out.job is not None
    assert out.job.status.value == "pending"
    assert orchestrator.scheduled and orchestrator.scheduled[0][0] == out.job.id


@pytest.mark.asyncio
async def test_large_set_cache_hit_returns_inline_no_job():
    repo = _InMemoryRepo()
    orchestrator = _StubOrchestrator()
    out = await StartScaffoldTreeJob(
        builder=_CacheHitBuilder(),
        repository=repo,
        orchestrator=orchestrator,
        sync_limit=500,
    ).execute(
        StartScaffoldTreeJobInput(
            molecule_ids=[uuid.uuid4() for _ in range(1000)],
            workspace_id=uuid.uuid4(),
            requested_by=uuid.uuid4(),
            now=datetime.now(timezone.utc),
        )
    )
    assert out.tree is not None
    assert out.job is None
    assert orchestrator.scheduled == []
```

- [ ] **Step 2: Run — expect failure**

- [ ] **Step 3: Implement**

```python
# backend/src/cellar/application/sar_analysis/start_scaffold_tree_job.py
"""StartScaffoldTreeJob — single entry-point for the scaffold-tree endpoint.

Dispatches one of three paths:
1. Cache hit (any size)      -> return tree inline (200 in the route).
2. Cache miss, <= sync_limit -> compute synchronously, persist as a READY job
                                  for cache reuse, return tree inline (200).
3. Cache miss, > sync_limit  -> create a PENDING job, schedule the workflow,
                                  return job inline (202 in the route).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from cellar.application.sar_analysis.build_scaffold_network import (
    BuildScaffoldNetwork,
    BuildScaffoldNetworkInput,
    compute_ids_hash,
)
from cellar.application.sar_analysis.repositories import ScaffoldTreeJobRepository
from cellar.domain.sar_analysis.scaffold_tree_job import (
    ScaffoldTreeJob,
)
from cellar.domain.sar_analysis.scaffold_tree_types import ScaffoldTreeResult


@dataclass(frozen=True)
class StartScaffoldTreeJobInput:
    molecule_ids: list[UUID]
    workspace_id: UUID
    requested_by: UUID
    now: datetime


@dataclass(frozen=True)
class StartScaffoldTreeJobOutput:
    tree: ScaffoldTreeResult | None
    job: ScaffoldTreeJob | None


class ScaffoldTreeOrchestrator(Protocol):
    async def schedule(self, *, job_id: UUID, molecule_ids: list[UUID]) -> None: ...
    async def cancel(self, *, job_id: UUID) -> None: ...


class StartScaffoldTreeJob:
    def __init__(
        self,
        *,
        builder: BuildScaffoldNetwork,
        repository: ScaffoldTreeJobRepository,
        orchestrator: ScaffoldTreeOrchestrator,
        sync_limit: int = 500,
    ) -> None:
        self._builder = builder
        self._repo = repository
        self._orchestrator = orchestrator
        self._sync_limit = sync_limit

    async def execute(self, payload: StartScaffoldTreeJobInput) -> StartScaffoldTreeJobOutput:
        # Try the cache first regardless of size — a cache hit always wins.
        tentative = await self._builder.execute(
            BuildScaffoldNetworkInput(
                molecule_ids=payload.molecule_ids,
                workspace_id=payload.workspace_id,
            )
        ) if len(payload.molecule_ids) <= self._sync_limit else None

        if tentative is not None and tentative.stats.cache_hit:
            return StartScaffoldTreeJobOutput(tree=tentative, job=None)

        if tentative is not None:
            # cache miss + small set — persist a READY job for the next call
            job = (
                ScaffoldTreeJob.create(
                    workspace_id=payload.workspace_id,
                    requested_by=payload.requested_by,
                    ids_hash=compute_ids_hash(payload.molecule_ids),
                    now=payload.now,
                )
                .mark_running(payload.now)
                .mark_ready(tentative, payload.now)
            )
            await self._repo.save(job)
            return StartScaffoldTreeJobOutput(tree=tentative, job=None)

        # Large set — try cache lookup via repository alone (avoids fetcher round-trip)
        cached = await self._repo.find_cached(
            ids_hash=compute_ids_hash(payload.molecule_ids), ttl_seconds=3600
        )
        if cached is not None:
            return StartScaffoldTreeJobOutput(tree=cached, job=None)

        # Cache miss + large set — create pending job + schedule workflow
        job = ScaffoldTreeJob.create(
            workspace_id=payload.workspace_id,
            requested_by=payload.requested_by,
            ids_hash=compute_ids_hash(payload.molecule_ids),
            now=payload.now,
        )
        await self._repo.save(job)
        await self._orchestrator.schedule(job_id=job.id, molecule_ids=list(payload.molecule_ids))
        return StartScaffoldTreeJobOutput(tree=None, job=job)
```

- [ ] **Step 4: Re-run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/application/sar_analysis/start_scaffold_tree_job.py \
        backend/tests/unit/application/sar_analysis/test_start_scaffold_tree_job.py
git commit -m "feat(scaffold-tree): StartScaffoldTreeJob — sync/async dispatch"
```

---

### Task 15: `ScaffoldTreeWorkflow` + activity + orchestrator

**Files:**
- Create: `backend/src/cellar/infrastructure/temporal/workflows/scaffold_tree.py`
- Create: `backend/src/cellar/infrastructure/temporal/activities/scaffold_tree.py`
- Create: `backend/src/cellar/infrastructure/temporal/orchestrators/scaffold_tree.py`
- Test: `backend/tests/unit/infrastructure/temporal/test_scaffold_tree_orchestrators.py`

Mirrors the export pipeline shape (`infrastructure/temporal/workflows/export.py` + `activities/export.py` + `orchestrators/export.py`). Read those three files first; this task copies the same patterns with `scaffold_tree`-shaped names.

- [ ] **Step 1: Write the failing test (NullOrchestrator)**

```python
# backend/tests/unit/infrastructure/temporal/test_scaffold_tree_orchestrators.py
from __future__ import annotations
import asyncio
import uuid

import pytest

from cellar.infrastructure.temporal.orchestrators.scaffold_tree import (
    NullScaffoldTreeOrchestrator,
)
from cellar.domain.sar_analysis.scaffold_tree_types import (
    ScaffoldTreeResult,
    ScaffoldTreeStats,
)


class _SpyRunner:
    def __init__(self):
        self.called_with = None

    async def run(self, *, job_id, molecule_ids):
        self.called_with = (job_id, list(molecule_ids))


@pytest.mark.asyncio
async def test_null_orchestrator_invokes_runner_inline():
    runner = _SpyRunner()
    o = NullScaffoldTreeOrchestrator(runner=runner)
    job_id = uuid.uuid4()
    mol_ids = [uuid.uuid4(), uuid.uuid4()]
    await o.schedule(job_id=job_id, molecule_ids=mol_ids)
    # NullOrchestrator runs fire-and-forget; give the task a beat
    await asyncio.sleep(0.05)
    assert runner.called_with == (job_id, mol_ids)


@pytest.mark.asyncio
async def test_null_orchestrator_cancel_is_noop():
    o = NullScaffoldTreeOrchestrator(runner=_SpyRunner())
    await o.cancel(job_id=uuid.uuid4())
```

- [ ] **Step 2: Run — expect failure**

- [ ] **Step 3: Implement workflow, activity, and orchestrator**

```python
# backend/src/cellar/infrastructure/temporal/workflows/scaffold_tree.py
"""ScaffoldTreeWorkflow — wraps the activity that does the real work."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn
class ScaffoldTreeWorkflow:
    @workflow.run
    async def run(self, job_id: UUID, molecule_ids: list[UUID]) -> None:
        await workflow.execute_activity(
            "run_scaffold_tree",
            args=[job_id, molecule_ids],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
```

```python
# backend/src/cellar/infrastructure/temporal/activities/scaffold_tree.py
"""Activity that drives BuildScaffoldNetwork + marks the job."""

from __future__ import annotations

import structlog
from datetime import datetime, timezone
from uuid import UUID

from temporalio import activity

from cellar.application.sar_analysis.build_scaffold_network import (
    BuildScaffoldNetwork,
    BuildScaffoldNetworkInput,
)
from cellar.application.sar_analysis.repositories import ScaffoldTreeJobRepository

logger = structlog.get_logger(__name__)


def make_scaffold_tree_activity(
    *, builder: BuildScaffoldNetwork, repository: ScaffoldTreeJobRepository
):
    """Factory returning the Temporal activity. We close over deps so the worker
    can register a single named activity."""

    @activity.defn(name="run_scaffold_tree")
    async def run_scaffold_tree(job_id: UUID, molecule_ids: list[UUID]) -> None:
        # The job already exists in PENDING — load workspace_id off it.
        # Two-step lookup pattern matches export pipeline.
        from cellar.infrastructure.persistence.sqlalchemy.session import async_session_factory  # adjust
        async with async_session_factory() as session:
            # Find by id via raw select — the activity boundary owns its session
            from sqlalchemy import select
            from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.models import (
                ScaffoldTreeJobModel,
            )
            row = (
                await session.execute(
                    select(ScaffoldTreeJobModel).where(ScaffoldTreeJobModel.id == job_id)
                )
            ).scalar_one()
            workspace_id = row.workspace_id

        try:
            # mark running
            from cellar.domain.sar_analysis.scaffold_tree_job import ScaffoldTreeJobStatus
            # Re-fetch via the repo's full domain hydration so save round-trips cleanly
            running = (
                await repository.find_by_id(job_id, workspace_id=workspace_id)
            ).mark_running(datetime.now(timezone.utc))
            await repository.save(running)

            tree = await builder.execute(
                BuildScaffoldNetworkInput(
                    molecule_ids=molecule_ids, workspace_id=workspace_id
                )
            )

            ready = running.mark_ready(tree, datetime.now(timezone.utc))
            await repository.save(ready)
        except Exception as exc:
            logger.exception("scaffold_tree_activity_failed", job_id=str(job_id))
            current = await repository.find_by_id(job_id, workspace_id=workspace_id)
            if current is not None:
                failed = current.mark_failed(str(exc), datetime.now(timezone.utc))
                await repository.save(failed)
            raise

    return run_scaffold_tree
```

```python
# backend/src/cellar/infrastructure/temporal/orchestrators/scaffold_tree.py
"""TemporalScaffoldTreeOrchestrator + NullScaffoldTreeOrchestrator.

The Null version runs the activity body in-process for tests and dev (when
TEMPORAL_DISABLED=1). Mirrors NullExportOrchestrator.
"""

from __future__ import annotations

import asyncio
from typing import Protocol
from uuid import UUID

from cellar.application.sar_analysis.start_scaffold_tree_job import (
    ScaffoldTreeOrchestrator,
)


class ScaffoldTreeRunner(Protocol):
    async def run(self, *, job_id: UUID, molecule_ids: list[UUID]) -> None: ...


class NullScaffoldTreeOrchestrator(ScaffoldTreeOrchestrator):
    """Fire-and-forget inline runner for tests / dev."""

    def __init__(self, *, runner: ScaffoldTreeRunner) -> None:
        self._runner = runner
        self._tasks: list[asyncio.Task] = []

    async def schedule(self, *, job_id: UUID, molecule_ids: list[UUID]) -> None:
        self._tasks.append(
            asyncio.create_task(self._runner.run(job_id=job_id, molecule_ids=molecule_ids))
        )

    async def cancel(self, *, job_id: UUID) -> None:
        # No back-reference from job_id to task in this minimal impl —
        # cancellation in the Null path is best-effort + tests don't exercise it.
        return None


class TemporalScaffoldTreeOrchestrator(ScaffoldTreeOrchestrator):
    """Schedules ScaffoldTreeWorkflow on a Temporal client."""

    def __init__(self, *, client_provider, task_queue: str) -> None:
        # client_provider: () -> Awaitable[Client]  — matches Cellar's existing
        # Temporal client provider pattern. See infrastructure/temporal/orchestrators/export.py.
        self._client_provider = client_provider
        self._task_queue = task_queue

    async def schedule(self, *, job_id: UUID, molecule_ids: list[UUID]) -> None:
        from cellar.infrastructure.temporal.workflows.scaffold_tree import ScaffoldTreeWorkflow
        client = await self._client_provider()
        await client.start_workflow(
            ScaffoldTreeWorkflow.run,
            args=[job_id, molecule_ids],
            id=f"scaffold-tree-{job_id}",
            task_queue=self._task_queue,
        )

    async def cancel(self, *, job_id: UUID) -> None:
        client = await self._client_provider()
        handle = client.get_workflow_handle(f"scaffold-tree-{job_id}")
        await handle.cancel()
```

If the existing export orchestrator uses different conventions (e.g. injected `Client` directly rather than a provider), match those — don't introduce a divergent pattern.

Register the workflow + activity in the worker bootstrap (look for `infrastructure/temporal/worker.py` or similar — the export pipeline added itself there). Mirror the pattern.

- [ ] **Step 4: Re-run — expect pass**

```bash
cd backend && uv run pytest tests/unit/infrastructure/temporal/test_scaffold_tree_orchestrators.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/temporal/workflows/scaffold_tree.py \
        backend/src/cellar/infrastructure/temporal/activities/scaffold_tree.py \
        backend/src/cellar/infrastructure/temporal/orchestrators/scaffold_tree.py \
        backend/tests/unit/infrastructure/temporal/test_scaffold_tree_orchestrators.py
git commit -m "feat(scaffold-tree): Temporal workflow + activity + orchestrators"
```

---

### Task 16: `GetScaffoldTreeJob` + `CancelScaffoldTreeJob`

**Files:**
- Create: `backend/src/cellar/application/sar_analysis/get_scaffold_tree_job.py`
- Create: `backend/src/cellar/application/sar_analysis/cancel_scaffold_tree_job.py`
- Test: `backend/tests/unit/application/sar_analysis/test_get_and_cancel_scaffold_tree_job.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/application/sar_analysis/test_get_and_cancel_scaffold_tree_job.py
from __future__ import annotations
import uuid
from datetime import datetime, timezone

import pytest

from cellar.application.sar_analysis.get_scaffold_tree_job import (
    GetScaffoldTreeJob,
    GetScaffoldTreeJobInput,
    ScaffoldTreeJobNotFound,
)
from cellar.application.sar_analysis.cancel_scaffold_tree_job import (
    CancelScaffoldTreeJob,
    CancelScaffoldTreeJobInput,
)
from cellar.domain.sar_analysis.scaffold_tree_job import (
    ScaffoldTreeJob,
    ScaffoldTreeJobStatus,
)


class _InMemoryRepo:
    def __init__(self): self.saved = {}
    async def save(self, job): self.saved[job.id] = job
    async def find_by_id(self, jid, *, workspace_id):
        job = self.saved.get(jid)
        if job and job.workspace_id == workspace_id:
            return job
        return None
    async def find_cached(self, **kw): return None


class _StubOrchestrator:
    def __init__(self): self.cancels = []
    async def schedule(self, **kw): pass
    async def cancel(self, *, job_id): self.cancels.append(job_id)


@pytest.mark.asyncio
async def test_get_returns_job_when_present():
    workspace_id = uuid.uuid4()
    job = ScaffoldTreeJob.create(
        workspace_id=workspace_id, requested_by=uuid.uuid4(),
        ids_hash="x", now=datetime.now(timezone.utc),
    )
    repo = _InMemoryRepo()
    await repo.save(job)
    fetched = await GetScaffoldTreeJob(repository=repo).execute(
        GetScaffoldTreeJobInput(job_id=job.id, workspace_id=workspace_id)
    )
    assert fetched.id == job.id


@pytest.mark.asyncio
async def test_get_raises_not_found_when_missing():
    with pytest.raises(ScaffoldTreeJobNotFound):
        await GetScaffoldTreeJob(repository=_InMemoryRepo()).execute(
            GetScaffoldTreeJobInput(
                job_id=uuid.uuid4(), workspace_id=uuid.uuid4()
            )
        )


@pytest.mark.asyncio
async def test_cancel_transitions_to_cancelled_and_calls_orchestrator():
    workspace_id = uuid.uuid4()
    job = ScaffoldTreeJob.create(
        workspace_id=workspace_id, requested_by=uuid.uuid4(),
        ids_hash="x", now=datetime.now(timezone.utc),
    )
    repo = _InMemoryRepo()
    await repo.save(job)
    orchestrator = _StubOrchestrator()
    cancelled = await CancelScaffoldTreeJob(
        repository=repo, orchestrator=orchestrator
    ).execute(
        CancelScaffoldTreeJobInput(
            job_id=job.id, workspace_id=workspace_id,
            now=datetime.now(timezone.utc),
        )
    )
    assert cancelled.status == ScaffoldTreeJobStatus.CANCELLED
    assert orchestrator.cancels == [job.id]


@pytest.mark.asyncio
async def test_cancel_idempotent_on_terminal_returns_unchanged():
    workspace_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    job = (
        ScaffoldTreeJob.create(
            workspace_id=workspace_id, requested_by=uuid.uuid4(),
            ids_hash="x", now=now,
        )
        .mark_running(now)
        .mark_failed("boom", now)
    )
    repo = _InMemoryRepo()
    await repo.save(job)
    out = await CancelScaffoldTreeJob(
        repository=repo, orchestrator=_StubOrchestrator()
    ).execute(
        CancelScaffoldTreeJobInput(
            job_id=job.id, workspace_id=workspace_id, now=now,
        )
    )
    assert out.status == ScaffoldTreeJobStatus.FAILED  # unchanged
```

- [ ] **Step 2: Run — expect failure**

- [ ] **Step 3: Implement**

```python
# backend/src/cellar/application/sar_analysis/get_scaffold_tree_job.py
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from cellar.application.sar_analysis.repositories import ScaffoldTreeJobRepository
from cellar.domain.sar_analysis.scaffold_tree_job import ScaffoldTreeJob


class ScaffoldTreeJobNotFound(Exception):
    pass


@dataclass(frozen=True)
class GetScaffoldTreeJobInput:
    job_id: UUID
    workspace_id: UUID


class GetScaffoldTreeJob:
    def __init__(self, *, repository: ScaffoldTreeJobRepository) -> None:
        self._repo = repository

    async def execute(self, payload: GetScaffoldTreeJobInput) -> ScaffoldTreeJob:
        job = await self._repo.find_by_id(payload.job_id, workspace_id=payload.workspace_id)
        if job is None:
            raise ScaffoldTreeJobNotFound(str(payload.job_id))
        return job
```

```python
# backend/src/cellar/application/sar_analysis/cancel_scaffold_tree_job.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from cellar.application.sar_analysis.get_scaffold_tree_job import ScaffoldTreeJobNotFound
from cellar.application.sar_analysis.repositories import ScaffoldTreeJobRepository
from cellar.application.sar_analysis.start_scaffold_tree_job import ScaffoldTreeOrchestrator
from cellar.domain.sar_analysis.scaffold_tree_job import (
    InvalidScaffoldTreeJobTransition,
    ScaffoldTreeJob,
)


@dataclass(frozen=True)
class CancelScaffoldTreeJobInput:
    job_id: UUID
    workspace_id: UUID
    now: datetime


class CancelScaffoldTreeJob:
    def __init__(
        self,
        *,
        repository: ScaffoldTreeJobRepository,
        orchestrator: ScaffoldTreeOrchestrator,
    ) -> None:
        self._repo = repository
        self._orchestrator = orchestrator

    async def execute(self, payload: CancelScaffoldTreeJobInput) -> ScaffoldTreeJob:
        job = await self._repo.find_by_id(payload.job_id, workspace_id=payload.workspace_id)
        if job is None:
            raise ScaffoldTreeJobNotFound(str(payload.job_id))
        try:
            cancelled = job.mark_cancelled(payload.now)
        except InvalidScaffoldTreeJobTransition:
            return job  # already terminal — idempotent no-op
        await self._repo.save(cancelled)
        await self._orchestrator.cancel(job_id=job.id)
        return cancelled
```

- [ ] **Step 4: Re-run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/application/sar_analysis/get_scaffold_tree_job.py \
        backend/src/cellar/application/sar_analysis/cancel_scaffold_tree_job.py \
        backend/tests/unit/application/sar_analysis/test_get_and_cancel_scaffold_tree_job.py
git commit -m "feat(scaffold-tree): GetScaffoldTreeJob + CancelScaffoldTreeJob use cases"
```

---

### Task 17: DI wiring (`_sar_analysis.py` + container)

**Files:**
- Create: `backend/src/cellar/infrastructure/di/_sar_analysis.py`
- Modify: `backend/src/cellar/infrastructure/di/container.py` (add `_sar_analysis.configure(container)` call)
- Modify: `backend/tests/api/conftest.py` (no change required IF `TEMPORAL_DISABLED=1` is already set globally; otherwise mirror what the export test conftest does)
- Test: `backend/tests/unit/infrastructure/di/test_sar_analysis_wiring.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/infrastructure/di/test_sar_analysis_wiring.py
from __future__ import annotations
import os

import pytest

from cellar.application.sar_analysis.build_scaffold_network import BuildScaffoldNetwork
from cellar.application.sar_analysis.start_scaffold_tree_job import (
    StartScaffoldTreeJob,
    ScaffoldTreeOrchestrator,
)
from cellar.application.sar_analysis.repositories import ScaffoldTreeJobRepository


def test_container_resolves_use_cases(make_container):
    container = make_container()
    assert isinstance(container[BuildScaffoldNetwork], BuildScaffoldNetwork)
    assert isinstance(container[StartScaffoldTreeJob], StartScaffoldTreeJob)
    # Repository binding — at least one concrete impl is bound
    assert container[ScaffoldTreeJobRepository] is not None
    # Orchestrator falls back to Null when TEMPORAL_DISABLED=1
    os.environ["TEMPORAL_DISABLED"] = "1"
    container2 = make_container()
    orch = container2[ScaffoldTreeOrchestrator]
    assert orch.__class__.__name__ == "NullScaffoldTreeOrchestrator"
```

`make_container` is the existing fixture that builds a fresh Lagom container — see `backend/tests/unit/infrastructure/di/conftest.py` for the pattern (the export DI tests use the same fixture).

- [ ] **Step 2: Run — expect failure**

- [ ] **Step 3: Implement DI module**

```python
# backend/src/cellar/infrastructure/di/_sar_analysis.py
"""DI wiring for the sar_analysis bounded context."""

from __future__ import annotations

import os

from lagom import Container, Singleton

from cellar.application.sar_analysis.build_scaffold_network import BuildScaffoldNetwork
from cellar.application.sar_analysis.cancel_scaffold_tree_job import CancelScaffoldTreeJob
from cellar.application.sar_analysis.get_scaffold_tree_job import GetScaffoldTreeJob
from cellar.application.sar_analysis.repositories import ScaffoldTreeJobRepository
from cellar.application.sar_analysis.start_scaffold_tree_job import (
    ScaffoldTreeOrchestrator,
    StartScaffoldTreeJob,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.scaffold_tree_job_repository import (
    SQLAlchemyScaffoldTreeJobRepository,
)
from cellar.infrastructure.rdkit.scaffold_network_builder import ScaffoldNetworkBuilder
from cellar.infrastructure.temporal.orchestrators.scaffold_tree import (
    NullScaffoldTreeOrchestrator,
    TemporalScaffoldTreeOrchestrator,
)


class _ScaffoldTreeRunnerAdapter:
    """Adapts BuildScaffoldNetwork + repo into a ScaffoldTreeRunner for the
    NullOrchestrator (mirrors the activity body)."""

    def __init__(self, *, builder, repository):
        self._builder = builder
        self._repository = repository

    async def run(self, *, job_id, molecule_ids):
        from datetime import datetime, timezone
        job = await self._repository.find_by_id(
            job_id,
            workspace_id=(await self._lookup_workspace(job_id)),
        )
        running = job.mark_running(datetime.now(timezone.utc))
        await self._repository.save(running)
        from cellar.application.sar_analysis.build_scaffold_network import (
            BuildScaffoldNetworkInput,
        )
        tree = await self._builder.execute(
            BuildScaffoldNetworkInput(
                molecule_ids=molecule_ids, workspace_id=running.workspace_id
            )
        )
        ready = running.mark_ready(tree, datetime.now(timezone.utc))
        await self._repository.save(ready)

    async def _lookup_workspace(self, job_id):
        # Lighter than the activity body — caller already knows workspace from
        # the most-recent save. For simplicity reuse repo lookup with a wildcard
        # by selecting any workspace match — the runner is per-process in dev.
        from sqlalchemy import select
        from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.models import (
            ScaffoldTreeJobModel,
        )
        # If the codebase exposes a "raw" session injection, prefer that here.
        # Otherwise this adapter pattern needs a session factory dep — wire one.
        raise NotImplementedError(
            "Runner adapter for the Null path needs a session factory; "
            "wire from container during implementation."
        )


def configure(container: Container) -> None:
    # Infra singletons
    container[ScaffoldNetworkBuilder] = Singleton(ScaffoldNetworkBuilder)

    # Repository — abstract -> concrete
    container[SQLAlchemyScaffoldTreeJobRepository] = Singleton(
        lambda c: SQLAlchemyScaffoldTreeJobRepository(session=c[SessionFactory])  # type: ignore[name-defined]
    )
    container[ScaffoldTreeJobRepository] = lambda c: c[SQLAlchemyScaffoldTreeJobRepository]

    # Use cases
    container[BuildScaffoldNetwork] = Singleton(
        lambda c: BuildScaffoldNetwork(
            molecule_fetcher=c[ScaffoldTreeMoleculeFetcher],  # type: ignore[name-defined]
            job_repository=c[ScaffoldTreeJobRepository],
            network_builder=c[ScaffoldNetworkBuilder],
        )
    )

    # Orchestrator — Null in tests/dev, Temporal otherwise
    if os.getenv("TEMPORAL_DISABLED") == "1":
        container[ScaffoldTreeOrchestrator] = Singleton(
            lambda c: NullScaffoldTreeOrchestrator(runner=c[_ScaffoldTreeRunnerAdapter])
        )
    else:
        container[ScaffoldTreeOrchestrator] = Singleton(
            lambda c: TemporalScaffoldTreeOrchestrator(
                client_provider=c[TemporalClientProvider],  # type: ignore[name-defined]
                task_queue="cellar-default",
            )
        )

    container[StartScaffoldTreeJob] = Singleton(
        lambda c: StartScaffoldTreeJob(
            builder=c[BuildScaffoldNetwork],
            repository=c[ScaffoldTreeJobRepository],
            orchestrator=c[ScaffoldTreeOrchestrator],
        )
    )
    container[GetScaffoldTreeJob] = Singleton(
        lambda c: GetScaffoldTreeJob(repository=c[ScaffoldTreeJobRepository])
    )
    container[CancelScaffoldTreeJob] = Singleton(
        lambda c: CancelScaffoldTreeJob(
            repository=c[ScaffoldTreeJobRepository],
            orchestrator=c[ScaffoldTreeOrchestrator],
        )
    )
```

The `# type: ignore[name-defined]` markers above are placeholders for **the names this codebase actually uses for the DB session factory + Temporal client provider**. Find them by looking at how `_research_organization.py` (or any other existing `_*.py`) wires its repositories and how `infrastructure/di/_temporal.py` (if present) wires the Temporal client. Mirror exactly — the wiring inconsistency is the only thing that will go wrong at runtime.

Also: implement the `ScaffoldTreeMoleculeFetcher` Protocol + a SQLAlchemy concrete (a thin extension of `SQLAlchemyMoleculeRepository` adding `fetch_for_scaffold_tree`). That sits naturally in `infrastructure/persistence/sqlalchemy/chemical_registration/molecule_repository.py` (add a method) — bind it in this DI module.

In `container.py`:

```python
from cellar.infrastructure.di import _sar_analysis
# ...
_sar_analysis.configure(container)
```

- [ ] **Step 4: Re-run — expect pass**

```bash
cd backend && uv run pytest tests/unit/infrastructure/di/test_sar_analysis_wiring.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/di/_sar_analysis.py \
        backend/src/cellar/infrastructure/di/container.py \
        backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_repository.py \
        backend/tests/unit/infrastructure/di/test_sar_analysis_wiring.py
git commit -m "feat(scaffold-tree): DI wiring for sar_analysis context"
```

---

### Task 18: API routes (`scaffold_tree.py` + register router)

**Files:**
- Create: `backend/src/cellar/interface/routes/scaffold_tree.py`
- Modify: `backend/src/cellar/interface/app.py` (or wherever routers register; the export route lives there too)
- Test: `backend/tests/api/test_scaffold_tree_routes.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/api/test_scaffold_tree_routes.py
from __future__ import annotations
import uuid

import pytest


@pytest.mark.asyncio
async def test_post_scaffold_tree_with_no_ids_returns_empty_tree(authed_client):
    res = await authed_client.post("/api/v1/scaffold-tree", json={"molecule_ids": []})
    assert res.status_code == 200
    body = res.json()
    assert body["tree"]["nodes"] == []
    assert body["job"] is None


@pytest.mark.asyncio
async def test_post_scaffold_tree_small_set_returns_inline_tree(
    authed_client, seeded_ringed_molecules
):
    # seeded_ringed_molecules: fixture creating ~5 mols incl. benzene + ibuprofen
    mol_ids = [str(m.id) for m in seeded_ringed_molecules]
    res = await authed_client.post(
        "/api/v1/scaffold-tree", json={"molecule_ids": mol_ids}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["tree"] is not None
    assert any(n["scaffold_smiles"] == "c1ccccc1" for n in body["tree"]["nodes"])


@pytest.mark.asyncio
async def test_post_scaffold_tree_large_set_returns_job(
    authed_client, many_seeded_molecules
):
    # many_seeded_molecules: 501 mols
    mol_ids = [str(m.id) for m in many_seeded_molecules]
    res = await authed_client.post(
        "/api/v1/scaffold-tree", json={"molecule_ids": mol_ids}
    )
    assert res.status_code == 202
    body = res.json()
    assert body["tree"] is None
    assert body["job"]["status"] == "pending"


@pytest.mark.asyncio
async def test_get_scaffold_tree_job_lifecycle(authed_client, many_seeded_molecules):
    mol_ids = [str(m.id) for m in many_seeded_molecules]
    start = await authed_client.post("/api/v1/scaffold-tree", json={"molecule_ids": mol_ids})
    assert start.status_code == 202
    job_id = start.json()["job"]["id"]

    # NullOrchestrator runs the activity in-process; one poll cycle should suffice
    poll = await authed_client.get(f"/api/v1/scaffold-tree/jobs/{job_id}")
    assert poll.status_code == 200
    body = poll.json()
    assert body["status"] in {"pending", "running", "ready"}


@pytest.mark.asyncio
async def test_get_nonexistent_job_returns_404(authed_client):
    res = await authed_client.get(f"/api/v1/scaffold-tree/jobs/{uuid.uuid4()}")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_cancel_scaffold_tree_job(authed_client, many_seeded_molecules):
    mol_ids = [str(m.id) for m in many_seeded_molecules]
    start = await authed_client.post("/api/v1/scaffold-tree", json={"molecule_ids": mol_ids})
    job_id = start.json()["job"]["id"]
    res = await authed_client.post(f"/api/v1/scaffold-tree/jobs/{job_id}/cancel")
    assert res.status_code == 200
    assert res.json()["status"] in {"cancelled", "ready"}  # tolerate race
```

- [ ] **Step 2: Run — expect failure**

- [ ] **Step 3: Implement the routes**

```python
# backend/src/cellar/interface/routes/scaffold_tree.py
"""POST /api/v1/scaffold-tree + GET/cancel job endpoints."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from cellar.application.sar_analysis.cancel_scaffold_tree_job import (
    CancelScaffoldTreeJob,
    CancelScaffoldTreeJobInput,
)
from cellar.application.sar_analysis.get_scaffold_tree_job import (
    GetScaffoldTreeJob,
    GetScaffoldTreeJobInput,
    ScaffoldTreeJobNotFound,
)
from cellar.application.sar_analysis.start_scaffold_tree_job import (
    StartScaffoldTreeJob,
    StartScaffoldTreeJobInput,
)
from cellar.domain.sar_analysis.scaffold_tree_job import ScaffoldTreeJob
from cellar.domain.sar_analysis.scaffold_tree_types import ScaffoldTreeResult
from cellar.interface.deps import (  # adjust per repo
    AuthenticatedUser,
    get_authenticated_user,
    resolve_use_case,
)

router = APIRouter(prefix="/api/v1/scaffold-tree", tags=["scaffold-tree"])


class StartScaffoldTreeRequest(BaseModel):
    molecule_ids: list[UUID]


class JobView(BaseModel):
    id: UUID
    status: str
    ids_hash: str
    requested_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None


class StartScaffoldTreeResponse(BaseModel):
    tree: dict | None
    job: JobView | None


class JobDetailResponse(BaseModel):
    id: UUID
    status: str
    ids_hash: str
    requested_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    tree: dict | None = None


def _serialize_tree(tree: ScaffoldTreeResult) -> dict:
    return {
        "nodes": [
            {
                "scaffold_smiles": n.scaffold_smiles,
                "molecule_ids": [str(m) for m in n.molecule_ids],
                "molecule_count": n.molecule_count,
                "subtree_molecule_count": n.subtree_molecule_count,
            }
            for n in tree.nodes
        ],
        "edges": [
            {"parent_smiles": e.parent_smiles, "child_smiles": e.child_smiles}
            for e in tree.edges
        ],
        "stats": dataclasses.asdict(tree.stats),
    }


def _serialize_job(job: ScaffoldTreeJob) -> JobView:
    return JobView(
        id=job.id,
        status=job.status.value,
        ids_hash=job.ids_hash,
        requested_at=job.requested_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
    )


@router.post("", status_code=status.HTTP_200_OK)
async def start_scaffold_tree(
    payload: StartScaffoldTreeRequest,
    response: Response,
    user: Annotated[AuthenticatedUser, Depends(get_authenticated_user)],
    use_case: Annotated[StartScaffoldTreeJob, Depends(resolve_use_case(StartScaffoldTreeJob))],
) -> StartScaffoldTreeResponse:
    out = await use_case.execute(
        StartScaffoldTreeJobInput(
            molecule_ids=payload.molecule_ids,
            workspace_id=user.workspace_id,
            requested_by=user.id,
            now=datetime.now(timezone.utc),
        )
    )
    if out.tree is not None:
        return StartScaffoldTreeResponse(tree=_serialize_tree(out.tree), job=None)
    response.status_code = status.HTTP_202_ACCEPTED
    return StartScaffoldTreeResponse(tree=None, job=_serialize_job(out.job))  # type: ignore[arg-type]


@router.get("/jobs/{job_id}")
async def get_scaffold_tree_job(
    job_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(get_authenticated_user)],
    use_case: Annotated[GetScaffoldTreeJob, Depends(resolve_use_case(GetScaffoldTreeJob))],
) -> JobDetailResponse:
    try:
        job = await use_case.execute(
            GetScaffoldTreeJobInput(job_id=job_id, workspace_id=user.workspace_id)
        )
    except ScaffoldTreeJobNotFound:
        raise HTTPException(status_code=404, detail="scaffold tree job not found")
    return JobDetailResponse(
        id=job.id,
        status=job.status.value,
        ids_hash=job.ids_hash,
        requested_at=job.requested_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        tree=_serialize_tree(job.result) if job.result else None,
    )


@router.post("/jobs/{job_id}/cancel")
async def cancel_scaffold_tree_job(
    job_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(get_authenticated_user)],
    use_case: Annotated[CancelScaffoldTreeJob, Depends(resolve_use_case(CancelScaffoldTreeJob))],
) -> JobDetailResponse:
    try:
        job = await use_case.execute(
            CancelScaffoldTreeJobInput(
                job_id=job_id,
                workspace_id=user.workspace_id,
                now=datetime.now(timezone.utc),
            )
        )
    except ScaffoldTreeJobNotFound:
        raise HTTPException(status_code=404, detail="scaffold tree job not found")
    return JobDetailResponse(
        id=job.id,
        status=job.status.value,
        ids_hash=job.ids_hash,
        requested_at=job.requested_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        tree=_serialize_tree(job.result) if job.result else None,
    )
```

Adjust `AuthenticatedUser` / `get_authenticated_user` / `resolve_use_case` imports to match the existing codebase patterns — the export router uses the same dependency shape.

Register the router in `interface/app.py`:

```python
from cellar.interface.routes import scaffold_tree
# ...
app.include_router(scaffold_tree.router)
```

- [ ] **Step 4: Re-run — expect pass**

```bash
cd backend && uv run pytest tests/api/test_scaffold_tree_routes.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/interface/routes/scaffold_tree.py \
        backend/src/cellar/interface/app.py \
        backend/tests/api/test_scaffold_tree_routes.py
git commit -m "feat(scaffold-tree): POST /scaffold-tree + GET/cancel job endpoints"
```

---

### Task 19: Regenerate orval FE client

**Files:**
- Run: `cd frontend && pnpm orval`
- Modify: auto-generated files under `frontend/src/api/generated/` (or wherever orval writes — check `orval.config.ts`)

- [ ] **Step 1: Verify the new endpoints exist in the OpenAPI schema**

```bash
cd backend && uv run uvicorn cellar.interface.app:app --port 8000 &
sleep 2
curl -s localhost:8000/openapi.json | python -m json.tool | grep -A2 scaffold-tree
kill %1
```
Expected: three entries — POST `/api/v1/scaffold-tree`, GET `/api/v1/scaffold-tree/jobs/{job_id}`, POST `/api/v1/scaffold-tree/jobs/{job_id}/cancel`.

- [ ] **Step 2: Regenerate**

```bash
cd frontend && pnpm orval
```

- [ ] **Step 3: Sanity-check that the generated hooks exist**

```bash
grep -l "scaffoldTree\|startScaffoldTree\|getScaffoldTreeJob" frontend/src/api/generated/ -r
```
Expected: a `scaffold-tree` (or similar) module under the generated tree.

- [ ] **Step 4: Type-check**

```bash
cd frontend && pnpm exec tsc --noEmit
```
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/generated/
git commit -m "chore(api): regenerate orval client for /scaffold-tree endpoints"
```

---

## Wave 4 — Frontend (Tasks 20–28)

### Task 20: Install shadcn `Resizable` primitive

**Files:**
- Modify: `frontend/package.json` (+1 dep)
- Create: `frontend/src/shared/components/ui/resizable.tsx` (the shadcn-generated component)

- [ ] **Step 1: Check current state**

```bash
ls frontend/src/shared/components/ui/resizable.tsx 2>/dev/null || echo "missing"
grep '"react-resizable-panels"' frontend/package.json || echo "dep missing"
```
Expected: both missing.

- [ ] **Step 2: Install shadcn primitive**

```bash
cd frontend && pnpm dlx shadcn@latest add resizable
```
This (a) installs `react-resizable-panels` and (b) writes `src/shared/components/ui/resizable.tsx`.

- [ ] **Step 3: Verify import path matches the rest of the UI primitives**

```bash
head -5 frontend/src/shared/components/ui/resizable.tsx
```
Expected: imports from `react-resizable-panels`, exports `ResizablePanel`, `ResizablePanelGroup`, `ResizableHandle`.

- [ ] **Step 4: Type-check**

```bash
cd frontend && pnpm exec tsc --noEmit
```

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/pnpm-lock.yaml \
        frontend/src/shared/components/ui/resizable.tsx
git commit -m "chore(deps): add shadcn Resizable (react-resizable-panels) for scaffold tree split-pane"
```

---

### Task 21: FE wire types — `scaffold-tree.ts`

**Files:**
- Create: `frontend/src/features/sar-analysis/types/scaffold-tree.ts`
- Test: `frontend/src/features/sar-analysis/types/scaffold-tree.test.ts`

The hand-written types live alongside the generated orval ones; they shape what the FE actually passes around (orval types are wire-only).

- [ ] **Step 1: Write the failing type-shape test**

```ts
// frontend/src/features/sar-analysis/types/scaffold-tree.test.ts
import { describe, it, expect } from "vitest";
import {
  NO_SCAFFOLD_SENTINEL,
  type ScaffoldTreeNode,
  type ScaffoldTreeEdge,
  type ScaffoldTreeResult,
  type ScaffoldTreeJob,
} from "./scaffold-tree";

describe("scaffold-tree types", () => {
  it("exposes NO_SCAFFOLD_SENTINEL", () => {
    expect(NO_SCAFFOLD_SENTINEL).toBe("__no_scaffold__");
  });

  it("allows valid node construction", () => {
    const node: ScaffoldTreeNode = {
      scaffold_smiles: "c1ccccc1",
      molecule_ids: ["mol-1"],
      molecule_count: 1,
      subtree_molecule_count: 1,
    };
    expect(node.scaffold_smiles).toBe("c1ccccc1");
  });

  it("allows result with empty nodes", () => {
    const r: ScaffoldTreeResult = {
      nodes: [],
      edges: [],
      stats: { node_count: 0, elapsed_ms: 0, cache_hit: false, truncated: false },
    };
    expect(r.nodes).toHaveLength(0);
  });

  it("models job lifecycle status union", () => {
    const job: ScaffoldTreeJob = {
      id: "uuid",
      status: "pending",
      ids_hash: "hash",
      requested_at: "2026-05-17T00:00:00Z",
    };
    expect(job.status).toBe("pending");
  });
});
```

- [ ] **Step 2: Run — expect failure (module missing)**

```bash
cd frontend && pnpm vitest run src/features/sar-analysis/types/scaffold-tree.test.ts
```

- [ ] **Step 3: Implement types**

```ts
// frontend/src/features/sar-analysis/types/scaffold-tree.ts
export const NO_SCAFFOLD_SENTINEL = "__no_scaffold__";

export type ScaffoldTreeNode = {
  scaffold_smiles: string;          // canonical SMILES OR NO_SCAFFOLD_SENTINEL
  molecule_ids: string[];
  molecule_count: number;
  subtree_molecule_count: number;
};

export type ScaffoldTreeEdge = {
  parent_smiles: string;
  child_smiles: string;
};

export type ScaffoldTreeStats = {
  node_count: number;
  elapsed_ms: number;
  cache_hit: boolean;
  truncated?: boolean;
};

export type ScaffoldTreeResult = {
  nodes: ScaffoldTreeNode[];
  edges: ScaffoldTreeEdge[];
  stats: ScaffoldTreeStats;
};

export type ScaffoldTreeJobStatus =
  | "pending"
  | "running"
  | "ready"
  | "failed"
  | "cancelled";

export type ScaffoldTreeJob = {
  id: string;
  status: ScaffoldTreeJobStatus;
  ids_hash: string;
  requested_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  error_message?: string | null;
  tree?: ScaffoldTreeResult | null;
};

export type StartScaffoldTreeResponse = {
  tree: ScaffoldTreeResult | null;
  job: Pick<
    ScaffoldTreeJob,
    "id" | "status" | "ids_hash" | "requested_at" | "started_at" | "completed_at" | "error_message"
  > | null;
};
```

- [ ] **Step 4: Re-run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/sar-analysis/types/scaffold-tree.ts \
        frontend/src/features/sar-analysis/types/scaffold-tree.test.ts
git commit -m "feat(scaffold-tree): FE wire types + NO_SCAFFOLD sentinel"
```

---

### Task 22: `scaffold-tree-math.ts` — subtree helpers

**Files:**
- Create: `frontend/src/features/sar-analysis/lib/scaffold-tree-math.ts`
- Test: `frontend/src/features/sar-analysis/lib/scaffold-tree-math.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/features/sar-analysis/lib/scaffold-tree-math.test.ts
import { describe, it, expect } from "vitest";
import {
  buildChildIndex,
  collectSubtreeMolIds,
  rootNodes,
} from "./scaffold-tree-math";
import {
  NO_SCAFFOLD_SENTINEL,
  type ScaffoldTreeResult,
} from "../types/scaffold-tree";

const tree: ScaffoldTreeResult = {
  nodes: [
    { scaffold_smiles: "c1ccccc1",        molecule_ids: ["m1"],       molecule_count: 1, subtree_molecule_count: 3 },
    { scaffold_smiles: "c1ccc2ccccc2c1",  molecule_ids: ["m2"],       molecule_count: 1, subtree_molecule_count: 2 },
    { scaffold_smiles: "c1ccc2cc(N)ccc2c1", molecule_ids: ["m3"],     molecule_count: 1, subtree_molecule_count: 1 },
    { scaffold_smiles: NO_SCAFFOLD_SENTINEL, molecule_ids: ["m4","m5"], molecule_count: 2, subtree_molecule_count: 2 },
  ],
  edges: [
    { parent_smiles: "c1ccccc1",       child_smiles: "c1ccc2ccccc2c1" },
    { parent_smiles: "c1ccc2ccccc2c1", child_smiles: "c1ccc2cc(N)ccc2c1" },
  ],
  stats: { node_count: 4, elapsed_ms: 0, cache_hit: false },
};

describe("scaffold-tree-math", () => {
  it("buildChildIndex returns parent->children map", () => {
    const idx = buildChildIndex(tree);
    expect(idx.get("c1ccccc1")).toEqual(["c1ccc2ccccc2c1"]);
    expect(idx.get("c1ccc2ccccc2c1")).toEqual(["c1ccc2cc(N)ccc2c1"]);
    expect(idx.get("c1ccc2cc(N)ccc2c1")).toBeUndefined();
  });

  it("collectSubtreeMolIds gathers self + descendants", () => {
    const ids = collectSubtreeMolIds("c1ccccc1", tree);
    expect(new Set(ids)).toEqual(new Set(["m1", "m2", "m3"]));
  });

  it("collectSubtreeMolIds for leaf returns only own", () => {
    const ids = collectSubtreeMolIds("c1ccc2cc(N)ccc2c1", tree);
    expect(ids).toEqual(["m3"]);
  });

  it("collectSubtreeMolIds for no-scaffold bucket returns own", () => {
    const ids = collectSubtreeMolIds(NO_SCAFFOLD_SENTINEL, tree);
    expect(new Set(ids)).toEqual(new Set(["m4", "m5"]));
  });

  it("rootNodes returns nodes with no incoming edge", () => {
    const roots = rootNodes(tree).map((n) => n.scaffold_smiles);
    expect(new Set(roots)).toEqual(new Set(["c1ccccc1", NO_SCAFFOLD_SENTINEL]));
  });
});
```

- [ ] **Step 2: Run — expect failure**

- [ ] **Step 3: Implement**

```ts
// frontend/src/features/sar-analysis/lib/scaffold-tree-math.ts
import type { ScaffoldTreeNode, ScaffoldTreeResult } from "../types/scaffold-tree";

export function buildChildIndex(tree: ScaffoldTreeResult): Map<string, string[]> {
  const idx = new Map<string, string[]>();
  for (const e of tree.edges) {
    const arr = idx.get(e.parent_smiles) ?? [];
    arr.push(e.child_smiles);
    idx.set(e.parent_smiles, arr);
  }
  return idx;
}

export function collectSubtreeMolIds(
  scaffoldSmiles: string,
  tree: ScaffoldTreeResult,
): string[] {
  const byScaffold = new Map<string, ScaffoldTreeNode>(
    tree.nodes.map((n) => [n.scaffold_smiles, n]),
  );
  const children = buildChildIndex(tree);
  const visited = new Set<string>();
  const acc: string[] = [];
  const stack: string[] = [scaffoldSmiles];
  while (stack.length > 0) {
    const s = stack.pop()!;
    if (visited.has(s)) continue;
    visited.add(s);
    const node = byScaffold.get(s);
    if (node) acc.push(...node.molecule_ids);
    for (const c of children.get(s) ?? []) stack.push(c);
  }
  return acc;
}

export function rootNodes(tree: ScaffoldTreeResult): ScaffoldTreeNode[] {
  const hasParent = new Set<string>(tree.edges.map((e) => e.child_smiles));
  return tree.nodes.filter((n) => !hasParent.has(n.scaffold_smiles));
}
```

- [ ] **Step 4: Re-run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/sar-analysis/lib/scaffold-tree-math.ts \
        frontend/src/features/sar-analysis/lib/scaffold-tree-math.test.ts
git commit -m "feat(scaffold-tree): scaffold-tree-math — subtree + child-index helpers"
```

---

### Task 23: `scaffold-rollup.ts` — activity rollup

**Files:**
- Create: `frontend/src/features/sar-analysis/lib/scaffold-rollup.ts`
- Test: `frontend/src/features/sar-analysis/lib/scaffold-rollup.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/features/sar-analysis/lib/scaffold-rollup.test.ts
import { describe, it, expect } from "vitest";
import {
  medianPic50ForMols,
  classifyActivity,
  type ActivityRollupBin,
} from "./scaffold-rollup";

type ActivityData = Record<string, Record<string, { intercept_values?: { kind: string; level: number; value: number | null; qualifier: string }[] }>>;

describe("medianPic50ForMols", () => {
  const activity: ActivityData = {
    "m1": { "proto-A": { intercept_values: [{ kind: "ec", level: 50, value: 1e-6, qualifier: "=" }] } },
    "m2": { "proto-A": { intercept_values: [{ kind: "ec", level: 50, value: 1e-7, qualifier: "=" }] } },
    "m3": { "proto-A": { intercept_values: [{ kind: "ec", level: 50, value: null, qualifier: "nd" }] } },
    "m4": { "proto-A": { intercept_values: [{ kind: "ec", level: 50, value: 1e-8, qualifier: "=" }] } },
  };

  it("computes median of pIC50 values (excludes ND)", () => {
    const v = medianPic50ForMols(["m1", "m2", "m3", "m4"], activity as any, "proto-A");
    // pIC50s: 6, 7, 8 -> median 7
    expect(v).toBeCloseTo(7, 5);
  });

  it("returns null when no mols have data", () => {
    expect(medianPic50ForMols(["mX"], activity as any, "proto-A")).toBeNull();
  });

  it("returns null when all values are ND", () => {
    expect(medianPic50ForMols(["m3"], activity as any, "proto-A")).toBeNull();
  });
});

describe("classifyActivity", () => {
  it("classifies into 4 bins", () => {
    expect(classifyActivity(8.5)).toBe<"active_high">("active_high");
    expect(classifyActivity(7)).toBe<"active_mid">("active_mid");
    expect(classifyActivity(5.5)).toBe<"weak">("weak");
    expect(classifyActivity(4)).toBe<"inactive">("inactive");
    expect(classifyActivity(null)).toBeNull();
  });
});
```

- [ ] **Step 2: Run — expect failure**

- [ ] **Step 3: Implement**

```ts
// frontend/src/features/sar-analysis/lib/scaffold-rollup.ts
/**
 * Activity rollup for scaffold-tree node coloring.
 *
 * Reads each molecule's existing ActivityValue payload (returned from
 * useCollectionSearch), pulls the chosen protocol's pIC50/pEC50, and
 * computes a median across the subtree. ND values (qualifier "nd")
 * are excluded — they're not zero, they're "no determination".
 */

import type { ActivityValue } from "@/features/research-organization/types";

export type ActivityRollupBin = "active_high" | "active_mid" | "weak" | "inactive";

type ActivityDataMap = Record<string, Record<string, ActivityValue>>;

const PIC50_BINS: { threshold: number; bin: ActivityRollupBin }[] = [
  { threshold: 8.0, bin: "active_high" },
  { threshold: 6.0, bin: "active_mid" },
  { threshold: 5.0, bin: "weak" },
];

export function classifyActivity(pic50: number | null): ActivityRollupBin | null {
  if (pic50 === null || Number.isNaN(pic50)) return null;
  for (const { threshold, bin } of PIC50_BINS) {
    if (pic50 >= threshold) return bin;
  }
  return "inactive";
}

export function medianPic50ForMols(
  molIds: string[],
  activity: ActivityDataMap | undefined,
  protocolId: string,
): number | null {
  if (!activity) return null;
  const values: number[] = [];
  for (const mid of molIds) {
    const proto = activity[mid]?.[protocolId];
    if (!proto?.intercept_values) continue;
    for (const iv of proto.intercept_values) {
      if (iv.qualifier === "nd" || iv.value == null) continue;
      if (iv.value <= 0) continue;
      values.push(-Math.log10(iv.value));
    }
  }
  if (values.length === 0) return null;
  values.sort((a, b) => a - b);
  const mid = Math.floor(values.length / 2);
  return values.length % 2 === 0
    ? (values[mid - 1] + values[mid]) / 2
    : values[mid];
}
```

The `ActivityValue` import path matches the existing FE shape. If `intercept_values` lives under a different key, follow what `InterceptCell` uses.

- [ ] **Step 4: Re-run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/sar-analysis/lib/scaffold-rollup.ts \
        frontend/src/features/sar-analysis/lib/scaffold-rollup.test.ts
git commit -m "feat(scaffold-tree): scaffold-rollup — median pIC50 + 4-bin classification"
```

---

### Task 24: `useScaffoldTree` hook (sync + poll)

**Files:**
- Create: `frontend/src/features/sar-analysis/hooks/use-scaffold-tree.ts`
- Test: `frontend/src/features/sar-analysis/hooks/use-scaffold-tree.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/features/sar-analysis/hooks/use-scaffold-tree.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { useScaffoldTree } from "./use-scaffold-tree";

const wrapper = ({ children }: { children: React.ReactNode }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
};

describe("useScaffoldTree", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("returns tree directly when BE replies 200 with inline tree", async () => {
    const startMock = vi.fn(async () => ({
      tree: { nodes: [], edges: [], stats: { node_count: 0, elapsed_ms: 5, cache_hit: false } },
      job: null,
    }));
    const { result } = renderHook(
      () => useScaffoldTree({ moleculeIds: ["m1"], startFn: startMock }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.tree).toBeTruthy());
    expect(result.current.tree?.stats.cache_hit).toBe(false);
    expect(result.current.isPolling).toBe(false);
  });

  it("polls when BE replies 202 with job, then returns tree on ready", async () => {
    const startMock = vi.fn(async () => ({
      tree: null,
      job: { id: "job-1", status: "pending", ids_hash: "h", requested_at: "now" },
    }));
    let pollCount = 0;
    const pollMock = vi.fn(async () => {
      pollCount++;
      if (pollCount < 2) {
        return { id: "job-1", status: "running", ids_hash: "h", requested_at: "now" };
      }
      return {
        id: "job-1",
        status: "ready",
        ids_hash: "h",
        requested_at: "now",
        tree: { nodes: [], edges: [], stats: { node_count: 0, elapsed_ms: 50, cache_hit: false } },
      };
    });

    const { result } = renderHook(
      () =>
        useScaffoldTree({
          moleculeIds: ["m1", "m2"],
          startFn: startMock,
          pollFn: pollMock,
          pollIntervalMs: 10,
        }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.tree).toBeTruthy(), { timeout: 1000 });
    expect(pollMock).toHaveBeenCalled();
  });

  it("surfaces error on job failure", async () => {
    const startMock = vi.fn(async () => ({
      tree: null,
      job: { id: "job-2", status: "pending", ids_hash: "h", requested_at: "now" },
    }));
    const pollMock = vi.fn(async () => ({
      id: "job-2",
      status: "failed",
      ids_hash: "h",
      requested_at: "now",
      error_message: "boom",
    }));
    const { result } = renderHook(
      () =>
        useScaffoldTree({
          moleculeIds: ["m1"],
          startFn: startMock,
          pollFn: pollMock,
          pollIntervalMs: 10,
        }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.error).toBeTruthy(), { timeout: 1000 });
  });
});
```

- [ ] **Step 2: Run — expect failure**

- [ ] **Step 3: Implement**

```ts
// frontend/src/features/sar-analysis/hooks/use-scaffold-tree.ts
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import type {
  ScaffoldTreeJob,
  ScaffoldTreeResult,
  StartScaffoldTreeResponse,
} from "../types/scaffold-tree";

export type UseScaffoldTreeParams = {
  moleculeIds: string[];
  /** Override for tests — defaults to the orval-generated POST /scaffold-tree call. */
  startFn?: (mol_ids: string[]) => Promise<StartScaffoldTreeResponse>;
  /** Override for tests — defaults to the orval-generated GET /scaffold-tree/jobs/{id} call. */
  pollFn?: (job_id: string) => Promise<ScaffoldTreeJob>;
  pollIntervalMs?: number;
  enabled?: boolean;
};

export type UseScaffoldTreeReturn = {
  tree: ScaffoldTreeResult | null;
  jobId: string | null;
  isStarting: boolean;
  isPolling: boolean;
  error: Error | null;
};

const DEFAULT_POLL_MS = 1500;

function sortedKey(ids: string[]): string {
  return [...ids].sort().join(",");
}

export function useScaffoldTree(params: UseScaffoldTreeParams): UseScaffoldTreeReturn {
  const {
    moleculeIds,
    startFn = defaultStartFn,
    pollFn = defaultPollFn,
    pollIntervalMs = DEFAULT_POLL_MS,
    enabled = true,
  } = params;

  const key = useMemo(() => sortedKey(moleculeIds), [moleculeIds]);

  const start = useQuery({
    queryKey: ["scaffold-tree", "start", key],
    queryFn: () => startFn(moleculeIds),
    enabled: enabled && moleculeIds.length > 0,
    staleTime: 5 * 60_000,
  });

  const inlineTree = start.data?.tree ?? null;
  const job = start.data?.job ?? null;

  const [jobTreeResult, setJobTreeResult] = useState<ScaffoldTreeResult | null>(null);
  const [jobError, setJobError] = useState<Error | null>(null);

  useEffect(() => {
    if (!job || job.status === "ready" || job.status === "failed" || job.status === "cancelled") {
      return;
    }
    let cancelled = false;
    let attempts = 0;
    const tick = async () => {
      try {
        const status = await pollFn(job.id);
        if (cancelled) return;
        if (status.status === "ready" && status.tree) {
          setJobTreeResult(status.tree);
          return;
        }
        if (status.status === "failed") {
          setJobError(new Error(status.error_message ?? "scaffold tree compute failed"));
          return;
        }
        attempts++;
        const interval = attempts < 3 ? pollIntervalMs : pollIntervalMs * 2;
        window.setTimeout(tick, interval);
      } catch (e) {
        if (!cancelled) setJobError(e as Error);
      }
    };
    tick();
    return () => {
      cancelled = true;
    };
  }, [job, pollFn, pollIntervalMs]);

  return {
    tree: inlineTree ?? jobTreeResult,
    jobId: job?.id ?? null,
    isStarting: start.isPending,
    isPolling: job != null && jobTreeResult === null && jobError === null,
    error: jobError ?? (start.error as Error | null) ?? null,
  };
}

// The default implementations resolve at runtime to the orval-generated functions.
// Tests inject their own.
async function defaultStartFn(mol_ids: string[]): Promise<StartScaffoldTreeResponse> {
  const { startScaffoldTree } = await import("@/api/generated/scaffold-tree/scaffold-tree");
  const res = await startScaffoldTree({ molecule_ids: mol_ids });
  return res as unknown as StartScaffoldTreeResponse;
}

async function defaultPollFn(job_id: string): Promise<ScaffoldTreeJob> {
  const { getScaffoldTreeJob } = await import("@/api/generated/scaffold-tree/scaffold-tree");
  const res = await getScaffoldTreeJob(job_id);
  return res as unknown as ScaffoldTreeJob;
}
```

If orval generates different module / function names, adjust the dynamic imports. The injected `startFn` / `pollFn` parameters keep the unit tests insulated from generated code.

- [ ] **Step 4: Re-run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/sar-analysis/hooks/use-scaffold-tree.ts \
        frontend/src/features/sar-analysis/hooks/use-scaffold-tree.test.tsx
git commit -m "feat(scaffold-tree): useScaffoldTree — sync return + async poll"
```

---

### Task 25: `<ScaffoldColorPicker />`

**Files:**
- Create: `frontend/src/features/sar-analysis/components/scaffold-color-picker.tsx`
- Test: `frontend/src/features/sar-analysis/components/scaffold-color-picker.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/features/sar-analysis/components/scaffold-color-picker.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { ScaffoldColorPicker } from "./scaffold-color-picker";

describe("ScaffoldColorPicker", () => {
  it("renders 'none' label by default", () => {
    render(
      <ScaffoldColorPicker
        protocols={[{ id: "p1", name: "Mtb WCA" }]}
        value={null}
        onChange={() => {}}
      />,
    );
    expect(screen.getByText(/none/i)).toBeInTheDocument();
  });

  it("emits onChange when a protocol is picked", () => {
    const handle = vi.fn();
    render(
      <ScaffoldColorPicker
        protocols={[{ id: "p1", name: "Mtb WCA" }]}
        value={null}
        onChange={handle}
      />,
    );
    fireEvent.click(screen.getByRole("combobox"));
    fireEvent.click(screen.getByText("Mtb WCA"));
    expect(handle).toHaveBeenCalledWith("p1");
  });

  it("clears selection back to null via the 'none' option", () => {
    const handle = vi.fn();
    render(
      <ScaffoldColorPicker
        protocols={[{ id: "p1", name: "Mtb WCA" }]}
        value="p1"
        onChange={handle}
      />,
    );
    fireEvent.click(screen.getByRole("combobox"));
    fireEvent.click(screen.getByText(/none/i));
    expect(handle).toHaveBeenCalledWith(null);
  });
});
```

- [ ] **Step 2: Run — expect failure**

- [ ] **Step 3: Implement**

```tsx
// frontend/src/features/sar-analysis/components/scaffold-color-picker.tsx
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";

export type ScaffoldColorProtocol = { id: string; name: string };

type Props = {
  protocols: ScaffoldColorProtocol[];
  value: string | null;
  onChange: (value: string | null) => void;
};

const NONE = "__none__";

export function ScaffoldColorPicker({ protocols, value, onChange }: Props) {
  return (
    <Select
      value={value ?? NONE}
      onValueChange={(v) => onChange(v === NONE ? null : v)}
    >
      <SelectTrigger className="w-full max-w-[240px]">
        <SelectValue placeholder="— none —" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>— none —</SelectItem>
        {protocols.map((p) => (
          <SelectItem key={p.id} value={p.id}>
            {p.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
```

- [ ] **Step 4: Re-run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/sar-analysis/components/scaffold-color-picker.tsx \
        frontend/src/features/sar-analysis/components/scaffold-color-picker.test.tsx
git commit -m "feat(scaffold-tree): ScaffoldColorPicker dropdown"
```

---

### Task 26: `<ScaffoldTreeNode />` (recursive)

**Files:**
- Create: `frontend/src/features/sar-analysis/components/scaffold-tree-node.tsx`
- Test: `frontend/src/features/sar-analysis/components/scaffold-tree-node.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/features/sar-analysis/components/scaffold-tree-node.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { ScaffoldTreeNode } from "./scaffold-tree-node";
import { NO_SCAFFOLD_SENTINEL } from "../types/scaffold-tree";

const tree = {
  nodes: [
    { scaffold_smiles: "c1ccccc1", molecule_ids: ["m1"], molecule_count: 1, subtree_molecule_count: 2 },
    { scaffold_smiles: "c1ccc2ccccc2c1", molecule_ids: ["m2"], molecule_count: 1, subtree_molecule_count: 1 },
  ],
  edges: [{ parent_smiles: "c1ccccc1", child_smiles: "c1ccc2ccccc2c1" }],
  stats: { node_count: 2, elapsed_ms: 0, cache_hit: false },
};

describe("ScaffoldTreeNode", () => {
  it("renders subtree count when greater than own count", () => {
    render(
      <ScaffoldTreeNode
        scaffoldSmiles="c1ccccc1"
        tree={tree}
        depth={0}
        expanded={new Set()}
        selected={null}
        onToggle={() => {}}
        onSelect={() => {}}
        colorByProtocolId={null}
        activity={undefined}
      />,
    );
    expect(screen.getByText(/1 · 2/)).toBeInTheDocument();
  });

  it("emits onSelect with scaffold smiles on click", () => {
    const handle = vi.fn();
    render(
      <ScaffoldTreeNode
        scaffoldSmiles="c1ccccc1"
        tree={tree}
        depth={0}
        expanded={new Set()}
        selected={null}
        onToggle={() => {}}
        onSelect={handle}
        colorByProtocolId={null}
        activity={undefined}
      />,
    );
    fireEvent.click(screen.getByTestId("scaffold-node-c1ccccc1"));
    expect(handle).toHaveBeenCalledWith("c1ccccc1");
  });

  it("renders 'no scaffold' label for the sentinel bucket", () => {
    const treeWithBucket = {
      ...tree,
      nodes: [
        ...tree.nodes,
        { scaffold_smiles: NO_SCAFFOLD_SENTINEL, molecule_ids: ["m3"], molecule_count: 1, subtree_molecule_count: 1 },
      ],
    };
    render(
      <ScaffoldTreeNode
        scaffoldSmiles={NO_SCAFFOLD_SENTINEL}
        tree={treeWithBucket}
        depth={0}
        expanded={new Set()}
        selected={null}
        onToggle={() => {}}
        onSelect={() => {}}
        colorByProtocolId={null}
        activity={undefined}
      />,
    );
    expect(screen.getByText(/no scaffold/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run — expect failure**

- [ ] **Step 3: Implement**

```tsx
// frontend/src/features/sar-analysis/components/scaffold-tree-node.tsx
import { ChevronDown, ChevronRight } from "lucide-react";

import { cn } from "@/shared/lib/utils";
import { MoleculeThumbnail } from "@/features/chemical-registration/components/molecule-thumbnail";  // adjust to existing path

import {
  NO_SCAFFOLD_SENTINEL,
  type ScaffoldTreeResult,
} from "../types/scaffold-tree";
import { buildChildIndex, collectSubtreeMolIds } from "../lib/scaffold-tree-math";
import { classifyActivity, medianPic50ForMols } from "../lib/scaffold-rollup";

type Props = {
  scaffoldSmiles: string;
  tree: ScaffoldTreeResult;
  depth: number;
  expanded: Set<string>;
  selected: string | null;
  onToggle: (scaffoldSmiles: string) => void;
  onSelect: (scaffoldSmiles: string) => void;
  colorByProtocolId: string | null;
  activity: Record<string, Record<string, any>> | undefined;
};

const BIN_COLORS: Record<string, string> = {
  active_high: "bg-emerald-500",
  active_mid: "bg-amber-400",
  weak: "bg-orange-400",
  inactive: "bg-rose-400",
};

export function ScaffoldTreeNode(props: Props) {
  const {
    scaffoldSmiles, tree, depth, expanded, selected,
    onToggle, onSelect, colorByProtocolId, activity,
  } = props;
  const node = tree.nodes.find((n) => n.scaffold_smiles === scaffoldSmiles);
  if (!node) return null;

  const children = buildChildIndex(tree).get(scaffoldSmiles) ?? [];
  const isExpanded = expanded.has(scaffoldSmiles);
  const isSelected = selected === scaffoldSmiles;
  const isBucket = scaffoldSmiles === NO_SCAFFOLD_SENTINEL;

  let colorBin: string | null = null;
  if (colorByProtocolId && activity) {
    const ids = collectSubtreeMolIds(scaffoldSmiles, tree);
    colorBin = classifyActivity(medianPic50ForMols(ids, activity, colorByProtocolId));
  }

  return (
    <div className="flex flex-col">
      <div
        data-testid={`scaffold-node-${scaffoldSmiles}`}
        onClick={() => onSelect(scaffoldSmiles)}
        className={cn(
          "flex items-center gap-2 rounded px-2 py-1 cursor-pointer hover:bg-muted",
          isSelected && "bg-muted",
        )}
        style={{ paddingLeft: `${8 + depth * 16}px` }}
      >
        {children.length > 0 ? (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onToggle(scaffoldSmiles); }}
            className="text-muted-foreground"
            aria-label={isExpanded ? "collapse" : "expand"}
          >
            {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </button>
        ) : (
          <span className="inline-block w-3" aria-hidden />
        )}

        {isBucket ? (
          <span className="text-xs italic text-muted-foreground w-14">no scaffold</span>
        ) : (
          <MoleculeThumbnail smiles={scaffoldSmiles} size="sm" />
        )}

        <span className="text-xs font-mono truncate flex-1">
          {isBucket ? "—" : scaffoldSmiles}
        </span>
        <span className="text-xs tabular-nums text-muted-foreground">
          {node.molecule_count === node.subtree_molecule_count
            ? node.molecule_count
            : `${node.molecule_count} · ${node.subtree_molecule_count}`}
        </span>
        {colorBin && (
          <span
            aria-label={`activity ${colorBin}`}
            className={cn("h-1.5 w-6 rounded", BIN_COLORS[colorBin])}
          />
        )}
      </div>

      {isExpanded && children.length > 0 && (
        <div>
          {children.map((c) => (
            <ScaffoldTreeNode
              key={c}
              scaffoldSmiles={c}
              tree={tree}
              depth={depth + 1}
              expanded={expanded}
              selected={selected}
              onToggle={onToggle}
              onSelect={onSelect}
              colorByProtocolId={colorByProtocolId}
              activity={activity}
            />
          ))}
        </div>
      )}
    </div>
  );
}
```

If `MoleculeThumbnail`'s import path / size enum differs from what's here, fix to match. The component must render visibly in jsdom (the test relies on `getByText` finding the count).

- [ ] **Step 4: Re-run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/sar-analysis/components/scaffold-tree-node.tsx \
        frontend/src/features/sar-analysis/components/scaffold-tree-node.test.tsx
git commit -m "feat(scaffold-tree): recursive ScaffoldTreeNode component"
```

---

### Task 27: `<ScaffoldTreeView />` (split-pane composition)

**Files:**
- Create: `frontend/src/features/sar-analysis/components/scaffold-tree-view.tsx`
- Test: `frontend/src/features/sar-analysis/components/scaffold-tree-view.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/features/sar-analysis/components/scaffold-tree-view.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { ScaffoldTreeView } from "./scaffold-tree-view";

vi.mock("../hooks/use-scaffold-tree", () => ({
  useScaffoldTree: () => ({
    tree: {
      nodes: [
        { scaffold_smiles: "c1ccccc1", molecule_ids: ["m1", "m2"], molecule_count: 2, subtree_molecule_count: 3 },
        { scaffold_smiles: "c1ccc2ccccc2c1", molecule_ids: ["m3"], molecule_count: 1, subtree_molecule_count: 1 },
      ],
      edges: [{ parent_smiles: "c1ccccc1", child_smiles: "c1ccc2ccccc2c1" }],
      stats: { node_count: 2, elapsed_ms: 5, cache_hit: false },
    },
    jobId: null,
    isStarting: false,
    isPolling: false,
    error: null,
  }),
}));

// Mock CardGrid so the test focuses on tree behavior
vi.mock("@/features/research-organization/components/results/card-grid", () => ({
  CardGrid: ({ molecules }: any) => (
    <div data-testid="card-grid">{molecules.length} cards</div>
  ),
}));

const wrapper = ({ children }: any) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
};

const molecules = [
  { id: "m1", bemis_murcko_smiles: "c1ccccc1", structure: { smiles: "..." } } as any,
  { id: "m2", bemis_murcko_smiles: "c1ccccc1", structure: { smiles: "..." } } as any,
  { id: "m3", bemis_murcko_smiles: "c1ccc2ccccc2c1", structure: { smiles: "..." } } as any,
];

describe("ScaffoldTreeView", () => {
  it("renders the tree with first-level nodes", async () => {
    render(
      <ScaffoldTreeView
        molecules={molecules}
        activityData={{}}
        aggregationRule={"latest_approved_run" as any}
      />,
      { wrapper },
    );
    await waitFor(() => expect(screen.getByTestId("scaffold-node-c1ccccc1")).toBeInTheDocument());
  });

  it("right pane shows all molecules when no node selected", async () => {
    render(
      <ScaffoldTreeView
        molecules={molecules}
        activityData={{}}
        aggregationRule={"latest_approved_run" as any}
      />,
      { wrapper },
    );
    await waitFor(() => expect(screen.getByTestId("card-grid")).toHaveTextContent("3 cards"));
  });

  it("right pane filters to selected node's subtree on click", async () => {
    render(
      <ScaffoldTreeView
        molecules={molecules}
        activityData={{}}
        aggregationRule={"latest_approved_run" as any}
      />,
      { wrapper },
    );
    // benzene has subtree of 3 (itself + naphthalene); click selects the subtree
    fireEvent.click(await screen.findByTestId("scaffold-node-c1ccccc1"));
    await waitFor(() => expect(screen.getByTestId("card-grid")).toHaveTextContent("3 cards"));
  });
});
```

- [ ] **Step 2: Run — expect failure**

- [ ] **Step 3: Implement**

```tsx
// frontend/src/features/sar-analysis/components/scaffold-tree-view.tsx
import { useMemo, useState, useEffect } from "react";

import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/shared/components/ui/resizable";
import { CardGrid } from "@/features/research-organization/components/results/card-grid";

import { useScaffoldTree } from "../hooks/use-scaffold-tree";
import { ScaffoldTreeNode } from "./scaffold-tree-node";
import { ScaffoldColorPicker } from "./scaffold-color-picker";
import { collectSubtreeMolIds, rootNodes } from "../lib/scaffold-tree-math";

// Adjust import paths to match the existing types module
import type { Molecule } from "@/features/chemical-registration/types";
import type { ActivityValue } from "@/features/research-organization/types";

type Props = {
  molecules: Molecule[];
  activityData: Record<string, Record<string, ActivityValue>>;
  aggregationRule: unknown; // pass-through; consumed by upstream rollup
};

const STORAGE_KEY = "scaffoldTreePaneWidth";
const DEFAULT_WIDTH_PCT = 30;

export function ScaffoldTreeView({ molecules, activityData }: Props) {
  const moleculeIds = useMemo(() => molecules.map((m) => m.id), [molecules]);
  const { tree, isStarting, isPolling, error } = useScaffoldTree({ moleculeIds });

  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selectedScaffold, setSelectedScaffold] = useState<string | null>(null);
  const [colorBy, setColorBy] = useState<string | null>(null);

  useEffect(() => {
    if (tree?.nodes.length) {
      const roots = rootNodes(tree).map((n) => n.scaffold_smiles);
      setExpanded(new Set(roots));
    }
  }, [tree]);

  const filteredMolecules = useMemo(() => {
    if (!tree || selectedScaffold == null) return molecules;
    const ids = new Set(collectSubtreeMolIds(selectedScaffold, tree));
    return molecules.filter((m) => ids.has(m.id));
  }, [molecules, tree, selectedScaffold]);

  const protocolOptions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const perMol of Object.values(activityData ?? {})) {
      for (const protocolId of Object.keys(perMol ?? {})) {
        if (!seen.has(protocolId)) {
          seen.set(protocolId, protocolId); // we don't have names here; consumer can map
        }
      }
    }
    return [...seen.entries()].map(([id, name]) => ({ id, name }));
  }, [activityData]);

  if (error) {
    return (
      <div className="p-6 text-sm text-rose-600">
        Scaffold tree failed to load: {error.message}
      </div>
    );
  }

  if (isStarting || (isPolling && !tree)) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        Computing scaffold tree…
      </div>
    );
  }

  if (!tree || tree.nodes.length === 0) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        {molecules.length === 0
          ? "Add molecules to see the scaffold tree."
          : "These molecules are all acyclic — no scaffolds to display."}
      </div>
    );
  }

  const roots = rootNodes(tree);

  return (
    <ResizablePanelGroup direction="horizontal" className="h-full">
      <ResizablePanel defaultSize={DEFAULT_WIDTH_PCT} minSize={20} maxSize={50}>
        <div className="flex flex-col h-full">
          <div className="p-2 border-b">
            <ScaffoldColorPicker
              protocols={protocolOptions}
              value={colorBy}
              onChange={setColorBy}
            />
          </div>
          <div className="flex-1 overflow-y-auto p-1">
            {roots.map((root) => (
              <ScaffoldTreeNode
                key={root.scaffold_smiles}
                scaffoldSmiles={root.scaffold_smiles}
                tree={tree}
                depth={0}
                expanded={expanded}
                selected={selectedScaffold}
                onToggle={(s) =>
                  setExpanded((prev) => {
                    const next = new Set(prev);
                    if (next.has(s)) next.delete(s);
                    else next.add(s);
                    return next;
                  })
                }
                onSelect={(s) => setSelectedScaffold((prev) => (prev === s ? null : s))}
                colorByProtocolId={colorBy}
                activity={activityData}
              />
            ))}
          </div>
        </div>
      </ResizablePanel>
      <ResizableHandle />
      <ResizablePanel defaultSize={100 - DEFAULT_WIDTH_PCT}>
        <div className="h-full overflow-auto">
          <CardGrid molecules={filteredMolecules} />
        </div>
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}
```

`CardGrid`'s actual prop shape may include more than `molecules` (e.g. selection callbacks). Pass through whatever the existing call site in `ResultsSurface` uses — copy its prop shape.

- [ ] **Step 4: Re-run — expect pass**

```bash
cd frontend && pnpm vitest run src/features/sar-analysis/components/scaffold-tree-view.test.tsx
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/sar-analysis/components/scaffold-tree-view.tsx \
        frontend/src/features/sar-analysis/components/scaffold-tree-view.test.tsx
git commit -m "feat(scaffold-tree): ScaffoldTreeView split-pane composition"
```

---

### Task 28: Wire third view mode into `ResultsSurface` + toggle + URL

**Files:**
- Modify: `frontend/src/features/research-organization/lib/use-view-mode.ts`
- Modify: `frontend/src/features/research-organization/components/results/view-mode-toggle.tsx`
- Modify: `frontend/src/features/research-organization/components/results/results-surface.tsx`
- Test: `frontend/src/features/research-organization/lib/use-view-mode.test.ts` (extend)
- Test: `frontend/src/features/research-organization/components/results/view-mode-toggle.test.tsx` (extend)

- [ ] **Step 1: Extend the existing tests**

In `use-view-mode.test.ts`, add:

```ts
it("accepts 'scaffold-tree' as a valid mode", () => {
  // Use the existing harness; replace existing `cards`/`table` test pattern
  const { result } = renderHook(() => useViewMode());
  act(() => result.current.setMode("scaffold-tree"));
  expect(result.current.mode).toBe("scaffold-tree");
});

it("URL form for scaffold-tree is 'tree'", () => {
  // Mirror the existing URL serialization test
  const url = serializeViewMode("scaffold-tree");
  expect(url).toBe("tree");
  expect(parseViewMode("tree")).toBe("scaffold-tree");
});
```

In `view-mode-toggle.test.tsx`, add:

```tsx
it("renders a 'tree' segment", () => {
  render(<ViewModeToggle mode="cards" onModeChange={() => {}} />);
  expect(screen.getByRole("button", { name: /tree/i })).toBeInTheDocument();
});

it("emits 'scaffold-tree' on tree-segment click", () => {
  const handle = vi.fn();
  render(<ViewModeToggle mode="cards" onModeChange={handle} />);
  fireEvent.click(screen.getByRole("button", { name: /tree/i }));
  expect(handle).toHaveBeenCalledWith("scaffold-tree");
});
```

- [ ] **Step 2: Run — expect failure**

- [ ] **Step 3: Implement**

In `use-view-mode.ts`:

```ts
// Replace existing ViewMode union
export type ViewMode = "table" | "cards" | "scaffold-tree";

const URL_TO_MODE: Record<string, ViewMode> = {
  table: "table",
  cards: "cards",
  tree: "scaffold-tree",
};

const MODE_TO_URL: Record<ViewMode, string> = {
  table: "table",
  cards: "cards",
  "scaffold-tree": "tree",
};

export function parseViewMode(input: string | null): ViewMode {
  if (input && input in URL_TO_MODE) return URL_TO_MODE[input];
  return "cards";  // unchanged default
}

export function serializeViewMode(mode: ViewMode): string {
  return MODE_TO_URL[mode];
}
```

(Keep the rest of `useViewMode` untouched — only the union + lookup tables move.)

In `view-mode-toggle.tsx` — add a third segment:

```tsx
<Button
  variant={mode === "scaffold-tree" ? "default" : "ghost"}
  size="sm"
  onClick={() => onModeChange("scaffold-tree")}
  aria-label="tree view"
>
  <GitForkIcon className="h-4 w-4" />
  <span className="ml-1 hidden sm:inline">tree</span>
</Button>
```

(Use whichever shadcn segmented-control primitive is currently in use. If the toggle uses a single `Tabs` / `ToggleGroup`, just add a third `<TabsTrigger value="scaffold-tree">tree</TabsTrigger>`.)

In `results-surface.tsx` — add the third branch:

```tsx
import { ScaffoldTreeView } from "@/features/sar-analysis/components/scaffold-tree-view";

// ... inside the existing switch / conditional ...
if (mode === "scaffold-tree") {
  return (
    <ScaffoldTreeView
      molecules={molecules}
      activityData={activityData}
      aggregationRule={aggregationRule}
    />
  );
}
```

The `activityData` + `aggregationRule` props flow in from `CollectionDetail` (which already receives them via `useCollectionSearch` + `AggregationControl`). If `ResultsSurface` doesn't currently take them, add the props and pass them through at the call site in `collection-detail.tsx`.

- [ ] **Step 4: Re-run — expect pass**

```bash
cd frontend && pnpm vitest run src/features/research-organization/lib/use-view-mode.test.ts
cd frontend && pnpm vitest run src/features/research-organization/components/results/view-mode-toggle.test.tsx
cd frontend && pnpm exec tsc --noEmit
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/research-organization/lib/use-view-mode.ts \
        frontend/src/features/research-organization/components/results/view-mode-toggle.tsx \
        frontend/src/features/research-organization/components/results/results-surface.tsx \
        frontend/src/features/research-organization/components/collection-detail.tsx \
        frontend/src/features/research-organization/lib/use-view-mode.test.ts \
        frontend/src/features/research-organization/components/results/view-mode-toggle.test.tsx
git commit -m "feat(scaffold-tree): wire scaffold-tree view-mode into ResultsSurface + toggle"
```

---

## Manual smoke checklist (run after Task 28)

| # | Scenario | Expected |
|---|---|---|
| 1 | Apply migrations 037 + 038 (`uv run alembic upgrade head`) | clean upgrade, both new tables/columns present |
| 2 | Register a new molecule via API | row has non-NULL `bemis_murcko_smiles` |
| 3 | Run `backfill_bemis_murcko.py` on a dev DB with some NULL rows | log shows N processed; subsequent run shows 0 processed |
| 4 | Open `/collections/{id}` with ≥10 ringed mols | view-mode toggle shows three segments; default still `cards` |
| 5 | Switch to tree view | URL gains `?view=tree`; left pane renders tree; right pane shows all mols via CardGrid |
| 6 | Click a leaf scaffold node | right pane filters to that one mol |
| 7 | Click an inner node | right pane shows subtree members (count matches `subtree_molecule_count`) |
| 8 | Pick a protocol from the color-by dropdown | tree nodes show color bands; nodes with no data show no band |
| 9 | Switch to a different protocol | bands re-color; no flash to "Computing…" |
| 10 | Switch back to cards view | URL drops `?view=tree`; CardGrid renders intact |
| 11 | Open a >500-mol collection in tree view | "Computing scaffold tree…" caption; result appears within ~30s; subsequent reload is instant (cache hit) |
| 12 | Refresh the page | tree re-renders from cache (<200 ms) |
| 13 | Add a molecule to the collection, re-open tree view | new request (different `ids_hash`) → recompute |
| 14 | Open a collection of only acyclic compounds | tree shows the single "no scaffold" bucket; right pane has all mols |
| 15 | Drag the resizable divider | left pane resizes; persists across reload via localStorage |

---

## Open implementation questions (deferred to the executor)

1. **Lagom `SessionFactory` name:** the DI wiring task uses `c[SessionFactory]` as a placeholder. Look at how the export pipeline's `_export.py` resolves its session and copy.
2. **Temporal client provider name:** ditto — copy from `_temporal.py` or wherever the export's `TemporalExportOrchestrator` resolves its client.
3. **`MoleculeThumbnail` size enum:** Task 26 assumes `size="sm"`. If the existing primitive uses different size tokens, use the smallest one that renders ≥56×56.
4. **`CardGrid` extra props:** Task 27 passes only `molecules`. Confirm via `results-surface.tsx`'s existing call site whether selection state needs threading through.
5. **`MoleculeFetcher.fetch_for_scaffold_tree` placement:** sits naturally as a new method on the existing `SQLAlchemyMoleculeRepository`. If the repo already has a similar bulk-fetch helper, add `fetch_for_scaffold_tree` next to it rather than introducing a new method type.

---

## Post-shipping follow-ups (NOT in this plan)

These are explicitly out of scope per the spec:

- Precompute scaffold trees on collection-membership change (Temporal event handler).
- Scaffold filter row in `SearchQueryBuilder`.
- Scaffold chip on `MoleculeCard`.
- Move cache layer to Valkey once another feature needs it.
- Hoist view-mode toggle + scaffold tree onto standalone `/search`.
- **Sonner toast upgrade after 3s of async computing** — `ScaffoldTreeView` currently renders an inline "Computing scaffold tree…" caption. The spec calls for upgrading to a `ExportJobToast`-style Sonner toast with an elapsed counter and a Cancel button after 3s of waiting. Solves the UX for big collections where the chemist might want to leave the tab.
