# Auto-sync molecule synonyms → batch identifier mirrors — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Materialize a `BatchIdentifier` for every `(MoleculeIdentifier × Batch)` pair of a molecule, with `identifier = f"{synonym}-{suffix}"` where suffix comes from the batch's hyphenated tail. Mirrors live + die alongside their parent synonym via a nullable FK with `ON DELETE CASCADE`.

**Architecture:** New FK column `batch_identifiers.derived_from_molecule_identifier_id` (NULL = chemist-added, non-NULL = auto-mirror). A stateless `SyncBatchIdentifierMirrors` collaborator (in `application/inventory/`) fans out on `AddIdentifier`, `CreateBatch`, and `EnsureBatchExists`. `RemoveIdentifier` needs no code — DB cascade handles it. Conflict-skip semantics: workspace-unique conflicts and same-string-on-batch are logged + returned to the caller as `MirrorSummary` for toast UX; the parent action always succeeds.

**Tech Stack:** Python 3.13 / SQLAlchemy 2.0 async / Alembic / FastAPI / dry-python returns / Lagom DI / Next.js 16 / React 19 / TanStack Query v5 / Sonner / Vitest.

**Spec:** `docs/superpowers/specs/2026-05-22-auto-sync-batch-identifier-mirrors-design.md`.

---

## Task 1: Migration 044 — FK column + cascade + partial index

**Files:**
- Create: `backend/alembic/versions/044_auto_mirror_fk_on_batch_identifiers.py`

- [ ] **Step 1: Write migration file**

```python
"""044 — auto-mirror FK on batch_identifiers.

Adds nullable FK from batch_identifiers to molecule_identifiers so that
synonyms registered on a Molecule can fan out a parallel BatchIdentifier
per batch. ON DELETE CASCADE means removing a MoleculeIdentifier
automatically removes its derived mirrors.

NULL on this column = chemist-added BatchIdentifier (untouched by sync).
Non-NULL = auto-mirror keyed to a specific MoleculeIdentifier.

Revision ID: 044_auto_mirror_fk_on_batch_identifiers
Revises: 043_batch_identifiers
Create Date: 2026-05-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "044_auto_mirror_fk_on_batch_identifiers"
down_revision: str | None = "043_batch_identifiers"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.add_column(
        "batch_identifiers",
        sa.Column(
            "derived_from_molecule_identifier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("molecule_identifiers.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_batch_identifiers_derived_from",
        "batch_identifiers",
        ["derived_from_molecule_identifier_id"],
        postgresql_where=sa.text("derived_from_molecule_identifier_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_batch_identifiers_derived_from", table_name="batch_identifiers")
    op.drop_column("batch_identifiers", "derived_from_molecule_identifier_id")
```

- [ ] **Step 2: Apply migration locally**

Run: `cd backend && uv run alembic upgrade head`
Expected: `INFO ... Running upgrade 043_batch_identifiers -> 044_auto_mirror_fk_on_batch_identifiers`

- [ ] **Step 3: Verify column + index exist + downgrade cleanly**

Run:
```bash
cd backend && uv run python -c "
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from cellar.infrastructure.persistence.settings import DatabaseSettings
async def main():
    eng = create_async_engine(DatabaseSettings().url, echo=False)
    async with eng.connect() as conn:
        r = await conn.execute(text('SELECT column_name FROM information_schema.columns WHERE table_name=\\'batch_identifiers\\' AND column_name=\\'derived_from_molecule_identifier_id\\''))
        print('column:', r.scalar_one_or_none())
        r = await conn.execute(text('SELECT indexname FROM pg_indexes WHERE indexname=\\'idx_batch_identifiers_derived_from\\''))
        print('index:', r.scalar_one_or_none())
asyncio.run(main())
"
```
Expected: prints `column: derived_from_molecule_identifier_id` and `index: idx_batch_identifiers_derived_from`.

Then verify downgrade + reapply round-trip:
```bash
cd backend && uv run alembic downgrade -1 && uv run alembic upgrade head
```
Expected: both run cleanly with no errors.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/044_auto_mirror_fk_on_batch_identifiers.py
git commit -m "feat(migration): 044 — auto-mirror FK on batch_identifiers"
```

---

## Task 2: Domain entity — `BatchIdentifier.derived_from_molecule_identifier_id`

**Files:**
- Modify: `backend/src/cellar/domain/inventory/batch_identifier.py`
- Create: `backend/tests/unit/domain/inventory/test_batch_identifier.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/unit/domain/inventory/test_batch_identifier.py` (if the file already exists, append):

```python
"""Unit tests for BatchIdentifier domain entity."""

from __future__ import annotations

import uuid

from cellar.domain.inventory.batch_identifier import BatchIdentifier


def test_create_accepts_derived_from_molecule_identifier_id():
    batch_id = uuid.uuid4()
    mol_ident_id = uuid.uuid4()
    actor = uuid.uuid4()

    bi = BatchIdentifier.create(
        batch_id=batch_id,
        identifier="SACC-0036913-001",
        identifier_type="custom",
        source="compound-syn",
        registered_by=actor,
        derived_from_molecule_identifier_id=mol_ident_id,
    )

    assert bi.derived_from_molecule_identifier_id == mol_ident_id


def test_create_defaults_derived_from_to_none():
    bi = BatchIdentifier.create(
        batch_id=uuid.uuid4(),
        identifier="LOT-001",
        identifier_type="external_lot",
        source="chemist input",
        registered_by=uuid.uuid4(),
    )

    assert bi.derived_from_molecule_identifier_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/domain/inventory/test_batch_identifier.py -v`
Expected: FAIL with `TypeError: create() got an unexpected keyword argument 'derived_from_molecule_identifier_id'`.

- [ ] **Step 3: Add field to entity**

In `backend/src/cellar/domain/inventory/batch_identifier.py`, modify `__init__` and `create()`:

```python
class BatchIdentifier(Entity):
    """An external identifier mapped to a batch. Fully owned by the parent Batch."""

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        batch_id: uuid.UUID,
        identifier: str,
        identifier_type: str,
        source: str,
        registered_by: uuid.UUID,
        derived_from_molecule_identifier_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        if not identifier or not identifier.strip():
            raise ValidationError("Identifier must not be empty")
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)
        self.batch_id = batch_id
        self.identifier = identifier.strip()
        self.identifier_type = identifier_type
        self.source = source
        self.registered_by = registered_by
        self.derived_from_molecule_identifier_id = derived_from_molecule_identifier_id

    @classmethod
    def create(
        cls,
        *,
        batch_id: uuid.UUID,
        identifier: str,
        identifier_type: str,
        source: str,
        registered_by: uuid.UUID,
        derived_from_molecule_identifier_id: uuid.UUID | None = None,
    ) -> BatchIdentifier:
        return cls(
            batch_id=batch_id,
            identifier=identifier,
            identifier_type=identifier_type,
            source=source,
            registered_by=registered_by,
            derived_from_molecule_identifier_id=derived_from_molecule_identifier_id,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/domain/inventory/test_batch_identifier.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/domain/inventory/batch_identifier.py backend/tests/unit/domain/inventory/test_batch_identifier.py
git commit -m "feat(domain): BatchIdentifier.derived_from_molecule_identifier_id"
```

---

## Task 3: Persistence model + repo round-trip

**Files:**
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/models.py:82-98`
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/batch_repository.py:226-272` (`_to_domain`) and `:359-369` (`_ident_to_model`)
- Create: `backend/tests/integration/inventory/test_batch_identifier_persistence.py`

- [ ] **Step 1: Write failing integration test**

Create `backend/tests/integration/inventory/test_batch_identifier_persistence.py`:

```python
"""Integration: BatchIdentifier round-trips derived_from_molecule_identifier_id."""

from __future__ import annotations

import uuid
import pytest

from cellar.domain.inventory.batch import Batch
from cellar.domain.inventory.batch_identifier import BatchIdentifier
from cellar.domain.inventory.enums import BatchSource
from cellar.domain.shared.value_objects import Amount, AmountUnit, BatchNumber
from cellar.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


@pytest.mark.asyncio
async def test_round_trips_derived_from_fk(sessionmaker, seeded_workspace_and_molecule):
    workspace_id, molecule_id, mol_ident_id, actor = seeded_workspace_and_molecule

    uow = AsyncUnitOfWork(sessionmaker)
    repo = SQLAlchemyBatchRepository(uow)

    async with uow:
        batch = Batch.create(
            workspace_id=workspace_id,
            molecule_id=molecule_id,
            batch_number=BatchNumber(value="CC-000001-001"),
            amount=Amount(value=10.0, unit=AmountUnit.MG),
            source=BatchSource.IN_HOUSE,
            chemist=actor,
        )
        mirror = BatchIdentifier.create(
            batch_id=batch.id,
            identifier="SACC-0001-001",
            identifier_type="custom",
            source="compound-syn",
            registered_by=actor,
            derived_from_molecule_identifier_id=mol_ident_id,
        )
        manual = BatchIdentifier.create(
            batch_id=batch.id,
            identifier="VENDOR-LOT-Z9",
            identifier_type="external_lot",
            source="chemist input",
            registered_by=actor,
        )
        batch.identifiers.extend([mirror, manual])
        await repo.save(batch)
        await uow.commit()

    uow2 = AsyncUnitOfWork(sessionmaker)
    repo2 = SQLAlchemyBatchRepository(uow2)
    async with uow2:
        loaded = await repo2.find_by_id_in_workspace(workspace_id, batch.id)

    assert loaded is not None
    by_str = {i.identifier: i for i in loaded.identifiers}
    assert by_str["SACC-0001-001"].derived_from_molecule_identifier_id == mol_ident_id
    assert by_str["VENDOR-LOT-Z9"].derived_from_molecule_identifier_id is None
```

If the fixture `seeded_workspace_and_molecule` doesn't exist, add it to the nearest `conftest.py` (likely `backend/tests/integration/inventory/conftest.py`):

```python
import uuid
import pytest

from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from cellar.domain.shared.value_objects import ChemicalStructure, RegistrationNumber
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


@pytest.fixture
async def seeded_workspace_and_molecule(sessionmaker):
    workspace_id = uuid.uuid4()
    actor = uuid.uuid4()
    uow = AsyncUnitOfWork(sessionmaker)
    repo = SQLAlchemyMoleculeRepository(uow)
    async with uow:
        mol = Molecule.create(
            workspace_id=workspace_id,
            registration_number=RegistrationNumber(value="CC-000001"),
            name="SACC-0001",
            structure=ChemicalStructure(
                inchi="InChI=1S/CH4/h1H4",
                inchi_key="VNWKTOKETHGBQD-UHFFFAOYSA-N",
                canonical_smiles="C",
                molecular_formula="CH4",
                molecular_weight=16.04,
            ),
            registered_by=actor,
        )
        ident = MoleculeIdentifier.create(
            molecule_id=mol.id,
            identifier="SACC-0001",
            identifier_type="custom",
            source="Registration",
            registered_by=actor,
        )
        mol.add_identifier(ident)
        await repo.save(mol)
        await uow.commit()
    return workspace_id, mol.id, ident.id, actor
```

- [ ] **Step 2: Run integration test to verify it fails**

Run: `cd backend && uv run pytest tests/integration/inventory/test_batch_identifier_persistence.py -v`
Expected: FAIL — either `AttributeError: 'BatchIdentifierModel' object has no attribute 'derived_from_molecule_identifier_id'` or the round-trip returns `None` for the FK.

- [ ] **Step 3: Add column to model**

In `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/models.py`, modify `BatchIdentifierModel`:

```python
class BatchIdentifierModel(Base, EntityModelMixin):
    """External/foreign identifiers mapped to a batch."""

    __tablename__ = "batch_identifiers"

    batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("batches.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    identifier_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    registered_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    derived_from_molecule_identifier_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("molecule_identifiers.id", ondelete="CASCADE"),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "identifier", name="uq_batch_ws_identifier"),
    )
```

- [ ] **Step 4: Round-trip in repository**

In `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/batch_repository.py`, modify the `BatchIdentifier(...)` construction inside `_to_domain` (around line 227-238):

```python
        identifiers = [
            BatchIdentifier(
                id=im.id,
                batch_id=im.batch_id,
                identifier=im.identifier,
                identifier_type=im.identifier_type,
                source=im.source,
                registered_by=im.registered_by,
                derived_from_molecule_identifier_id=im.derived_from_molecule_identifier_id,
                created_at=im.created_at,
                updated_at=im.updated_at,
            )
            for im in (model.identifiers or [])
        ]
```

And modify `_ident_to_model` (around line 359-369):

```python
    @staticmethod
    def _ident_to_model(ident: BatchIdentifier, workspace_id: uuid.UUID) -> BatchIdentifierModel:
        return BatchIdentifierModel(
            id=ident.id,
            batch_id=ident.batch_id,
            workspace_id=workspace_id,
            identifier=ident.identifier,
            identifier_type=ident.identifier_type,
            source=ident.source,
            registered_by=ident.registered_by,
            derived_from_molecule_identifier_id=ident.derived_from_molecule_identifier_id,
        )
```

- [ ] **Step 5: Run integration test to verify it passes**

Run: `cd backend && uv run pytest tests/integration/inventory/test_batch_identifier_persistence.py -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/models.py \
        backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/batch_repository.py \
        backend/tests/integration/inventory/test_batch_identifier_persistence.py \
        backend/tests/integration/inventory/conftest.py
git commit -m "feat(persistence): round-trip derived_from FK on BatchIdentifierModel"
```

---

## Task 4: `SyncBatchIdentifierMirrors` helper — pure logic + summary type

**Files:**
- Create: `backend/src/cellar/application/inventory/sync_batch_identifier_mirrors.py`
- Create: `backend/tests/unit/application/inventory/test_sync_batch_identifier_mirrors.py`

This task delivers the stateless collaborator + `MirrorSummary` type. The helper is consumed by later tasks; for now we cover its logic with unit tests using fake repos.

- [ ] **Step 1: Write failing test for suffix derivation + mirror creation**

Create `backend/tests/unit/application/inventory/test_sync_batch_identifier_mirrors.py`:

```python
"""Unit tests for SyncBatchIdentifierMirrors collaborator."""

from __future__ import annotations

import uuid

import pytest

from cellar.application.inventory.sync_batch_identifier_mirrors import (
    MirrorSummary,
    SyncBatchIdentifierMirrors,
)
from cellar.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from cellar.domain.inventory.batch import Batch
from cellar.domain.inventory.batch_identifier import BatchIdentifier
from cellar.domain.inventory.enums import BatchSource
from cellar.domain.shared.value_objects import Amount, AmountUnit, BatchNumber


WS = uuid.UUID("11111111-1111-1111-1111-111111111111")
MOL = uuid.UUID("22222222-2222-2222-2222-222222222222")
ACTOR = uuid.UUID("33333333-3333-3333-3333-333333333333")


def _batch(number: str, batch_id: uuid.UUID | None = None) -> Batch:
    return Batch(
        workspace_id=WS,
        molecule_id=MOL,
        batch_number=BatchNumber(value=number),
        amount=Amount(value=10.0, unit=AmountUnit.MG),
        source=BatchSource.IN_HOUSE,
        chemist=ACTOR,
        id=batch_id or uuid.uuid4(),
    )


def _identifier(value: str, ident_id: uuid.UUID | None = None) -> MoleculeIdentifier:
    return MoleculeIdentifier(
        id=ident_id or uuid.uuid4(),
        molecule_id=MOL,
        identifier=value,
        identifier_type="custom",
        source="Registration",
        registered_by=ACTOR,
    )


class _FakeBatchRepo:
    """Captures saved batches; returns None on alias lookup."""

    def __init__(self) -> None:
        self.saved: list[Batch] = []

    async def save(self, batch: Batch) -> None:
        self.saved.append(batch)

    async def find_by_external_identifier(self, workspace_id, identifier):
        return None


@pytest.mark.asyncio
async def test_fan_out_for_new_identifier_creates_one_mirror_per_batch():
    ident = _identifier("SACC-0001")
    batches = [_batch("CC-000001-001"), _batch("CC-000001-002")]
    repo = _FakeBatchRepo()
    sync = SyncBatchIdentifierMirrors(repo)

    summary = await sync.fan_out_for_new_identifier(
        workspace_id=WS, identifier=ident, batches=batches, actor=ACTOR,
    )

    assert summary.created == 2
    assert summary.skipped == []
    saved_strings = {bi.identifier for b in repo.saved for bi in b.identifiers}
    assert saved_strings == {"SACC-0001-001", "SACC-0001-002"}
    for b in repo.saved:
        for bi in b.identifiers:
            assert bi.identifier_type == "custom"
            assert bi.source == "compound-syn"
            assert bi.derived_from_molecule_identifier_id == ident.id


@pytest.mark.asyncio
async def test_fan_out_for_new_batch_appends_mirrors_in_memory_without_saving():
    batch = _batch("CC-000001-001")
    idents = [_identifier("SACC-0001"), _identifier("VENDOR-FOO")]
    repo = _FakeBatchRepo()
    sync = SyncBatchIdentifierMirrors(repo)

    summary = await sync.fan_out_for_new_batch(
        workspace_id=WS, batch=batch, identifiers=idents, actor=ACTOR,
    )

    assert summary.created == 2
    assert summary.skipped == []
    # Pure mutator — does NOT save; caller saves the batch.
    assert repo.saved == []
    mirror_strings = {bi.identifier for bi in batch.identifiers}
    assert mirror_strings == {"SACC-0001-001", "VENDOR-FOO-001"}


@pytest.mark.asyncio
async def test_malformed_batch_number_recorded_as_skip():
    ident = _identifier("SACC-0001")
    batches = [_batch("LEGACY-NO-SUFFIX"), _batch("ALSO_BAD"), _batch("CC-000001-005")]
    repo = _FakeBatchRepo()
    sync = SyncBatchIdentifierMirrors(repo)

    summary = await sync.fan_out_for_new_identifier(
        workspace_id=WS, identifier=ident, batches=batches, actor=ACTOR,
    )

    assert summary.created == 1
    reasons = {s.reason for s in summary.skipped}
    assert reasons == {"malformed_batch_number"}
    assert len(summary.skipped) == 2


@pytest.mark.asyncio
async def test_already_mapped_on_batch_is_skipped():
    ident = _identifier("SACC-0001")
    batch = _batch("CC-000001-001")
    batch.identifiers.append(
        BatchIdentifier.create(
            batch_id=batch.id,
            identifier="SACC-0001-001",
            identifier_type="external_lot",
            source="chemist input",
            registered_by=ACTOR,
        )
    )
    repo = _FakeBatchRepo()
    sync = SyncBatchIdentifierMirrors(repo)

    summary = await sync.fan_out_for_new_identifier(
        workspace_id=WS, identifier=ident, batches=[batch], actor=ACTOR,
    )

    assert summary.created == 0
    assert len(summary.skipped) == 1
    assert summary.skipped[0].reason == "already_mapped"
    # Pre-existing manual identifier is preserved (1 entry, untouched).
    assert len(batch.identifiers) == 1
    assert batch.identifiers[0].derived_from_molecule_identifier_id is None


@pytest.mark.asyncio
async def test_workspace_conflict_is_skipped():
    ident = _identifier("SACC-0001")
    other_batch = _batch("CC-999999-099", batch_id=uuid.uuid4())
    target_batch = _batch("CC-000001-001")

    class _Repo(_FakeBatchRepo):
        async def find_by_external_identifier(self, workspace_id, identifier):
            if identifier == "SACC-0001-001":
                return other_batch
            return None

    repo = _Repo()
    sync = SyncBatchIdentifierMirrors(repo)
    summary = await sync.fan_out_for_new_identifier(
        workspace_id=WS, identifier=ident, batches=[target_batch], actor=ACTOR,
    )

    assert summary.created == 0
    assert summary.skipped[0].reason == "workspace_conflict"


@pytest.mark.asyncio
async def test_synonym_with_internal_hyphens_round_trips():
    ident = _identifier("SACC-0036913")
    batch = _batch("CC-036715-001")
    repo = _FakeBatchRepo()
    sync = SyncBatchIdentifierMirrors(repo)

    summary = await sync.fan_out_for_new_identifier(
        workspace_id=WS, identifier=ident, batches=[batch], actor=ACTOR,
    )

    assert summary.created == 1
    assert repo.saved[0].identifiers[-1].identifier == "SACC-0036913-001"


def test_mirror_summary_combines():
    a = MirrorSummary(created=2, skipped=[])
    b = MirrorSummary.empty()
    assert (a + b).created == 2
    assert (a + b).skipped == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/application/inventory/test_sync_batch_identifier_mirrors.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cellar.application.inventory.sync_batch_identifier_mirrors'`.

- [ ] **Step 3: Implement the helper**

Create `backend/src/cellar/application/inventory/sync_batch_identifier_mirrors.py`:

```python
"""Synchronize batch identifier mirrors with molecule synonyms.

Stateless collaborator. Two entry points:
  - fan_out_for_new_identifier: for one new MoleculeIdentifier, create
    a BatchIdentifier mirror on every existing batch of the molecule.
  - fan_out_for_new_batch: for one new Batch, create a BatchIdentifier
    mirror from every existing MoleculeIdentifier of its molecule.

Both skip-and-log on collision; the parent action always succeeds.

Mirrors are identified at the DB layer by a non-NULL FK
(BatchIdentifier.derived_from_molecule_identifier_id). Removal of the
parent MoleculeIdentifier cascade-deletes its mirrors — this helper
never deletes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal, Protocol

import structlog

from cellar.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from cellar.domain.inventory.batch import Batch
from cellar.domain.inventory.batch_identifier import BatchIdentifier

logger = structlog.get_logger(__name__)

SkipReason = Literal["already_mapped", "workspace_conflict", "malformed_batch_number"]


@dataclass(frozen=True)
class SkippedMirror:
    batch_number: str
    mirror_string: str
    reason: SkipReason


@dataclass(frozen=True)
class MirrorSummary:
    created: int = 0
    skipped: list[SkippedMirror] = field(default_factory=list)

    @classmethod
    def empty(cls) -> MirrorSummary:
        return cls()

    def __add__(self, other: MirrorSummary) -> MirrorSummary:
        return MirrorSummary(
            created=self.created + other.created,
            skipped=[*self.skipped, *other.skipped],
        )


class _BatchRepoProto(Protocol):
    async def save(self, batch: Batch) -> None: ...
    async def find_by_external_identifier(
        self, workspace_id: uuid.UUID, identifier: str
    ) -> Batch | None: ...


def _derive_suffix(batch_number: str) -> str | None:
    parts = batch_number.rsplit("-", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        return None
    return parts[1]


class SyncBatchIdentifierMirrors:
    """Stateless. Runs inside the caller's UoW."""

    def __init__(self, batch_repo: _BatchRepoProto) -> None:
        self._batch_repo = batch_repo

    async def fan_out_for_new_identifier(
        self,
        *,
        workspace_id: uuid.UUID,
        identifier: MoleculeIdentifier,
        batches: list[Batch],
        actor: uuid.UUID,
    ) -> MirrorSummary:
        summary = MirrorSummary.empty()
        for batch in batches:
            summary = summary + await self._mirror_one(
                workspace_id=workspace_id,
                identifier=identifier,
                batch=batch,
                actor=actor,
            )
        return summary

    async def fan_out_for_new_batch(
        self,
        *,
        workspace_id: uuid.UUID,
        batch: Batch,
        identifiers: list[MoleculeIdentifier],
        actor: uuid.UUID,
    ) -> MirrorSummary:
        """Pure mutator. Appends mirrors to batch.identifiers. Caller must save."""
        summary = MirrorSummary.empty()
        for identifier in identifiers:
            summary = summary + await self._mirror_one(
                workspace_id=workspace_id,
                identifier=identifier,
                batch=batch,
                actor=actor,
                save=False,
            )
        return summary

    async def _mirror_one(
        self,
        *,
        workspace_id: uuid.UUID,
        identifier: MoleculeIdentifier,
        batch: Batch,
        actor: uuid.UUID,
        save: bool = True,
    ) -> MirrorSummary:
        suffix = _derive_suffix(batch.batch_number.value)
        if suffix is None:
            return MirrorSummary(
                created=0,
                skipped=[
                    SkippedMirror(
                        batch_number=batch.batch_number.value,
                        mirror_string=f"{identifier.identifier}-?",
                        reason="malformed_batch_number",
                    )
                ],
            )
        mirror_string = f"{identifier.identifier}-{suffix}"

        # Skip if same string already on this batch (manual or prior auto-mirror).
        if any(bi.identifier == mirror_string for bi in batch.identifiers):
            return MirrorSummary(
                created=0,
                skipped=[
                    SkippedMirror(
                        batch_number=batch.batch_number.value,
                        mirror_string=mirror_string,
                        reason="already_mapped",
                    )
                ],
            )

        # Skip on workspace-unique conflict on another batch.
        owner = await self._batch_repo.find_by_external_identifier(workspace_id, mirror_string)
        if owner is not None and owner.id != batch.id:
            return MirrorSummary(
                created=0,
                skipped=[
                    SkippedMirror(
                        batch_number=batch.batch_number.value,
                        mirror_string=mirror_string,
                        reason="workspace_conflict",
                    )
                ],
            )

        batch.identifiers.append(
            BatchIdentifier.create(
                batch_id=batch.id,
                identifier=mirror_string,
                identifier_type="custom",
                source="compound-syn",
                registered_by=actor,
                derived_from_molecule_identifier_id=identifier.id,
            )
        )
        if save:
            await self._batch_repo.save(batch)
        return MirrorSummary(created=1, skipped=[])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/application/inventory/test_sync_batch_identifier_mirrors.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/application/inventory/sync_batch_identifier_mirrors.py \
        backend/tests/unit/application/inventory/test_sync_batch_identifier_mirrors.py
git commit -m "feat(inventory): SyncBatchIdentifierMirrors helper + MirrorSummary"
```

---

## Task 5: Wire `AddIdentifier` → fan-out + return `AddIdentifierResult`

**Files:**
- Modify: `backend/src/cellar/application/chemical_registration/identifiers.py:53-106` (`AddIdentifier`)
- Modify: `backend/src/cellar/infrastructure/di/_chemical_registration.py:242` (factory)
- Create: `backend/tests/integration/chemical_registration/test_add_identifier_fans_out_mirrors.py`

- [ ] **Step 1: Write failing integration test**

Create `backend/tests/integration/chemical_registration/test_add_identifier_fans_out_mirrors.py`:

```python
"""Integration: AddIdentifier fans out auto-mirrors to every batch."""

from __future__ import annotations

import uuid
import pytest

from cellar.application.auth import AuthContext
from cellar.application.chemical_registration.identifiers import (
    AddIdentifier,
    AddIdentifierCommand,
)
from cellar.application.inventory.sync_batch_identifier_mirrors import (
    SyncBatchIdentifierMirrors,
)
from cellar.domain.inventory.batch import Batch
from cellar.domain.inventory.enums import BatchSource
from cellar.domain.shared.value_objects import Amount, AmountUnit, BatchNumber
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


@pytest.mark.asyncio
async def test_add_identifier_creates_one_mirror_per_existing_batch(
    sessionmaker, seeded_workspace_and_molecule, fake_event_dispatcher, editor_auth,
):
    workspace_id, molecule_id, _seed_ident_id, actor = seeded_workspace_and_molecule

    uow_seed = AsyncUnitOfWork(sessionmaker)
    batch_repo_seed = SQLAlchemyBatchRepository(uow_seed)
    async with uow_seed:
        for i in (1, 2, 3):
            b = Batch.create(
                workspace_id=workspace_id,
                molecule_id=molecule_id,
                batch_number=BatchNumber(value=f"CC-000001-00{i}"),
                amount=Amount(value=10.0, unit=AmountUnit.MG),
                source=BatchSource.IN_HOUSE,
                chemist=actor,
            )
            await batch_repo_seed.save(b)
        await uow_seed.commit()

    uow = AsyncUnitOfWork(sessionmaker)
    mol_repo = SQLAlchemyMoleculeRepository(uow)
    batch_repo = SQLAlchemyBatchRepository(uow)
    sync = SyncBatchIdentifierMirrors(batch_repo)
    use_case = AddIdentifier(uow, mol_repo, fake_event_dispatcher, sync=sync, batch_repo=batch_repo)

    result = await use_case(
        AddIdentifierCommand(
            workspace_id=workspace_id,
            molecule_id=molecule_id,
            identifier="VENDOR-FOO",
            identifier_type="custom",
            source="lab notebook",
            registered_by=actor,
        ),
        auth=editor_auth,
    )

    assert result.is_successful()
    outcome = result.unwrap()
    assert outcome.mirror_summary.created == 3
    assert outcome.mirror_summary.skipped == []

    uow2 = AsyncUnitOfWork(sessionmaker)
    repo2 = SQLAlchemyBatchRepository(uow2)
    async with uow2:
        all_batches = await repo2.find_by_molecule(workspace_id, molecule_id)
    mirror_strings = {bi.identifier for b in all_batches for bi in b.identifiers
                      if bi.derived_from_molecule_identifier_id is not None}
    assert mirror_strings == {"VENDOR-FOO-001", "VENDOR-FOO-002", "VENDOR-FOO-003"}
```

If the fixtures `fake_event_dispatcher` and `editor_auth` aren't already in the integration conftest, add to `backend/tests/integration/conftest.py` (or the nearest applicable conftest):

```python
import uuid
import pytest

from cellar.application.auth import AuthContext


class _Dispatcher:
    def __init__(self) -> None:
        self.dispatched = []
    async def dispatch_all(self, events) -> None:
        self.dispatched.extend(events)


@pytest.fixture
def fake_event_dispatcher():
    return _Dispatcher()


@pytest.fixture
def editor_auth():
    return AuthContext(
        user_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),  # tests override via seeded_workspace_and_molecule
        workspace_role="editor",
    )
```

- [ ] **Step 2: Run integration test to verify it fails**

Run: `cd backend && uv run pytest tests/integration/chemical_registration/test_add_identifier_fans_out_mirrors.py -v`
Expected: FAIL with `TypeError: AddIdentifier.__init__() got an unexpected keyword argument 'sync'` or `AttributeError: ... no attribute 'mirror_summary'`.

- [ ] **Step 3: Add `AddIdentifierResult` + modify use case**

In `backend/src/cellar/application/chemical_registration/identifiers.py`, replace the top imports + `AddIdentifier` class:

```python
"""Molecule identifier CRUD -- add, remove, list identifiers on a molecule."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_workspace_role
from cellar.application.inventory.sync_batch_identifier_mirrors import (
    MirrorSummary,
    SyncBatchIdentifierMirrors,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.inventory.repository import BatchRepository
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError, ValidationError


@dataclass(frozen=True, kw_only=True)
class AddIdentifierCommand(Command):
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID
    identifier: str
    identifier_type: str
    source: str
    registered_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class RemoveIdentifierCommand(Command):
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID
    identifier_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ListIdentifiersQuery(Query):
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class AddIdentifierResult:
    """Wrapped result: updated molecule + summary of fan-out to batch mirrors."""

    molecule: Molecule
    mirror_summary: MirrorSummary


class AddIdentifier:
    """Add an external identifier to a molecule. Fans out mirrors to all batches."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: MoleculeRepository,
        dispatcher: EventDispatcherProtocol,
        sync: SyncBatchIdentifierMirrors,
        batch_repo: BatchRepository,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._sync = sync
        self._batch_repo = batch_repo

    async def __call__(
        self,
        input: AddIdentifierCommand,
        auth: AuthContext | None = None,
    ) -> Result[AddIdentifierResult, DomainError]:
        require_editor(auth)

        async with self._uow:
            mol = await self._repo.find_by_id_in_workspace(input.workspace_id, input.molecule_id)
            if mol is None:
                return Failure(NotFoundError("Molecule", str(input.molecule_id)))

            existing = await self._repo.find_by_identifier(input.workspace_id, input.identifier)
            if existing is not None and existing.id != mol.id:
                return Failure(
                    ConflictError(
                        f"Identifier '{input.identifier}' is already assigned to "
                        f"molecule '{existing.registration_number.value}'"
                    )
                )

            try:
                identifier = MoleculeIdentifier.create(
                    molecule_id=mol.id,
                    identifier=input.identifier,
                    identifier_type=input.identifier_type,
                    source=input.source,
                    registered_by=input.registered_by,
                )
                mol.add_identifier(identifier)
            except (ValidationError, ValueError) as exc:
                if isinstance(exc, ValueError):
                    return Failure(ValidationError(str(exc)))
                return Failure(exc)

            await self._repo.save(mol)

            batches = await self._batch_repo.find_by_molecule(input.workspace_id, mol.id)
            mirror_summary = await self._sync.fan_out_for_new_identifier(
                workspace_id=input.workspace_id,
                identifier=identifier,
                batches=batches,
                actor=input.registered_by,
            )

            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(AddIdentifierResult(molecule=mol, mirror_summary=mirror_summary))


class RemoveIdentifier:
    """Remove an identifier from a molecule by ID. DB cascade removes mirrors."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: MoleculeRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: RemoveIdentifierCommand,
        auth: AuthContext | None = None,
    ) -> Result[None, DomainError]:
        require_editor(auth)

        async with self._uow:
            mol = await self._repo.find_by_id_in_workspace(input.workspace_id, input.molecule_id)
            if mol is None:
                return Failure(NotFoundError("Molecule", str(input.molecule_id)))

            try:
                mol.remove_identifier(input.identifier_id)
            except ValidationError as exc:
                return Failure(exc)

            await self._repo.save(mol)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)


class ListIdentifiers:
    """List all identifiers on a molecule (read-only)."""

    def __init__(self, uow: UnitOfWork, repo: MoleculeRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListIdentifiersQuery, auth: AuthContext | None = None
    ) -> Result[list[MoleculeIdentifier], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            mol = await self._repo.find_by_id_in_workspace(input.workspace_id, input.molecule_id)
            if mol is None:
                return Failure(NotFoundError("Molecule", str(input.molecule_id)))
            return Success(mol.identifiers)
```

- [ ] **Step 4: Update DI factory**

In `backend/src/cellar/infrastructure/di/_chemical_registration.py`, replace line 242:

```python
    def _add_identifier(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        from cellar.application.inventory.sync_batch_identifier_mirrors import (
            SyncBatchIdentifierMirrors,
        )
        from cellar.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
            SQLAlchemyBatchRepository,
        )

        batch_repo = SQLAlchemyBatchRepository(uow)
        sync = SyncBatchIdentifierMirrors(batch_repo)
        return AddIdentifier(
            uow,
            SQLAlchemyMoleculeRepository(uow),
            c[EventDispatcher],
            sync=sync,
            batch_repo=batch_repo,
        )

    container.define(AddIdentifier, _add_identifier)
```

Imports for `SQLAlchemyBatchRepository` + `SyncBatchIdentifierMirrors` should go to the top of the file alongside the other imports (the inline import in the example above is fine for the first edit; move to the top once green).

- [ ] **Step 5: Run integration test to verify it passes**

Run: `cd backend && uv run pytest tests/integration/chemical_registration/test_add_identifier_fans_out_mirrors.py -v`
Expected: 1 passed.

Also re-run the existing identifier-related tests to confirm no regression:
Run: `cd backend && uv run pytest tests/unit/application/chemical_registration tests/integration/chemical_registration -v -k "identifier"`
Expected: all green.

- [ ] **Step 6: Update existing callers of AddIdentifier**

Any test or code that called `AddIdentifier(...)` with only 3 positional args will break. Search:
Run: `cd backend && grep -rn "AddIdentifier(uow\|AddIdentifier(\\s*uow" tests/ src/`
For each hit (excluding the new code), update to pass `sync=` and `batch_repo=` kwargs OR update the caller test to use the new constructor.

Also: callers of `await use_case(command, auth=auth)` previously expected `Result[Molecule, ...]`. Now they get `Result[AddIdentifierResult, ...]`. Update each unwrap site:
- `mol = result.unwrap()` → `mol = result.unwrap().molecule`

Update the route in Task 9 (not now). For now confirm no other production unwrap sites exist:
Run: `cd backend && grep -rn "use_case.*AddIdentifierCommand\|AddIdentifier()" src/ | head -20`

- [ ] **Step 7: Commit**

```bash
git add backend/src/cellar/application/chemical_registration/identifiers.py \
        backend/src/cellar/infrastructure/di/_chemical_registration.py \
        backend/tests/integration/chemical_registration/test_add_identifier_fans_out_mirrors.py \
        backend/tests/integration/conftest.py
git commit -m "feat(chemical_registration): AddIdentifier fans out batch mirrors"
```

---

## Task 6: Wire `CreateBatch` → fan-out + return `CreateBatchResult`

**Files:**
- Modify: `backend/src/cellar/application/inventory/create_batch.py`
- Modify: `backend/src/cellar/infrastructure/di/_inventory.py:141-151` (factory)
- Create: `backend/tests/integration/inventory/test_create_batch_fans_out_mirrors.py`

- [ ] **Step 1: Write failing integration test**

Create `backend/tests/integration/inventory/test_create_batch_fans_out_mirrors.py`:

```python
"""Integration: CreateBatch fans out mirrors from existing molecule synonyms."""

from __future__ import annotations

import uuid
import pytest

from cellar.application.auth import AuthContext
from cellar.application.inventory.create_batch import CreateBatch, CreateBatchCommand
from cellar.application.inventory.sync_batch_identifier_mirrors import (
    SyncBatchIdentifierMirrors,
)
from cellar.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from cellar.domain.inventory.enums import BatchSource
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


@pytest.mark.asyncio
async def test_create_batch_fans_out_mirrors_from_existing_synonyms(
    sessionmaker, seeded_workspace_and_molecule, fake_event_dispatcher, editor_auth,
):
    workspace_id, molecule_id, _seed_ident_id, actor = seeded_workspace_and_molecule

    # Add a 2nd molecule synonym so we have 2 to fan out from.
    uow_seed = AsyncUnitOfWork(sessionmaker)
    mol_repo_seed = SQLAlchemyMoleculeRepository(uow_seed)
    async with uow_seed:
        mol = await mol_repo_seed.find_by_id_in_workspace(workspace_id, molecule_id)
        mol.add_identifier(
            MoleculeIdentifier.create(
                molecule_id=mol.id,
                identifier="VENDOR-FOO",
                identifier_type="custom",
                source="lab notebook",
                registered_by=actor,
            )
        )
        await mol_repo_seed.save(mol)
        await uow_seed.commit()

    uow = AsyncUnitOfWork(sessionmaker)
    mol_repo = SQLAlchemyMoleculeRepository(uow)
    batch_repo = SQLAlchemyBatchRepository(uow)
    sync = SyncBatchIdentifierMirrors(batch_repo)
    use_case = CreateBatch(
        uow, batch_repo, mol_repo, fake_event_dispatcher,
        custom_field_validator=None, workspace_settings_repo=None, sync=sync,
    )

    result = await use_case(
        CreateBatchCommand(
            workspace_id=workspace_id,
            molecule_id=molecule_id,
            source=BatchSource.IN_HOUSE.value,
            chemist=actor,
            amount_value=10.0,
            amount_unit="mg",
        ),
        auth=editor_auth,
    )

    assert result.is_successful()
    outcome = result.unwrap()
    assert outcome.mirror_summary.created == 2  # "SACC-0001" + "VENDOR-FOO"

    uow2 = AsyncUnitOfWork(sessionmaker)
    repo2 = SQLAlchemyBatchRepository(uow2)
    async with uow2:
        loaded = await repo2.find_by_id_in_workspace(workspace_id, outcome.batch.id)
    suffix = loaded.batch_number.value.rsplit("-", 1)[-1]
    mirror_strings = {bi.identifier for bi in loaded.identifiers
                      if bi.derived_from_molecule_identifier_id is not None}
    assert mirror_strings == {f"SACC-0001-{suffix}", f"VENDOR-FOO-{suffix}"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/integration/inventory/test_create_batch_fans_out_mirrors.py -v`
Expected: FAIL with constructor error or missing `mirror_summary` attribute.

- [ ] **Step 3: Add `CreateBatchResult` + modify `CreateBatch`**

In `backend/src/cellar/application/inventory/create_batch.py`, near the top:

```python
from dataclasses import dataclass
from cellar.application.inventory.sync_batch_identifier_mirrors import (
    MirrorSummary,
    SyncBatchIdentifierMirrors,
)
```

Add the result wrapper:

```python
@dataclass(frozen=True, kw_only=True)
class CreateBatchResult:
    batch: Batch
    mirror_summary: MirrorSummary
```

Modify the `CreateBatch.__init__` to accept `sync`:

```python
class CreateBatch:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: BatchRepository,
        molecule_repo: MoleculeRepository,
        dispatcher: EventDispatcherProtocol,
        custom_field_validator: CustomFieldValidator | None = None,
        workspace_settings_repo: WorkspaceSettingsRepository | None = None,
        sync: SyncBatchIdentifierMirrors | None = None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._molecule_repo = molecule_repo
        self._dispatcher = dispatcher
        self._custom_field_validator = custom_field_validator
        self._workspace_settings_repo = workspace_settings_repo
        self._sync = sync
```

Modify `__call__` return type and add fan-out *before* the save (so mirrors land in the same INSERT round-trip):

```python
    async def __call__(
        self, input: CreateBatchCommand, auth: AuthContext | None = None
    ) -> Result[CreateBatchResult, DomainError]:
        # ... existing logic until the `batch = Batch.create(...)` line ...

        mirror_summary = MirrorSummary.empty()
        if self._sync is not None:
            mirror_summary = await self._sync.fan_out_for_new_batch(
                workspace_id=input.workspace_id,
                batch=batch,
                identifiers=molecule.identifiers,
                actor=input.chemist,
            )

        await self._repo.save(batch)
        events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(CreateBatchResult(batch=batch, mirror_summary=mirror_summary))
```

(Sync is optional so legacy tests that constructed `CreateBatch` without it keep working; the route always passes it.)

- [ ] **Step 4: Update DI factory**

In `backend/src/cellar/infrastructure/di/_inventory.py`, modify `_batch_cmd`:

```python
    def _batch_cmd(c: Container):
        from cellar.application.inventory.sync_batch_identifier_mirrors import (
            SyncBatchIdentifierMirrors,
        )

        uow = AsyncUnitOfWork(c[async_sessionmaker])
        validator = CustomFieldValidator(repo=SQLAlchemyCustomFieldDefinitionRepository(uow))
        batch_repo = SQLAlchemyBatchRepository(uow)
        sync = SyncBatchIdentifierMirrors(batch_repo)
        return CreateBatch(
            uow,
            batch_repo,
            SQLAlchemyMoleculeRepository(uow),
            c[EventDispatcher],
            validator,
            workspace_settings_repo=SQLAlchemyWorkspaceSettingsRepository(uow),
            sync=sync,
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/integration/inventory/test_create_batch_fans_out_mirrors.py -v`
Expected: 1 passed.

Also re-run existing CreateBatch tests for regression:
Run: `cd backend && uv run pytest tests/unit/application/inventory/test_batch_identifiers.py tests/integration/inventory -v -k "create_batch or batch_creation"`
Expected: all green.

- [ ] **Step 6: Update callers of `CreateBatch`**

Any caller of `result.unwrap()` expecting a `Batch` directly now gets `CreateBatchResult`. Search:
Run: `cd backend && grep -rn "CreateBatchCommand\|use_case.*CreateBatch" src/ tests/ | head -20`
Update each unwrap site: `batch = result.unwrap()` → `batch = result.unwrap().batch`.

The route is updated separately in Task 10.

- [ ] **Step 7: Commit**

```bash
git add backend/src/cellar/application/inventory/create_batch.py \
        backend/src/cellar/infrastructure/di/_inventory.py \
        backend/tests/integration/inventory/test_create_batch_fans_out_mirrors.py
git commit -m "feat(inventory): CreateBatch fans out mirrors from molecule synonyms"
```

---

## Task 7: Wire `EnsureBatchExists` → fan-out (create branch only)

**Files:**
- Modify: `backend/src/cellar/application/inventory/ensure_batch_exists.py`
- Modify: `backend/src/cellar/infrastructure/di/_inventory.py:183-189`
- Create: `backend/tests/integration/inventory/test_ensure_batch_exists_fans_out_mirrors.py`

- [ ] **Step 1: Read existing `EnsureBatchExists` to confirm the create branch**

Run: `cd backend && cat src/cellar/application/inventory/ensure_batch_exists.py`
Identify the line where a new `Batch` is saved on the create branch (typically `await self._batch_repo.save(batch)` near the end of an `if not found` branch). The fan-out call goes immediately after that save.

- [ ] **Step 2: Write failing integration test**

Create `backend/tests/integration/inventory/test_ensure_batch_exists_fans_out_mirrors.py`:

```python
"""Integration: EnsureBatchExists fans out mirrors on the create branch."""

from __future__ import annotations

import uuid
import pytest

from cellar.application.inventory.ensure_batch_exists import (
    EnsureBatchExists,
    EnsureBatchExistsCommand,
)
from cellar.application.inventory.sync_batch_identifier_mirrors import (
    SyncBatchIdentifierMirrors,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.workspace_settings_repository import (
    SQLAlchemyWorkspaceSettingsRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


@pytest.mark.asyncio
async def test_create_branch_fans_out_mirrors(
    sessionmaker, seeded_workspace_and_molecule,
):
    workspace_id, molecule_id, _ident_id, actor = seeded_workspace_and_molecule

    uow = AsyncUnitOfWork(sessionmaker)
    batch_repo = SQLAlchemyBatchRepository(uow)
    settings_repo = SQLAlchemyWorkspaceSettingsRepository(uow)
    mol_repo = SQLAlchemyMoleculeRepository(uow)
    sync = SyncBatchIdentifierMirrors(batch_repo)
    use_case = EnsureBatchExists(
        uow=uow, batch_repo=batch_repo, settings_repo=settings_repo,
        molecule_repo=mol_repo, sync=sync,
    )

    # The EXT-LOT-Z9 ref will miss the alias lookup, triggering the create branch.
    result = await use_case(
        EnsureBatchExistsCommand(
            workspace_id=workspace_id,
            molecule_id=molecule_id,
            external_batch_ref="EXT-LOT-Z9",
            importing_user_id=actor,
            source_label="screening import test",
        ),
    )

    assert result.is_successful()
    outcome = result.unwrap()
    assert outcome.created is True

    uow2 = AsyncUnitOfWork(sessionmaker)
    repo2 = SQLAlchemyBatchRepository(uow2)
    async with uow2:
        loaded = await repo2.find_by_id_in_workspace(workspace_id, outcome.batch.id)

    by_str = {bi.identifier: bi for bi in loaded.identifiers}
    assert "EXT-LOT-Z9" in by_str  # the trigger alias (chemist input, NULL FK)
    assert by_str["EXT-LOT-Z9"].derived_from_molecule_identifier_id is None
    mirror_keys = [k for k, v in by_str.items()
                   if v.derived_from_molecule_identifier_id is not None]
    assert len(mirror_keys) == 1
    assert mirror_keys[0].startswith("SACC-0001-")  # the seeded synonym, suffixed
```

`EnsureBatchExists` currently has no auth check (no `require_*` call in the use case), so no `auth` kwarg is passed.

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/integration/inventory/test_ensure_batch_exists_fans_out_mirrors.py -v`
Expected: FAIL with constructor error or missing mirror.

- [ ] **Step 4: Modify `EnsureBatchExists`**

In `backend/src/cellar/application/inventory/ensure_batch_exists.py`:

1. Add `sync: SyncBatchIdentifierMirrors | None = None` and `molecule_repo: MoleculeRepository | None = None` parameters to `__init__`.
2. On the create branch — between the alias-add line `batch.add_identifier(...)` (the EXT trigger alias) and `await self._batch_repo.save(batch)` *plus* the `await self._uow.commit()` after — load molecule identifiers and call the fan-out helper *before* commit. The exact edit (around line 105-115):

```python
            batch.add_identifier(BatchIdentifier.create(
                batch_id=batch.id,
                identifier=input.external_batch_ref,
                identifier_type="external_lot",
                source=input.source_label,
                registered_by=input.importing_user_id,
            ))

            if self._sync is not None and self._molecule_repo is not None:
                mol = await self._molecule_repo.find_by_id_in_workspace(
                    input.workspace_id, input.molecule_id
                )
                if mol is not None and mol.identifiers:
                    await self._sync.fan_out_for_new_batch(
                        workspace_id=input.workspace_id,
                        batch=batch,
                        identifiers=mol.identifiers,
                        actor=input.importing_user_id,
                    )

            await self._batch_repo.save(batch)
            await self._uow.commit()
```

(`fan_out_for_new_batch` is a pure mutator — it appends mirrors to `batch.identifiers` in memory. The single `save(batch)` after persists the EXT alias + all mirrors in one round-trip.)

Add imports near the top of the file:
```python
from cellar.application.inventory.sync_batch_identifier_mirrors import (
    SyncBatchIdentifierMirrors,
)
from cellar.domain.chemical_registration.repository import MoleculeRepository
```

(Both kwargs are optional so existing tests that construct `EnsureBatchExists` without them keep working; DI always wires them.)

- [ ] **Step 5: Update DI factory**

In `backend/src/cellar/infrastructure/di/_inventory.py`, modify `_ensure_batch_exists`:

```python
    def _ensure_batch_exists(c: Container):
        from cellar.application.inventory.sync_batch_identifier_mirrors import (
            SyncBatchIdentifierMirrors,
        )

        uow = AsyncUnitOfWork(c[async_sessionmaker])
        batch_repo = SQLAlchemyBatchRepository(uow)
        sync = SyncBatchIdentifierMirrors(batch_repo)
        return EnsureBatchExists(
            uow=uow,
            batch_repo=batch_repo,
            settings_repo=SQLAlchemyWorkspaceSettingsRepository(uow),
            molecule_repo=SQLAlchemyMoleculeRepository(uow),
            sync=sync,
        )
```

(`SQLAlchemyMoleculeRepository` needs an import at the top — copy from where `_chemical_registration` imports it.)

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/integration/inventory/test_ensure_batch_exists_fans_out_mirrors.py -v`
Expected: 1 passed.

Re-run existing `EnsureBatchExists` tests:
Run: `cd backend && uv run pytest tests/unit/application/inventory/test_ensure_batch_exists.py -v`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add backend/src/cellar/application/inventory/ensure_batch_exists.py \
        backend/src/cellar/infrastructure/di/_inventory.py \
        backend/tests/integration/inventory/test_ensure_batch_exists_fans_out_mirrors.py
git commit -m "feat(inventory): EnsureBatchExists fans out mirrors on create branch"
```

---

## Task 8: DB cascade-delete coverage test

**Files:**
- Create: `backend/tests/integration/inventory/test_mirror_cascade_delete.py`

No code change — just verifying the ON DELETE CASCADE behaves as expected via real Postgres.

- [ ] **Step 1: Write the test**

```python
"""Integration: removing a molecule identifier cascade-deletes its batch mirrors."""

from __future__ import annotations

import pytest

from cellar.application.auth import AuthContext
from cellar.application.chemical_registration.identifiers import (
    AddIdentifier,
    AddIdentifierCommand,
    RemoveIdentifier,
    RemoveIdentifierCommand,
)
from cellar.application.inventory.sync_batch_identifier_mirrors import (
    SyncBatchIdentifierMirrors,
)
from cellar.domain.inventory.batch import Batch
from cellar.domain.inventory.enums import BatchSource
from cellar.domain.shared.value_objects import Amount, AmountUnit, BatchNumber
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


@pytest.mark.asyncio
async def test_remove_identifier_cascades_to_mirrors(
    sessionmaker, seeded_workspace_and_molecule, fake_event_dispatcher, editor_auth,
):
    workspace_id, molecule_id, _seed_ident_id, actor = seeded_workspace_and_molecule

    # Seed 2 batches.
    uow_seed = AsyncUnitOfWork(sessionmaker)
    batch_repo_seed = SQLAlchemyBatchRepository(uow_seed)
    async with uow_seed:
        for i in (1, 2):
            b = Batch.create(
                workspace_id=workspace_id,
                molecule_id=molecule_id,
                batch_number=BatchNumber(value=f"CC-000001-00{i}"),
                amount=Amount(value=10.0, unit=AmountUnit.MG),
                source=BatchSource.IN_HOUSE,
                chemist=actor,
            )
            await batch_repo_seed.save(b)
        await uow_seed.commit()

    # Add a synonym → fan out 2 mirrors.
    uow_add = AsyncUnitOfWork(sessionmaker)
    mol_repo_add = SQLAlchemyMoleculeRepository(uow_add)
    batch_repo_add = SQLAlchemyBatchRepository(uow_add)
    sync = SyncBatchIdentifierMirrors(batch_repo_add)
    add_uc = AddIdentifier(
        uow_add, mol_repo_add, fake_event_dispatcher, sync=sync, batch_repo=batch_repo_add,
    )
    add_result = await add_uc(
        AddIdentifierCommand(
            workspace_id=workspace_id,
            molecule_id=molecule_id,
            identifier="VENDOR-FOO",
            identifier_type="custom",
            source="lab",
            registered_by=actor,
        ),
        auth=editor_auth,
    )
    assert add_result.unwrap().mirror_summary.created == 2

    # The new identifier id is the last one in mol.identifiers.
    new_ident = next(i for i in add_result.unwrap().molecule.identifiers
                     if i.identifier == "VENDOR-FOO")

    # Add a chemist-managed identifier with the same string SHAPE but distinct value, NULL FK.
    # Use one of the batches for the manual row.
    uow_manual = AsyncUnitOfWork(sessionmaker)
    batch_repo_manual = SQLAlchemyBatchRepository(uow_manual)
    async with uow_manual:
        loaded = await batch_repo_manual.find_by_molecule(workspace_id, molecule_id)
    # Confirm 2 mirrors exist before removal.
    mirror_strings_before = {bi.identifier for b in loaded for bi in b.identifiers
                             if bi.derived_from_molecule_identifier_id is not None}
    assert mirror_strings_before == {"VENDOR-FOO-001", "VENDOR-FOO-002"}

    # Now remove the molecule identifier.
    uow_rm = AsyncUnitOfWork(sessionmaker)
    mol_repo_rm = SQLAlchemyMoleculeRepository(uow_rm)
    rm_uc = RemoveIdentifier(uow_rm, mol_repo_rm, fake_event_dispatcher)
    rm_result = await rm_uc(
        RemoveIdentifierCommand(
            workspace_id=workspace_id,
            molecule_id=molecule_id,
            identifier_id=new_ident.id,
        ),
        auth=editor_auth,
    )
    assert rm_result.is_successful()

    # Verify cascade fired.
    uow_chk = AsyncUnitOfWork(sessionmaker)
    batch_repo_chk = SQLAlchemyBatchRepository(uow_chk)
    async with uow_chk:
        loaded_after = await batch_repo_chk.find_by_molecule(workspace_id, molecule_id)
    mirror_strings_after = {bi.identifier for b in loaded_after for bi in b.identifiers
                            if bi.derived_from_molecule_identifier_id is not None}
    assert mirror_strings_after == set()
```

- [ ] **Step 2: Run test**

Run: `cd backend && uv run pytest tests/integration/inventory/test_mirror_cascade_delete.py -v`
Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/inventory/test_mirror_cascade_delete.py
git commit -m "test(inventory): DB cascade deletes mirrors when molecule synonym removed"
```

---

## Task 9: API response shape — `mirror_summary` on `POST /molecules/{id}/identifiers`

**Files:**
- Modify: `backend/src/cellar/interface/routes/molecules.py:763-785`
- Create: `backend/tests/api/molecules/test_add_identifier_response.py` (or extend nearest sibling)

- [ ] **Step 1: Write failing API test**

Create `backend/tests/api/molecules/test_add_identifier_response.py`:

```python
"""API: POST /molecules/{id}/identifiers returns mirror_summary."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_add_identifier_returns_mirror_summary(
    api_client, seeded_workspace_and_molecule_with_2_batches,
):
    workspace_id, molecule_id = seeded_workspace_and_molecule_with_2_batches
    resp = await api_client.post(
        f"/api/v1/molecules/{molecule_id}/identifiers",
        json={
            "identifier": "VENDOR-FOO",
            "identifier_type": "custom",
            "source": "lab notebook",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "identifiers" in body
    assert "mirror_summary" in body
    assert body["mirror_summary"]["created"] == 2
    assert body["mirror_summary"]["skipped"] == []
```

(If `api_client` and `seeded_workspace_and_molecule_with_2_batches` fixtures don't exist, follow the pattern of the nearest sibling test in `tests/api/molecules/` to wire them. Many sibling tests already construct an `httpx.AsyncClient` against the FastAPI app.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/api/molecules/test_add_identifier_response.py -v`
Expected: FAIL — response is `list[IdentifierResponse]` not an object with `mirror_summary`.

- [ ] **Step 3: Modify route + response model**

In `backend/src/cellar/interface/routes/molecules.py`, near the other response models, add:

```python
class MirrorSummarySkippedResponse(BaseModel):
    batch_number: str
    mirror_string: str
    reason: str


class MirrorSummaryResponse(BaseModel):
    created: int
    skipped: list[MirrorSummarySkippedResponse]

    @classmethod
    def from_domain(cls, summary) -> MirrorSummaryResponse:
        return cls(
            created=summary.created,
            skipped=[
                MirrorSummarySkippedResponse(
                    batch_number=s.batch_number,
                    mirror_string=s.mirror_string,
                    reason=s.reason,
                )
                for s in summary.skipped
            ],
        )


class AddIdentifierResponse(BaseModel):
    identifiers: list[IdentifierResponse]
    mirror_summary: MirrorSummaryResponse
```

Replace the `add_identifier` route (around line 763-785):

```python
@router.post(
    "/{molecule_id}/identifiers",
    response_model=AddIdentifierResponse,
    status_code=201,
)
async def add_identifier(
    molecule_id: uuid.UUID,
    body: AddIdentifierBody,
    auth: AuthDep,
    use_case: AddIdentifierDep,
) -> AddIdentifierResponse:
    """Add an external identifier to a molecule. Returns updated list + mirror summary."""
    command = AddIdentifierCommand(
        workspace_id=auth.workspace_id,
        molecule_id=molecule_id,
        identifier=body.identifier,
        identifier_type=body.identifier_type,
        source=body.source,
        registered_by=auth.user_id,
    )
    outcome = result_to_response(await use_case(command, auth=auth))
    return AddIdentifierResponse(
        identifiers=[IdentifierResponse.from_domain(i) for i in outcome.molecule.identifiers],
        mirror_summary=MirrorSummaryResponse.from_domain(outcome.mirror_summary),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/api/molecules/test_add_identifier_response.py -v`
Expected: 1 passed.

- [ ] **Step 5: Sanity-check no other route tests broke**

Run: `cd backend && uv run pytest tests/api/molecules -v -k "identifier"`
Expected: all green (existing tests reading `body[0]` for the old list shape need updating — search and fix any).

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/interface/routes/molecules.py \
        backend/tests/api/molecules/test_add_identifier_response.py
git commit -m "feat(api): mirror_summary on POST /molecules/{id}/identifiers"
```

---

## Task 10: API response shape — `mirror_summary` on `POST /batches`

**Files:**
- Modify: `backend/src/cellar/interface/routes/batches.py:47-191`
- Create: `backend/tests/api/inventory/test_create_batch_response.py`

- [ ] **Step 1: Write failing API test**

Create `backend/tests/api/inventory/test_create_batch_response.py`:

```python
"""API: POST /batches returns mirror_summary."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_create_batch_returns_mirror_summary(
    api_client, seeded_workspace_and_molecule_with_2_synonyms,
):
    workspace_id, molecule_id = seeded_workspace_and_molecule_with_2_synonyms
    resp = await api_client.post(
        "/api/v1/batches",
        json={
            "molecule_id": str(molecule_id),
            "source": "in_house",
            "amount_value": 10.0,
            "amount_unit": "mg",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "batch" in body
    assert "mirror_summary" in body
    assert body["mirror_summary"]["created"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/api/inventory/test_create_batch_response.py -v`
Expected: FAIL — response is a flat `BatchResponse`, not an envelope.

- [ ] **Step 3: Modify route + add response envelope**

In `backend/src/cellar/interface/routes/batches.py`, add a new response model (reuse `MirrorSummaryResponse` from molecules.py — import it, or duplicate the small class if cross-route imports are discouraged in this codebase):

```python
from cellar.interface.routes.molecules import MirrorSummaryResponse


class CreateBatchResponse(BaseModel):
    batch: BatchResponse
    mirror_summary: MirrorSummaryResponse
```

Replace the route (around line 160-191):

```python
@router.post("/batches", response_model=CreateBatchResponse, status_code=201)
async def create_batch(
    auth: AuthDep,
    body: CreateBatchRequest,
    uc: CreateBatchDep,
) -> CreateBatchResponse:
    cmd = CreateBatchCommand(
        workspace_id=auth.workspace_id,
        molecule_id=body.molecule_id,
        source=body.source,
        chemist=auth.user_id,
        amount_value=body.amount_value,
        amount_unit=body.amount_unit,
        salt_entry_id=body.salt_entry_id,
        salt_name=body.salt_name,
        salt_smiles=body.salt_smiles,
        salt_stoichiometry=body.salt_stoichiometry,
        formula_weight=body.formula_weight,
        purity=body.purity,
        concentration_value=body.concentration_value,
        concentration_unit=body.concentration_unit,
        supplier_org_id=body.supplier_org_id,
        vendor_catalog_number=body.vendor_catalog_number,
        vendor_lot_number=body.vendor_lot_number,
        synthesis_date=body.synthesis_date,
        expiry_date=body.expiry_date,
        notebook_reference=body.notebook_reference,
        appearance=body.appearance,
        custom_fields=body.custom_fields,
    )
    outcome = result_to_response(await uc(cmd, auth=auth))
    return CreateBatchResponse(
        batch=BatchResponse.from_domain(outcome.batch),
        mirror_summary=MirrorSummaryResponse.from_domain(outcome.mirror_summary),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/api/inventory/test_create_batch_response.py -v`
Expected: 1 passed.

Re-run other `/batches` route tests:
Run: `cd backend && uv run pytest tests/api -v -k "batch and not test_create_batch_response"`
Expected: green (any existing test that expected a flat `BatchResponse` from POST /batches will fail; update to read `body["batch"]`).

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/interface/routes/batches.py \
        backend/tests/api/inventory/test_create_batch_response.py
git commit -m "feat(api): mirror_summary on POST /batches"
```

---

## Task 11: Orval regen

**Files:**
- Modify: `frontend/src/shared/lib/api/` (regenerated)

- [ ] **Step 1: Regenerate orval client**

Run: `cd frontend && pnpm exec orval`
Expected: regenerates `frontend/src/shared/lib/api/` against the new OpenAPI schema. New types like `AddIdentifierResponse`, `CreateBatchResponse`, `MirrorSummary` appear.

- [ ] **Step 2: Verify FE typecheck**

Run: `cd frontend && pnpm exec tsc --noEmit`
Expected: any FE callers of the old response shapes break with compile errors. These are fixed in Tasks 13 + 14 — for this task, just note which files need touching (the compiler tells you).

If the typecheck has too many errors to commit in this task alone, defer the regen until Task 12 is done (the new toast component lives independently of the type shape). Otherwise, commit just the regenerated files and move on.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/shared/lib/api
git commit -m "chore(frontend): orval regen for mirror_summary in identifier + batch responses"
```

---

## Task 12: FE — shared `MirrorSummaryToast` component

**Files:**
- Create: `frontend/src/features/inventory/components/mirror-summary-toast.tsx`
- Create: `frontend/src/features/inventory/components/__tests__/mirror-summary-toast.test.tsx`

- [ ] **Step 1: Write failing component test**

Create `frontend/src/features/inventory/components/__tests__/mirror-summary-toast.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest"
import { renderToast } from "../mirror-summary-toast"
import { toast } from "sonner"

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    message: vi.fn(),
  },
}))

beforeEach(() => {
  vi.clearAllMocks()
})

describe("renderToast", () => {
  it("does nothing for an empty summary", () => {
    renderToast({ created: 0, skipped: [] })
    expect(toast.success).not.toHaveBeenCalled()
    expect(toast.message).not.toHaveBeenCalled()
  })

  it("renders success toast for created > 0 and no skips", () => {
    renderToast({ created: 3, skipped: [] })
    expect(toast.success).toHaveBeenCalledWith(
      expect.stringContaining("3 batch mirror"),
      expect.any(Object),
    )
  })

  it("renders message toast with details when there are skips", () => {
    renderToast({
      created: 2,
      skipped: [
        { batch_number: "CC-036715-002", mirror_string: "SACC-0036913-002", reason: "workspace_conflict" },
      ],
    })
    expect(toast.message).toHaveBeenCalledWith(
      expect.stringContaining("2 created"),
      expect.objectContaining({
        description: expect.stringContaining("1 skipped"),
      }),
    )
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run src/features/inventory/components/__tests__/mirror-summary-toast.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement component**

Create `frontend/src/features/inventory/components/mirror-summary-toast.tsx`:

```typescript
import { toast } from "sonner"

export type MirrorSummary = {
  created: number
  skipped: Array<{
    batch_number: string
    mirror_string: string
    reason: "already_mapped" | "workspace_conflict" | "malformed_batch_number"
  }>
}

const reasonLabels = {
  already_mapped: "already exists as manual identifier",
  workspace_conflict: "already exists on another batch",
  malformed_batch_number: "batch number has no -NNN suffix",
} as const

export function renderToast(summary: MirrorSummary): void {
  const { created, skipped } = summary
  if (created === 0 && skipped.length === 0) return

  if (skipped.length === 0) {
    toast.success(
      `${created} batch mirror${created === 1 ? "" : "s"} created`,
      { duration: 4000 },
    )
    return
  }

  const detail = skipped
    .map((s) => `${s.mirror_string} → ${reasonLabels[s.reason]}`)
    .join("\n")
  toast.message(
    `${created} created · ${skipped.length} skipped`,
    {
      description: detail,
      duration: 8000,
    },
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm vitest run src/features/inventory/components/__tests__/mirror-summary-toast.test.tsx`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/inventory/components/mirror-summary-toast.tsx \
        frontend/src/features/inventory/components/__tests__/mirror-summary-toast.test.tsx
git commit -m "feat(frontend): MirrorSummaryToast — Sonner renderer for fan-out outcomes"
```

---

## Task 13: FE wire toast into `addIdentifier` mutation

**Files:**
- Modify: `frontend/src/features/chemical-registration/hooks/use-molecules.ts`

- [ ] **Step 1: Find the existing `addIdentifier` mutation**

Run: `cd frontend && grep -n "addIdentifier\|/identifiers" src/features/chemical-registration/hooks/use-molecules.ts | head -20`

This locates the mutation hook (likely `useAddIdentifier` or wrapped in a `useMolecules` factory).

- [ ] **Step 2: Wire the toast in `onSuccess`**

Add at the top of the file:

```typescript
import { renderToast } from "@/features/inventory/components/mirror-summary-toast"
```

In the `addIdentifier` mutation's `onSuccess` (or equivalent callback), after the existing query invalidation calls:

```typescript
onSuccess: (data) => {
  // ...existing invalidation...
  if (data?.mirror_summary) {
    renderToast(data.mirror_summary)
  }
},
```

If the existing hook is named differently or returns a shape the orval regen didn't reach yet, check the new orval-generated type for the POST identifier endpoint and adapt the field access accordingly.

- [ ] **Step 3: Manual verification (no automated test)**

Run: `cd frontend && pnpm exec tsc --noEmit`
Expected: no TS errors related to `data.mirror_summary`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/chemical-registration/hooks/use-molecules.ts
git commit -m "feat(frontend): toast fan-out summary on addIdentifier"
```

---

## Task 14: FE wire toast into `createBatch` mutation

**Files:**
- Modify: `frontend/src/features/inventory/hooks/use-batches.ts`

- [ ] **Step 1: Find the existing `createBatch` mutation**

Run: `cd frontend && grep -n "createBatch\|mutationFn" src/features/inventory/hooks/use-batches.ts | head -20`

- [ ] **Step 2: Wire the toast**

Add at the top:

```typescript
import { renderToast } from "@/features/inventory/components/mirror-summary-toast"
```

In the `createBatch` mutation's `onSuccess`:

```typescript
onSuccess: (data) => {
  // ...existing invalidation...
  if (data?.mirror_summary) {
    renderToast(data.mirror_summary)
  }
},
```

Note: with the new envelope, the batch payload is at `data.batch`, not `data` directly. Any existing code that read fields off the old flat response now needs `data.batch.<field>`. Update those sites.

- [ ] **Step 3: Typecheck**

Run: `cd frontend && pnpm exec tsc --noEmit`
Expected: any consumer reading `data.id`, `data.batch_number`, etc. from the old createBatch response is now flagged — fix to `data.batch.id`, etc.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/inventory/hooks/use-batches.ts
# also stage any consumer files that needed `.batch.` rewrites
git commit -m "feat(frontend): toast fan-out summary on createBatch"
```

---

## Task 15: Backfill script + integration test

**Files:**
- Create: `backend/scripts/backfill_batch_identifier_mirrors.py`
- Create: `backend/tests/integration/scripts/test_backfill_batch_identifier_mirrors.py`

- [ ] **Step 1: Write failing integration test**

Create `backend/tests/integration/scripts/test_backfill_batch_identifier_mirrors.py`:

```python
"""Integration: backfill_batch_identifier_mirrors is idempotent."""

from __future__ import annotations

import pytest

from cellar.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from cellar.domain.inventory.batch import Batch
from cellar.domain.inventory.enums import BatchSource
from cellar.domain.shared.value_objects import Amount, AmountUnit, BatchNumber
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

from scripts.backfill_batch_identifier_mirrors import run_backfill


@pytest.mark.asyncio
async def test_backfill_idempotent_and_creates_expected_mirrors(
    sessionmaker, seeded_workspace_and_molecule,
):
    workspace_id, molecule_id, ident_id, actor = seeded_workspace_and_molecule

    # Add a 2nd synonym + 2 batches.
    uow = AsyncUnitOfWork(sessionmaker)
    mol_repo = SQLAlchemyMoleculeRepository(uow)
    batch_repo = SQLAlchemyBatchRepository(uow)
    async with uow:
        mol = await mol_repo.find_by_id_in_workspace(workspace_id, molecule_id)
        mol.add_identifier(
            MoleculeIdentifier.create(
                molecule_id=mol.id, identifier="VENDOR-FOO",
                identifier_type="custom", source="lab", registered_by=actor,
            )
        )
        await mol_repo.save(mol)
        for i in (1, 2):
            b = Batch.create(
                workspace_id=workspace_id, molecule_id=molecule_id,
                batch_number=BatchNumber(value=f"CC-000001-00{i}"),
                amount=Amount(value=10.0, unit=AmountUnit.MG),
                source=BatchSource.IN_HOUSE, chemist=actor,
            )
            await batch_repo.save(b)
        await uow.commit()

    stats1 = await run_backfill(sessionmaker, workspace_id=workspace_id)
    assert stats1["created"] == 4  # 2 synonyms × 2 batches
    assert stats1["skipped"] == 0
    assert stats1["malformed"] == 0

    stats2 = await run_backfill(sessionmaker, workspace_id=workspace_id)
    assert stats2["created"] == 0
    assert stats2["skipped"] == 4
    assert stats2["malformed"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/integration/scripts/test_backfill_batch_identifier_mirrors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.backfill_batch_identifier_mirrors'`.

- [ ] **Step 3: Implement the script**

Create `backend/scripts/backfill_batch_identifier_mirrors.py`:

```python
"""One-shot backfill: materialize BatchIdentifier mirrors for existing molecule
synonyms + batches.

Idempotent. Uses ON CONFLICT DO NOTHING against the workspace-unique
constraint. Safe to re-run.

Run via:
    cd backend && uv run python scripts/backfill_batch_identifier_mirrors.py
    cd backend && uv run python scripts/backfill_batch_identifier_mirrors.py --workspace-id <uuid>
    cd backend && uv run python scripts/backfill_batch_identifier_mirrors.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Eagerly import sibling model modules so SQLAlchemy can resolve cross-context FKs.
import cellar.infrastructure.persistence.sqlalchemy.workspace_config.models  # noqa: F401
import cellar.infrastructure.persistence.sqlalchemy.research_organization.models  # noqa: F401
import cellar.infrastructure.persistence.sqlalchemy.screening_assay.models  # noqa: F401
import cellar.infrastructure.persistence.sqlalchemy.inventory.models  # noqa: F401
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
    MoleculeIdentifierModel,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import BatchModel
from cellar.infrastructure.persistence.settings import DatabaseSettings

logger = structlog.get_logger(__name__)


def _derive_suffix(batch_number: str) -> str | None:
    parts = batch_number.rsplit("-", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        return None
    return parts[1]


async def run_backfill(
    sessionmaker, *, workspace_id: uuid.UUID | None = None, dry_run: bool = False
) -> dict[str, int]:
    stats = {"created": 0, "skipped": 0, "malformed": 0}

    async with sessionmaker() as session:
        # Load all (molecule_id, workspace_id) pairs to iterate.
        mol_q = select(MoleculeModel.id, MoleculeModel.workspace_id)
        if workspace_id is not None:
            mol_q = mol_q.where(MoleculeModel.workspace_id == workspace_id)
        mol_rows = (await session.execute(mol_q)).all()

        for mol_id, ws_id in mol_rows:
            ident_rows = (
                await session.execute(
                    select(
                        MoleculeIdentifierModel.id,
                        MoleculeIdentifierModel.identifier,
                        MoleculeIdentifierModel.registered_by,
                    ).where(MoleculeIdentifierModel.molecule_id == mol_id)
                )
            ).all()
            batch_rows = (
                await session.execute(
                    select(BatchModel.id, BatchModel.batch_number).where(
                        BatchModel.molecule_id == mol_id
                    )
                )
            ).all()

            for ident_id, ident_value, ident_actor in ident_rows:
                for batch_id, batch_number in batch_rows:
                    suffix = _derive_suffix(batch_number)
                    if suffix is None:
                        stats["malformed"] += 1
                        continue
                    mirror = f"{ident_value}-{suffix}"
                    if dry_run:
                        stats["created"] += 1
                        continue
                    result = await session.execute(
                        text(
                            """
                            INSERT INTO batch_identifiers (
                                id, batch_id, workspace_id, identifier,
                                identifier_type, source, registered_by,
                                derived_from_molecule_identifier_id, created_at
                            ) VALUES (
                                gen_random_uuid(), :batch_id, :workspace_id, :identifier,
                                'custom', 'compound-syn (backfill)', :registered_by,
                                :derived_from, NOW()
                            )
                            ON CONFLICT (workspace_id, identifier) DO NOTHING
                            """
                        ),
                        {
                            "batch_id": batch_id,
                            "workspace_id": ws_id,
                            "identifier": mirror,
                            "registered_by": ident_actor,
                            "derived_from": ident_id,
                        },
                    )
                    if result.rowcount and result.rowcount > 0:
                        stats["created"] += 1
                    else:
                        stats["skipped"] += 1
        if not dry_run:
            await session.commit()

    logger.info("backfill_done", **stats)
    return stats


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Backfill batch identifier mirrors.")
    parser.add_argument("--workspace-id", type=uuid.UUID, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    engine = create_async_engine(DatabaseSettings().url, echo=False)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    stats = await run_backfill(
        sessionmaker, workspace_id=args.workspace_id, dry_run=args.dry_run
    )
    print(f"backfill: created={stats['created']} skipped={stats['skipped']} "
          f"malformed={stats['malformed']} dry_run={args.dry_run}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
```

- [ ] **Step 4: Run integration test to verify it passes**

Run: `cd backend && uv run pytest tests/integration/scripts/test_backfill_batch_identifier_mirrors.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/backfill_batch_identifier_mirrors.py \
        backend/tests/integration/scripts/test_backfill_batch_identifier_mirrors.py
git commit -m "feat(scripts): backfill_batch_identifier_mirrors — idempotent one-shot"
```

---

## Final verification

After all 15 tasks land:

- [ ] **Full BE test suite**

Run: `cd backend && uv run pytest tests/unit tests/integration tests/api -q`
Expected: all green.

- [ ] **Full FE test suite + typecheck**

Run: `cd frontend && pnpm test && pnpm exec tsc --noEmit`
Expected: all green.

- [ ] **Smoke checklist (browser, dev stack)**

See spec's "Smoke checklist" section — 9 scenarios spanning the wizard, conflict toast, cascade-delete verification in DB, and backfill re-run.
