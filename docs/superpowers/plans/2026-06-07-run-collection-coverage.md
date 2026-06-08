# Run/Protocol Collection Coverage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a run attach one or more `Collection`s (libraries), show per-run and protocol-rolled-up screening **coverage %** + an unscreened-member **gap list**, and give every collection type its own icon.

**Architecture:** Mirror the shipped run/protocol **targets** M2M (`run_targets`) feature: a pure association table `run_collections`, repo-managed (aggregate stays clean), idempotent lock-guarded use cases with audit events. Coverage is **computed live** at read time by a focused cross-context read model (`coverage_query.py`) that joins `run_collections` + `readout_data` (screening) with `collection_molecules` (research-org) via `COUNT(DISTINCT molecule_id)`. No persisted/derived coverage state.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy 2.0 async / Alembic / Lagom DI / dry-python returns (Railway) / pytest. Frontend: Next.js 16 / React 19 / TypeScript / TanStack Query / shadcn/ui / AG Grid / lucide-react / orval / Playwright.

**Spec:** `docs/superpowers/specs/2026-06-07-run-collection-coverage-design.md`

**Reference (mirror these):**
- `backend/src/cellar/application/screening/manage_run_targets.py`
- `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/run_repository.py` (`add_target`/`remove_target`)
- `backend/alembic/versions/051_protocol_run_targets_m2m.py`, `053_target_link_restrict.py`
- `frontend/src/features/screening-assay/components/target-multi-select.tsx`, `target-chips.tsx`, `hooks/create-target-link-hooks.ts`

---

## File Structure

**Backend — create:**
- `backend/alembic/versions/055_run_collections_m2m.py` — migration
- `backend/src/cellar/domain/screening_assay/collection_coverage.py` — `CollectionRef`, `CollectionCoverage`, `EffectiveCollectionCoverage` VOs
- `backend/src/cellar/application/screening/manage_run_collections.py` — Add/Remove use cases
- `backend/src/cellar/application/screening/resolve_collection_coverage.py` — Resolve run coverage + protocol rollup use cases
- `backend/src/cellar/application/screening/get_collection_gap.py` — run/protocol gap use cases
- `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/coverage_query.py` — `SQLAlchemyCollectionCoverageQuery`
- `backend/src/cellar/interface/routes/_collection_coverage.py` — response models

**Backend — modify:**
- `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/models.py` — add `run_collections` Table
- `backend/src/cellar/domain/screening_assay/repository.py` — `CollectionLinkResult` enum, `CollectionCoverageReader` protocol, RunRepository abstract methods
- `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/run_repository.py` — `add_collection`/`remove_collection`
- `backend/src/cellar/domain/screening_assay/events.py` — `RunCollectionAdded`/`RunCollectionRemoved`
- `backend/src/cellar/application/screening/list_runs_with_counts.py` — add `collections`
- `backend/src/cellar/application/screening/create_run.py` — accept `collection_ids`
- `backend/src/cellar/interface/routes/runs.py` — endpoints, `RunResponse.collections`, `CreateRunRequest.collection_ids`
- `backend/src/cellar/interface/routes/protocols.py` — coverage + gap endpoints
- `backend/src/cellar/infrastructure/di/_screening.py` — factories
- `backend/src/cellar/interface/dependencies/_screening.py` — `*Dep` aliases + `__all__`

**Frontend — create:**
- `frontend/src/features/research-organization/components/collection/collection-type-icon.tsx` — `COLLECTION_TYPE_ICONS` + `<CollectionTypeIcon>`
- `frontend/src/features/screening-assay/components/coverage-bar.tsx`
- `frontend/src/features/screening-assay/components/coverage-gap-dialog.tsx`
- `frontend/src/features/screening-assay/components/collection-coverage-chips.tsx`
- `frontend/src/features/screening-assay/components/collection-multi-select.tsx`
- `frontend/src/features/screening-assay/hooks/use-run-collections.ts`
- `frontend/src/features/screening-assay/hooks/create-link-hooks.ts` (generalized from `create-target-link-hooks.ts`)

**Frontend — modify:**
- `frontend/src/features/screening-assay/hooks/use-run-targets.ts`, `use-protocol-targets.ts` — use generalized factory
- `frontend/src/features/screening-assay/components/run-detail.tsx` — Collections card
- `frontend/src/features/screening-assay/components/run-list.tsx` — coverage column
- protocol detail component — coverage rollup section
- `frontend/src/features/research-organization/components/collection/collection-header.tsx` + `collection-list.tsx` — render type icon
- `frontend/src/features/screening-assay/types/index.ts` — `Run.collections`, coverage type aliases

---

# Phase 1 — Persistence foundation

### Task 1: Migration `055_run_collections_m2m`

**Files:**
- Create: `backend/alembic/versions/055_run_collections_m2m.py`

- [ ] **Step 1: Write the migration**

```python
"""run-collection M2M

A run can attach one or more collections (libraries); the protocol shows
rolled-up screening coverage over the runs that attached each collection. Pure
association table, mirroring ``run_targets`` (migration 051) but with the
referenced (collection) side declared ``RESTRICT`` from the start — a collection
referenced by a run cannot be silently deleted (the lesson of migration 053).
The owner (run) side keeps CASCADE: deleting a run drops its link rows.

Revision ID: 055_run_collections_m2m
Revises: 054_favorites
Create Date: 2026-06-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "055_run_collections_m2m"
down_revision = "054_favorites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_collections",
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "collection_id",
            sa.Uuid(),
            sa.ForeignKey("collections.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_run_collections_collection", "run_collections", ["collection_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_run_collections_collection", table_name="run_collections")
    op.drop_table("run_collections")
```

- [ ] **Step 2: Verify the migration applies and reverses**

Run: `cd backend && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: no errors; `run_collections` created, dropped, recreated.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/055_run_collections_m2m.py
git commit -m "feat(screening): migration 055 — run_collections M2M (RESTRICT on collection)"
```

---

### Task 2: `run_collections` Table in the model file

**Files:**
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/models.py` (near the `run_targets` Table, ~line 86-105)

- [ ] **Step 1: Add the Table** (mirror `run_targets`; collection side is `RESTRICT`)

```python
run_collections = Table(
    "run_collections",
    Base.metadata,
    Column(
        "run_id",
        Uuid(as_uuid=True),
        ForeignKey("runs.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "collection_id",
        Uuid(as_uuid=True),
        ForeignKey("collections.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
    Index("ix_run_collections_collection", "collection_id"),
)
```

- [ ] **Step 2: Verify the model imports cleanly**

Run: `cd backend && uv run python -c "from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import run_collections; print(run_collections.c.keys())"`
Expected: `['run_id', 'collection_id']`

- [ ] **Step 3: Commit**

```bash
git add backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/models.py
git commit -m "feat(screening): run_collections association Table"
```

---

### Task 3: Coverage value objects

**Files:**
- Create: `backend/src/cellar/domain/screening_assay/collection_coverage.py`
- Test: `backend/tests/unit/domain/screening_assay/test_collection_coverage.py`

- [ ] **Step 1: Write the failing test**

```python
import uuid

from cellar.domain.screening_assay.collection_coverage import (
    CollectionCoverage,
    CollectionRef,
    EffectiveCollectionCoverage,
)


def _ref() -> CollectionRef:
    return CollectionRef(id=uuid.uuid4(), name="Kinase Set", type="library")


def test_fraction_is_ratio_of_covered_to_total():
    cov = CollectionCoverage(ref=_ref(), covered=1840, total=2000)
    assert cov.fraction == 0.92


def test_fraction_is_none_for_empty_collection():
    cov = CollectionCoverage(ref=_ref(), covered=0, total=0)
    assert cov.fraction is None


def test_effective_coverage_carries_run_count():
    eff = EffectiveCollectionCoverage(ref=_ref(), covered=1840, total=2000, run_count=2)
    assert eff.fraction == 0.92
    assert eff.run_count == 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/unit/domain/screening_assay/test_collection_coverage.py -v`
Expected: FAIL — `ModuleNotFoundError: cellar.domain.screening_assay.collection_coverage`

- [ ] **Step 3: Write the value objects**

```python
"""Collection-coverage read-model value objects for runs and protocols.

Coverage is derived (never persisted): how many of a collection's molecules a
run — or a protocol's attaching runs cumulatively — has screened. ``fraction``
is ``None`` for an empty collection (no divide-by-zero; surfaced as "—"). See
``docs/superpowers/specs/2026-06-07-run-collection-coverage-design.md``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class CollectionRef:
    """Lightweight collection reference for read models (chips, coverage bars).

    ``type`` is the collection-type enum value (e.g. ``"library"``), carried as
    a plain string so the screening read model needn't import the research-org
    enum.
    """

    id: uuid.UUID
    name: str
    type: str


@dataclass(frozen=True)
class CollectionCoverage:
    """A run's coverage of one attached collection."""

    ref: CollectionRef
    covered: int
    total: int

    @property
    def fraction(self) -> float | None:
        """Covered / total, or ``None`` when the collection is empty."""
        if self.total == 0:
            return None
        return self.covered / self.total


@dataclass(frozen=True)
class EffectiveCollectionCoverage:
    """A protocol's cumulative coverage of one collection across attaching runs."""

    ref: CollectionRef
    covered: int
    total: int
    run_count: int

    @property
    def fraction(self) -> float | None:
        if self.total == 0:
            return None
        return self.covered / self.total
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/unit/domain/screening_assay/test_collection_coverage.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/domain/screening_assay/collection_coverage.py backend/tests/unit/domain/screening_assay/test_collection_coverage.py
git commit -m "feat(screening): collection-coverage value objects"
```

---

### Task 4: Domain repository contracts

**Files:**
- Modify: `backend/src/cellar/domain/screening_assay/repository.py` (where `TargetLinkResult` and `RunRepository` live)

- [ ] **Step 1: Add `CollectionLinkResult` enum** (next to `TargetLinkResult`)

```python
class CollectionLinkResult(Enum):
    """Outcome of attaching a collection to a run (idempotent)."""

    ADDED = "added"
    ALREADY_LINKED = "already_linked"
    OWNER_NOT_FOUND = "owner_not_found"
    COLLECTION_NOT_FOUND = "collection_not_found"
```

(If `Enum` is not yet imported in this file, add `from enum import Enum` — check the top; `TargetLinkResult` already uses it, so it is imported.)

- [ ] **Step 2: Add abstract methods to `RunRepository`** (next to `add_target`/`remove_target`)

```python
    @abstractmethod
    async def add_collection(
        self, workspace_id: uuid.UUID, run_id: uuid.UUID, collection_id: uuid.UUID
    ) -> CollectionLinkResult:
        """Attach a collection to a run (idempotent)."""
        ...

    @abstractmethod
    async def remove_collection(
        self, workspace_id: uuid.UUID, run_id: uuid.UUID, collection_id: uuid.UUID
    ) -> bool:
        """Detach a collection from a run. Returns True if a link was removed."""
        ...
```

- [ ] **Step 3: Add the `CollectionCoverageReader` protocol** (a read-model port the use cases depend on; place near `ReadoutDataRepository`)

```python
class CollectionCoverageReader(Protocol):
    """Read-model port for live collection-coverage computation.

    Implemented in screening infra; joins ``run_collections`` + ``readout_data``
    with research-org ``collection_molecules``. Read-only reporting.
    """

    async def run_coverage(
        self, workspace_id: uuid.UUID, run_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[CollectionCoverage]]: ...

    async def protocol_coverage(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID
    ) -> list[EffectiveCollectionCoverage]: ...

    async def run_gap(
        self,
        workspace_id: uuid.UUID,
        run_id: uuid.UUID,
        collection_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[uuid.UUID]: ...

    async def protocol_gap(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        collection_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[uuid.UUID]: ...
```

Add the import at the top of `repository.py`:

```python
from cellar.domain.screening_assay.collection_coverage import (
    CollectionCoverage,
    EffectiveCollectionCoverage,
)
```

(If `Protocol` is not imported, add `from typing import Protocol`.)

- [ ] **Step 4: Verify it imports**

Run: `cd backend && uv run python -c "from cellar.domain.screening_assay.repository import CollectionLinkResult, CollectionCoverageReader; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/domain/screening_assay/repository.py
git commit -m "feat(screening): CollectionLinkResult + CollectionCoverageReader contracts"
```

---

### Task 5: `add_collection` / `remove_collection` on the run repository

**Files:**
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/run_repository.py`
- Test: `backend/tests/integration/persistence/screening/test_run_collection_links.py`

- [ ] **Step 1: Write the failing integration test** (follow the existing run-target link test for fixtures: `tests/integration/persistence/screening/test_run_target_links.py`)

```python
import uuid

import pytest

from cellar.domain.screening_assay.repository import CollectionLinkResult
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.run_repository import (
    SQLAlchemyRunRepository,
)

pytestmark = pytest.mark.asyncio


async def test_add_collection_is_idempotent(uow, seeded_run, seeded_collection):
    async with uow:
        repo = SQLAlchemyRunRepository(uow)
        first = await repo.add_collection(
            seeded_run.workspace_id, seeded_run.id, seeded_collection.id
        )
        second = await repo.add_collection(
            seeded_run.workspace_id, seeded_run.id, seeded_collection.id
        )
        await uow.commit()
    assert first is CollectionLinkResult.ADDED
    assert second is CollectionLinkResult.ALREADY_LINKED


async def test_add_collection_unknown_collection_returns_not_found(uow, seeded_run):
    async with uow:
        repo = SQLAlchemyRunRepository(uow)
        result = await repo.add_collection(
            seeded_run.workspace_id, seeded_run.id, uuid.uuid4()
        )
    assert result is CollectionLinkResult.COLLECTION_NOT_FOUND


async def test_remove_collection_returns_true_then_false(uow, seeded_run, seeded_collection):
    async with uow:
        repo = SQLAlchemyRunRepository(uow)
        await repo.add_collection(
            seeded_run.workspace_id, seeded_run.id, seeded_collection.id
        )
        await uow.commit()
    async with uow:
        repo = SQLAlchemyRunRepository(uow)
        removed = await repo.remove_collection(
            seeded_run.workspace_id, seeded_run.id, seeded_collection.id
        )
        again = await repo.remove_collection(
            seeded_run.workspace_id, seeded_run.id, seeded_collection.id
        )
        await uow.commit()
    assert removed is True
    assert again is False
```

Add `seeded_collection` fixture if absent (in the test module or a conftest) — create a `CollectionModel` row in the run's workspace:

```python
@pytest.fixture
async def seeded_collection(uow, seeded_run):
    from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
        CollectionModel,
    )

    cid = uuid.uuid4()
    async with uow:
        uow.session.add(
            CollectionModel(
                id=cid,
                workspace_id=seeded_run.workspace_id,
                name="Kinase Set",
                created_by=seeded_run.operator,
                type="library",
                visibility="private",
                version=1,
            )
        )
        await uow.commit()

    class _C:
        id = cid

    return _C()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/integration/persistence/screening/test_run_collection_links.py -v`
Expected: FAIL — `AttributeError: 'SQLAlchemyRunRepository' object has no attribute 'add_collection'`

- [ ] **Step 3: Implement the methods** (mirror `add_target`/`remove_target`)

Add imports near the top of `run_repository.py`:

```python
from sqlalchemy.dialects.postgresql import insert as pg_insert

from cellar.domain.screening_assay.repository import CollectionLinkResult
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CollectionModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    run_collections,
)
```

(`pg_insert` and `run_collections`/`RunModel` may already be imported for the target methods — reuse the existing import lines; only add what's missing.)

Add the methods to the class (model the dual-side `_owns` workspace check on `add_target`):

```python
    async def add_collection(
        self, workspace_id: uuid.UUID, run_id: uuid.UUID, collection_id: uuid.UUID
    ) -> CollectionLinkResult:
        if not await self._owns(RunModel, run_id, workspace_id):
            return CollectionLinkResult.OWNER_NOT_FOUND
        if not await self._owns(CollectionModel, collection_id, workspace_id):
            return CollectionLinkResult.COLLECTION_NOT_FOUND
        stmt = (
            pg_insert(run_collections)
            .values(run_id=run_id, collection_id=collection_id)
            .on_conflict_do_nothing()
        )
        result = await self._uow.session.execute(stmt)
        return (
            CollectionLinkResult.ADDED
            if result.rowcount
            else CollectionLinkResult.ALREADY_LINKED
        )

    async def remove_collection(
        self, workspace_id: uuid.UUID, run_id: uuid.UUID, collection_id: uuid.UUID
    ) -> bool:
        if not await self._owns(RunModel, run_id, workspace_id):
            return False
        stmt = delete(run_collections).where(
            run_collections.c.run_id == run_id,
            run_collections.c.collection_id == collection_id,
        )
        result = await self._uow.session.execute(stmt)
        return bool(result.rowcount)
```

(Confirm `delete` is imported from `sqlalchemy` at the top — `remove_target` uses it, so it is. `_owns` is the shared base-repo helper used by `add_target`.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/integration/persistence/screening/test_run_collection_links.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/run_repository.py backend/tests/integration/persistence/screening/test_run_collection_links.py
git commit -m "feat(screening): run repo add_collection/remove_collection"
```

---

### Task 6: Coverage read model (`coverage_query.py`)

**Files:**
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/coverage_query.py`
- Test: `backend/tests/integration/persistence/screening/test_coverage_query.py`

- [ ] **Step 1: Write the failing integration test** (the correctness-critical tests)

```python
import uuid

import pytest

from cellar.infrastructure.persistence.sqlalchemy.screening_assay.coverage_query import (
    SQLAlchemyCollectionCoverageQuery,
)

pytestmark = pytest.mark.asyncio


# Fixtures expected (build via existing seed helpers):
#   ws_id, protocol_id
#   collection C with 4 members: m1, m2, m3, m4  (total = 4)
#   run A attaches C, has readouts for m1, m2          (covered = 2)
#   run B attaches C, has readouts for m2, m3          (covered = 2)
#   run X does NOT attach C but has a readout for m4    (must NOT count)
#   one readout row in run A with molecule_id = NULL    (must not break gap)


async def test_run_coverage_counts_distinct_members(uow, coverage_seed):
    s = coverage_seed
    async with uow:
        q = SQLAlchemyCollectionCoverageQuery(uow)
        by_run = await q.run_coverage(s.ws_id, [s.run_a, s.run_b])
    cov_a = next(c for c in by_run[s.run_a] if c.ref.id == s.collection_id)
    assert (cov_a.covered, cov_a.total) == (2, 4)
    assert cov_a.ref.name == "Kinase Set"
    assert cov_a.ref.type == "library"


async def test_protocol_coverage_unions_attaching_runs_only(uow, coverage_seed):
    s = coverage_seed
    async with uow:
        q = SQLAlchemyCollectionCoverageQuery(uow)
        rollup = await q.protocol_coverage(s.ws_id, s.protocol_id)
    eff = next(e for e in rollup if e.ref.id == s.collection_id)
    # union(m1,m2) ∪ (m2,m3) = {m1,m2,m3} = 3 ; m4 from non-attaching run X excluded
    assert (eff.covered, eff.total, eff.run_count) == (3, 4, 2)


async def test_run_gap_lists_unscreened_members(uow, coverage_seed):
    s = coverage_seed
    async with uow:
        q = SQLAlchemyCollectionCoverageQuery(uow)
        gap = await q.run_gap(s.ws_id, s.run_a, s.collection_id, offset=0, limit=100)
    # run A screened m1,m2 → gap = {m3, m4}
    assert set(gap) == {s.m3, s.m4}


async def test_protocol_gap_excludes_anything_screened_by_attaching_runs(uow, coverage_seed):
    s = coverage_seed
    async with uow:
        q = SQLAlchemyCollectionCoverageQuery(uow)
        gap = await q.protocol_gap(s.ws_id, s.protocol_id, s.collection_id, offset=0, limit=100)
    # union screened {m1,m2,m3} → gap = {m4}
    assert set(gap) == {s.m4}


async def test_empty_collection_yields_none_fraction(uow, coverage_seed_empty):
    s = coverage_seed_empty
    async with uow:
        q = SQLAlchemyCollectionCoverageQuery(uow)
        by_run = await q.run_coverage(s.ws_id, [s.run_id])
    cov = by_run[s.run_id][0]
    assert cov.total == 0
    assert cov.fraction is None
```

Build the `coverage_seed` / `coverage_seed_empty` fixtures using the existing run/readout/collection seed helpers (mirror `test_run_target_links.py` + readout-data integration fixtures). The seed MUST include: run X attaching nothing but with a readout for `m4`, and one NULL-molecule readout in run A.

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/integration/persistence/screening/test_coverage_query.py -v`
Expected: FAIL — `ModuleNotFoundError: ...coverage_query`

- [ ] **Step 3: Implement the read model**

```python
"""Live collection-coverage read model.

Joins ``run_collections`` + ``readout_data`` (screening) with
``collection_molecules`` + ``collections`` (research-org). Read-only reporting;
the write side (collection membership) stays in research-org. Every query is
workspace-scoped on both the run and the collection. See
``docs/superpowers/specs/2026-06-07-run-collection-coverage-design.md`` §4.
"""

from __future__ import annotations

import uuid

from sqlalchemy import and_, func, select

from cellar.domain.screening_assay.collection_coverage import (
    CollectionCoverage,
    CollectionRef,
    EffectiveCollectionCoverage,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CollectionModel,
    CollectionMoleculeModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    ReadoutDataModel,
    RunModel,
    run_collections,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyCollectionCoverageQuery:
    """Implements ``CollectionCoverageReader`` against PostgreSQL."""

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def _collection_sizes(
        self, collection_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        if not collection_ids:
            return {}
        stmt = (
            select(
                CollectionMoleculeModel.collection_id,
                func.count(),
            )
            .where(CollectionMoleculeModel.collection_id.in_(collection_ids))
            .group_by(CollectionMoleculeModel.collection_id)
        )
        rows = await self._uow.session.execute(stmt)
        return {row[0]: row[1] for row in rows.all()}

    async def run_coverage(
        self, workspace_id: uuid.UUID, run_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[CollectionCoverage]]:
        if not run_ids:
            return {}
        # 1) attached collections per run (ref + workspace scope)
        attach_stmt = (
            select(
                run_collections.c.run_id,
                CollectionModel.id,
                CollectionModel.name,
                CollectionModel.type,
            )
            .select_from(run_collections)
            .join(CollectionModel, CollectionModel.id == run_collections.c.collection_id)
            .where(
                run_collections.c.run_id.in_(run_ids),
                CollectionModel.workspace_id == workspace_id,
            )
        )
        attach_rows = (await self._uow.session.execute(attach_stmt)).all()

        # 2) covered = distinct screened members per (run, collection)
        covered_stmt = (
            select(
                run_collections.c.run_id,
                run_collections.c.collection_id,
                func.count(func.distinct(ReadoutDataModel.molecule_id)),
            )
            .select_from(run_collections)
            .join(
                ReadoutDataModel,
                and_(
                    ReadoutDataModel.run_id == run_collections.c.run_id,
                    ReadoutDataModel.molecule_id.is_not(None),
                ),
            )
            .join(
                CollectionMoleculeModel,
                and_(
                    CollectionMoleculeModel.collection_id
                    == run_collections.c.collection_id,
                    CollectionMoleculeModel.molecule_id == ReadoutDataModel.molecule_id,
                ),
            )
            .where(run_collections.c.run_id.in_(run_ids))
            .group_by(run_collections.c.run_id, run_collections.c.collection_id)
        )
        covered = {
            (row[0], row[1]): row[2]
            for row in (await self._uow.session.execute(covered_stmt)).all()
        }

        sizes = await self._collection_sizes(
            [r[1] for r in attach_rows]
        )

        out: dict[uuid.UUID, list[CollectionCoverage]] = {}
        for run_id, cid, name, ctype in attach_rows:
            out.setdefault(run_id, []).append(
                CollectionCoverage(
                    ref=CollectionRef(id=cid, name=name, type=ctype),
                    covered=covered.get((run_id, cid), 0),
                    total=sizes.get(cid, 0),
                )
            )
        return out

    async def protocol_coverage(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID
    ) -> list[EffectiveCollectionCoverage]:
        # distinct attached collections in this protocol (ref + run_count)
        attach_stmt = (
            select(
                CollectionModel.id,
                CollectionModel.name,
                CollectionModel.type,
                func.count(func.distinct(run_collections.c.run_id)),
            )
            .select_from(run_collections)
            .join(RunModel, RunModel.id == run_collections.c.run_id)
            .join(CollectionModel, CollectionModel.id == run_collections.c.collection_id)
            .where(
                RunModel.protocol_id == protocol_id,
                CollectionModel.workspace_id == workspace_id,
            )
            .group_by(CollectionModel.id, CollectionModel.name, CollectionModel.type)
        )
        attach_rows = (await self._uow.session.execute(attach_stmt)).all()
        if not attach_rows:
            return []

        covered_stmt = (
            select(
                run_collections.c.collection_id,
                func.count(func.distinct(ReadoutDataModel.molecule_id)),
            )
            .select_from(run_collections)
            .join(
                RunModel,
                and_(
                    RunModel.id == run_collections.c.run_id,
                    RunModel.protocol_id == protocol_id,
                ),
            )
            .join(
                ReadoutDataModel,
                and_(
                    ReadoutDataModel.run_id == run_collections.c.run_id,
                    ReadoutDataModel.molecule_id.is_not(None),
                ),
            )
            .join(
                CollectionMoleculeModel,
                and_(
                    CollectionMoleculeModel.collection_id
                    == run_collections.c.collection_id,
                    CollectionMoleculeModel.molecule_id == ReadoutDataModel.molecule_id,
                ),
            )
            .group_by(run_collections.c.collection_id)
        )
        covered = {
            row[0]: row[1]
            for row in (await self._uow.session.execute(covered_stmt)).all()
        }
        sizes = await self._collection_sizes([r[0] for r in attach_rows])

        return [
            EffectiveCollectionCoverage(
                ref=CollectionRef(id=cid, name=name, type=ctype),
                covered=covered.get(cid, 0),
                total=sizes.get(cid, 0),
                run_count=run_count,
            )
            for cid, name, ctype, run_count in attach_rows
        ]

    async def run_gap(
        self,
        workspace_id: uuid.UUID,
        run_id: uuid.UUID,
        collection_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[uuid.UUID]:
        screened = (
            select(ReadoutDataModel.molecule_id)
            .where(
                ReadoutDataModel.run_id == run_id,
                ReadoutDataModel.molecule_id == CollectionMoleculeModel.molecule_id,
            )
            .exists()
        )
        stmt = (
            select(CollectionMoleculeModel.molecule_id)
            .join(
                CollectionModel,
                CollectionMoleculeModel.collection_id == CollectionModel.id,
            )
            .where(
                CollectionMoleculeModel.collection_id == collection_id,
                CollectionModel.workspace_id == workspace_id,
                ~screened,
            )
            .order_by(CollectionMoleculeModel.added_at, CollectionMoleculeModel.molecule_id)
            .offset(offset)
            .limit(limit)
        )
        rows = await self._uow.session.execute(stmt)
        return list(rows.scalars())

    async def protocol_gap(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        collection_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[uuid.UUID]:
        screened = (
            select(ReadoutDataModel.molecule_id)
            .select_from(ReadoutDataModel)
            .join(
                run_collections,
                and_(
                    run_collections.c.run_id == ReadoutDataModel.run_id,
                    run_collections.c.collection_id == collection_id,
                ),
            )
            .join(
                RunModel,
                and_(
                    RunModel.id == ReadoutDataModel.run_id,
                    RunModel.protocol_id == protocol_id,
                ),
            )
            .where(ReadoutDataModel.molecule_id == CollectionMoleculeModel.molecule_id)
            .exists()
        )
        stmt = (
            select(CollectionMoleculeModel.molecule_id)
            .join(
                CollectionModel,
                CollectionMoleculeModel.collection_id == CollectionModel.id,
            )
            .where(
                CollectionMoleculeModel.collection_id == collection_id,
                CollectionModel.workspace_id == workspace_id,
                ~screened,
            )
            .order_by(CollectionMoleculeModel.added_at, CollectionMoleculeModel.molecule_id)
            .offset(offset)
            .limit(limit)
        )
        rows = await self._uow.session.execute(stmt)
        return list(rows.scalars())
```

> **Note:** confirm `RunModel` is the mapped class name for the `runs` table in `screening_assay/models.py` (it is referenced by the run repository). If the readout model exposes `molecule_id` as nullable, the `is_not(None)` filters and the `NOT EXISTS` equality (which never matches NULL) together guarantee null-safety.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/integration/persistence/screening/test_coverage_query.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/coverage_query.py backend/tests/integration/persistence/screening/test_coverage_query.py
git commit -m "feat(screening): live collection-coverage read model + gap queries"
```

---

# Phase 2 — Application + API

### Task 7: Run-collection use cases + events

**Files:**
- Modify: `backend/src/cellar/domain/screening_assay/events.py`
- Create: `backend/src/cellar/application/screening/manage_run_collections.py`
- Test: `backend/tests/unit/application/screening/test_manage_run_collections.py`

- [ ] **Step 1: Add the events** (next to `RunTargetAdded`/`RunTargetRemoved`)

```python
@dataclass(frozen=True, kw_only=True)
class RunCollectionAdded(DomainEvent):
    """A collection was attached to a run. Use-case-constructed, emitted only
    when a link row was actually inserted (idempotent re-adds stay silent)."""

    collection_id: uuid.UUID
    user_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class RunCollectionRemoved(DomainEvent):
    collection_id: uuid.UUID
    user_id: uuid.UUID | None = None
```

- [ ] **Step 2: Write the failing use-case test**

```python
import uuid

import pytest
from returns.result import Failure, Success

from cellar.application.screening.manage_run_collections import (
    AddRunCollection,
    AddRunCollectionCommand,
)
from cellar.domain.screening_assay.events import RunCollectionAdded
from cellar.domain.screening_assay.repository import CollectionLinkResult
from cellar.domain.shared.errors import ConflictError

pytestmark = pytest.mark.asyncio


class _Repo:
    def __init__(self, locked=False, link=CollectionLinkResult.ADDED):
        self._locked = locked
        self._link = link

    async def find_lock_state(self, ws, run_id):
        return self._locked

    async def add_collection(self, ws, run_id, collection_id):
        return self._link


async def test_add_collection_blocked_on_locked_run(uow_factory, fake_dispatcher, editor_auth):
    uc = AddRunCollection(uow_factory(), _Repo(locked=True), fake_dispatcher)
    cmd = AddRunCollectionCommand(
        workspace_id=editor_auth.workspace_id, run_id=uuid.uuid4(), collection_id=uuid.uuid4()
    )
    result = await uc(cmd, auth=editor_auth)
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), ConflictError)


async def test_add_collection_emits_event_when_newly_linked(
    uow_factory, fake_dispatcher, editor_auth
):
    uc = AddRunCollection(uow_factory(), _Repo(link=CollectionLinkResult.ADDED), fake_dispatcher)
    cmd = AddRunCollectionCommand(
        workspace_id=editor_auth.workspace_id, run_id=uuid.uuid4(), collection_id=uuid.uuid4()
    )
    result = await uc(cmd, auth=editor_auth)
    assert isinstance(result, Success)
    assert any(isinstance(e, RunCollectionAdded) for e in fake_dispatcher.dispatched)


async def test_add_collection_silent_on_idempotent_readd(
    uow_factory, fake_dispatcher, editor_auth
):
    uc = AddRunCollection(
        uow_factory(), _Repo(link=CollectionLinkResult.ALREADY_LINKED), fake_dispatcher
    )
    cmd = AddRunCollectionCommand(
        workspace_id=editor_auth.workspace_id, run_id=uuid.uuid4(), collection_id=uuid.uuid4()
    )
    await uc(cmd, auth=editor_auth)
    assert not any(isinstance(e, RunCollectionAdded) for e in fake_dispatcher.dispatched)
```

Reuse the existing `manage_run_targets` unit-test fixtures (`uow_factory`, `fake_dispatcher`, `editor_auth`) — copy/adapt from `tests/unit/application/screening/test_manage_run_targets.py`.

- [ ] **Step 3: Run to verify it fails**

Run: `cd backend && uv run pytest tests/unit/application/screening/test_manage_run_collections.py -v`
Expected: FAIL — `ModuleNotFoundError: ...manage_run_collections`

- [ ] **Step 4: Write the use cases** (direct mirror of `manage_run_targets.py`)

```python
"""Run-collection association use cases — attach / detach a collection on a run.

Mirrors ``manage_run_targets``: collections are an M2M association (not aggregate
state), so the lock guard uses a column-only query, the audit event is
constructed here, and there is no version bump on idempotent edits. Coverage is
computed live elsewhere (``coverage_query``); these use cases only manage links.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.events import (
    RunCollectionAdded,
    RunCollectionRemoved,
)
from cellar.domain.screening_assay.repository import CollectionLinkResult, RunRepository
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class AddRunCollectionCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    collection_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class RemoveRunCollectionCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    collection_id: uuid.UUID


class AddRunCollection:
    """Attach a collection to a run (idempotent). Blocked when the run is locked."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: RunRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: AddRunCollectionCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            is_locked = await self._repo.find_lock_state(input.workspace_id, input.run_id)
            if is_locked is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            if is_locked:
                return Failure(ConflictError("Cannot modify a locked run — unlock it first"))
            link = await self._repo.add_collection(
                input.workspace_id, input.run_id, input.collection_id
            )
            if link is CollectionLinkResult.COLLECTION_NOT_FOUND:
                return Failure(NotFoundError("Collection", str(input.collection_id)))
            if link is CollectionLinkResult.OWNER_NOT_FOUND:
                return Failure(NotFoundError("Run", str(input.run_id)))
            events = await self._uow.commit()

        if link is CollectionLinkResult.ADDED:
            events.append(
                RunCollectionAdded(
                    aggregate_id=input.run_id,
                    aggregate_type="Run",
                    workspace_id=input.workspace_id,
                    collection_id=input.collection_id,
                    user_id=auth.user_id if auth else None,
                )
            )
        await self._dispatcher.dispatch_all(events)
        return Success(None)


class RemoveRunCollection:
    """Detach a collection from a run. Blocked when the run is locked."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: RunRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: RemoveRunCollectionCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            is_locked = await self._repo.find_lock_state(input.workspace_id, input.run_id)
            if is_locked is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            if is_locked:
                return Failure(ConflictError("Cannot modify a locked run — unlock it first"))
            removed = await self._repo.remove_collection(
                input.workspace_id, input.run_id, input.collection_id
            )
            events = await self._uow.commit()

        if removed:
            events.append(
                RunCollectionRemoved(
                    aggregate_id=input.run_id,
                    aggregate_type="Run",
                    workspace_id=input.workspace_id,
                    collection_id=input.collection_id,
                    user_id=auth.user_id if auth else None,
                )
            )
        await self._dispatcher.dispatch_all(events)
        return Success(None)
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd backend && uv run pytest tests/unit/application/screening/test_manage_run_collections.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/domain/screening_assay/events.py backend/src/cellar/application/screening/manage_run_collections.py backend/tests/unit/application/screening/test_manage_run_collections.py
git commit -m "feat(screening): AddRunCollection/RemoveRunCollection use cases + events"
```

---

### Task 8: Resolve coverage use cases + gap use cases

**Files:**
- Create: `backend/src/cellar/application/screening/resolve_collection_coverage.py`
- Create: `backend/src/cellar/application/screening/get_collection_gap.py`
- Test: `backend/tests/unit/application/screening/test_resolve_collection_coverage.py`

- [ ] **Step 1: Write the failing test** (ownership 404 for protocol coverage)

```python
import uuid

import pytest
from returns.result import Failure, Success

from cellar.application.screening.resolve_collection_coverage import (
    GetProtocolCollectionCoverage,
    GetProtocolCollectionCoverageQuery,
)
from cellar.domain.screening_assay.collection_coverage import (
    CollectionRef,
    EffectiveCollectionCoverage,
)
from cellar.domain.shared.errors import NotFoundError

pytestmark = pytest.mark.asyncio


class _ProtoRepo:
    def __init__(self, exists):
        self._exists = exists

    async def find_lock_state(self, ws, protocol_id):
        return False if self._exists else None


class _Reader:
    async def protocol_coverage(self, ws, protocol_id):
        return [
            EffectiveCollectionCoverage(
                ref=CollectionRef(id=uuid.uuid4(), name="Kinase Set", type="library"),
                covered=3,
                total=4,
                run_count=2,
            )
        ]


async def test_foreign_protocol_404s(uow_factory, viewer_auth):
    uc = GetProtocolCollectionCoverage(uow_factory(), _ProtoRepo(exists=False), _Reader())
    q = GetProtocolCollectionCoverageQuery(
        workspace_id=viewer_auth.workspace_id, protocol_id=uuid.uuid4()
    )
    result = await uc(q, auth=viewer_auth)
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), NotFoundError)


async def test_returns_rollup_for_owned_protocol(uow_factory, viewer_auth):
    uc = GetProtocolCollectionCoverage(uow_factory(), _ProtoRepo(exists=True), _Reader())
    q = GetProtocolCollectionCoverageQuery(
        workspace_id=viewer_auth.workspace_id, protocol_id=uuid.uuid4()
    )
    result = await uc(q, auth=viewer_auth)
    assert isinstance(result, Success)
    assert result.unwrap()[0].fraction == 0.75
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/unit/application/screening/test_resolve_collection_coverage.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write `resolve_collection_coverage.py`**

```python
"""Read use cases for collection coverage: per-run resolution + protocol rollup.

``ResolveRunCollections`` populates the ``collections`` field on run responses
(single-run GET and list). ``GetProtocolCollectionCoverage`` powers the protocol
rollup, with the same ownership-first 404 discipline as ``GetProtocolTargets``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_same_workspace,
    require_workspace_role,
)
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.collection_coverage import (
    CollectionCoverage,
    EffectiveCollectionCoverage,
)
from cellar.domain.screening_assay.repository import (
    CollectionCoverageReader,
    ProtocolRepository,
)
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class ResolveRunCollectionsQuery(Query):
    workspace_id: uuid.UUID
    run_ids: tuple[uuid.UUID, ...]


class ResolveRunCollections:
    """Coverage per attached collection for the given runs."""

    def __init__(self, uow: UnitOfWork, reader: CollectionCoverageReader) -> None:
        self._uow = uow
        self._reader = reader

    async def __call__(
        self, input: ResolveRunCollectionsQuery, auth: AuthContext | None = None
    ) -> Result[dict[uuid.UUID, list[CollectionCoverage]], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            data = await self._reader.run_coverage(
                input.workspace_id, list(input.run_ids)
            )
        return Success(data)


@dataclass(frozen=True, kw_only=True)
class GetProtocolCollectionCoverageQuery(Query):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID


class GetProtocolCollectionCoverage:
    """Cumulative coverage per collection across a protocol's attaching runs."""

    def __init__(
        self,
        uow: UnitOfWork,
        protocol_repo: ProtocolRepository,
        reader: CollectionCoverageReader,
    ) -> None:
        self._uow = uow
        self._protocol_repo = protocol_repo
        self._reader = reader

    async def __call__(
        self, input: GetProtocolCollectionCoverageQuery, auth: AuthContext | None = None
    ) -> Result[list[EffectiveCollectionCoverage], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            state = await self._protocol_repo.find_lock_state(
                input.workspace_id, input.protocol_id
            )
            if state is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            rollup = await self._reader.protocol_coverage(
                input.workspace_id, input.protocol_id
            )
        return Success(rollup)
```

- [ ] **Step 4: Write `get_collection_gap.py`**

```python
"""Gap use cases: collection members not yet screened (run-level + protocol)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_same_workspace,
    require_workspace_role,
)
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.repository import (
    CollectionCoverageReader,
    ProtocolRepository,
    RunRepository,
)
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetRunCollectionGapQuery(Query):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    collection_id: uuid.UUID
    offset: int = 0
    limit: int = 100


class GetRunCollectionGap:
    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        reader: CollectionCoverageReader,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._reader = reader

    async def __call__(
        self, input: GetRunCollectionGapQuery, auth: AuthContext | None = None
    ) -> Result[list[uuid.UUID], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            state = await self._run_repo.find_lock_state(input.workspace_id, input.run_id)
            if state is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            ids = await self._reader.run_gap(
                input.workspace_id,
                input.run_id,
                input.collection_id,
                offset=input.offset,
                limit=input.limit,
            )
        return Success(ids)


@dataclass(frozen=True, kw_only=True)
class GetProtocolCollectionGapQuery(Query):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    collection_id: uuid.UUID
    offset: int = 0
    limit: int = 100


class GetProtocolCollectionGap:
    def __init__(
        self,
        uow: UnitOfWork,
        protocol_repo: ProtocolRepository,
        reader: CollectionCoverageReader,
    ) -> None:
        self._uow = uow
        self._protocol_repo = protocol_repo
        self._reader = reader

    async def __call__(
        self, input: GetProtocolCollectionGapQuery, auth: AuthContext | None = None
    ) -> Result[list[uuid.UUID], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            state = await self._protocol_repo.find_lock_state(
                input.workspace_id, input.protocol_id
            )
            if state is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            ids = await self._reader.protocol_gap(
                input.workspace_id,
                input.protocol_id,
                input.collection_id,
                offset=input.offset,
                limit=input.limit,
            )
        return Success(ids)
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd backend && uv run pytest tests/unit/application/screening/test_resolve_collection_coverage.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/application/screening/resolve_collection_coverage.py backend/src/cellar/application/screening/get_collection_gap.py backend/tests/unit/application/screening/test_resolve_collection_coverage.py
git commit -m "feat(screening): resolve-coverage + gap use cases"
```

---

### Task 9: Extend `ListRunsWithCounts` + `create_run` with collections

**Files:**
- Modify: `backend/src/cellar/application/screening/list_runs_with_counts.py`
- Modify: `backend/src/cellar/application/screening/create_run.py`
- Test: `backend/tests/unit/application/screening/test_list_runs_with_counts.py` (extend)

- [ ] **Step 1: Extend `RunWithCounts` + the use case**

In `list_runs_with_counts.py`, add the import and field, inject the reader, and populate coverage:

```python
from cellar.domain.screening_assay.collection_coverage import CollectionCoverage
from cellar.domain.screening_assay.repository import (
    CollectionCoverageReader,
    ReadoutDataRepository,
    RunRepository,
)
```

```python
@dataclass(frozen=True)
class RunWithCounts:
    run: Run
    molecule_count: int
    targets: list[TargetRef] = field(default_factory=list)
    collections: list[CollectionCoverage] = field(default_factory=list)
```

```python
    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        readout_data_repo: ReadoutDataRepository,
        coverage_reader: CollectionCoverageReader,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._rd_repo = readout_data_repo
        self._coverage_reader = coverage_reader
```

Inside `__call__`, after `targets = ...`:

```python
            run_ids = [r.id for r in runs]
            coverage = await self._coverage_reader.run_coverage(
                input.workspace_id, run_ids
            )
            return Success(
                [
                    RunWithCounts(
                        run=r,
                        molecule_count=counts.get(r.id, 0),
                        targets=targets.get(r.id, []),
                        collections=coverage.get(r.id, []),
                    )
                    for r in runs
                ]
            )
```

- [ ] **Step 2: Add `collection_ids` to `create_run`**

In `create_run.py`, add to the command:

```python
    collection_ids: list[uuid.UUID] = field(default_factory=list)
```

After the run is persisted (where `target_ids` are written — find the existing loop that calls `repo.add_target` for each id; if create_run writes targets via the repo, mirror it), add:

```python
            for collection_id in input.collection_ids:
                await self._repo.add_collection(
                    input.workspace_id, run.id, collection_id
                )
```

> If `create_run` does NOT currently write `target_ids` via the repo (e.g. it's handled by the route), match whatever pattern `target_ids` uses — keep the two symmetric. Inspect `create_run.py` first.

- [ ] **Step 3: Run existing + extended tests**

Run: `cd backend && uv run pytest tests/unit/application/screening/test_list_runs_with_counts.py tests/unit/application/screening/test_create_run.py -v`
Expected: PASS (update fixtures to pass a fake `coverage_reader` returning `{}`)

- [ ] **Step 4: Commit**

```bash
git add backend/src/cellar/application/screening/list_runs_with_counts.py backend/src/cellar/application/screening/create_run.py backend/tests/unit/application/screening/test_list_runs_with_counts.py backend/tests/unit/application/screening/test_create_run.py
git commit -m "feat(screening): runs list + create accept/return collection coverage"
```

---

### Task 10: DI wiring + dependency aliases

**Files:**
- Modify: `backend/src/cellar/infrastructure/di/_screening.py`
- Modify: `backend/src/cellar/interface/dependencies/_screening.py`

- [ ] **Step 1: Register the use cases** in `_screening.py` (DI)

Add imports:

```python
from cellar.application.screening.get_collection_gap import (
    GetProtocolCollectionGap,
    GetRunCollectionGap,
)
from cellar.application.screening.manage_run_collections import (
    AddRunCollection,
    RemoveRunCollection,
)
from cellar.application.screening.resolve_collection_coverage import (
    GetProtocolCollectionCoverage,
    ResolveRunCollections,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.coverage_query import (
    SQLAlchemyCollectionCoverageQuery,
)
```

Register the link commands with the existing `_run_cmd` closure, and add dedicated factories for the reader-backed use cases (place after the `AddRunTarget`/`RemoveRunTarget` lines):

```python
    container.define(AddRunCollection, _run_cmd(AddRunCollection))
    container.define(RemoveRunCollection, _run_cmd(RemoveRunCollection))

    def _resolve_run_collections(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ResolveRunCollections(uow, SQLAlchemyCollectionCoverageQuery(uow))

    container.define(ResolveRunCollections, _resolve_run_collections)

    def _protocol_collection_coverage(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetProtocolCollectionCoverage(
            uow,
            SQLAlchemyProtocolRepository(uow),
            SQLAlchemyCollectionCoverageQuery(uow),
        )

    container.define(GetProtocolCollectionCoverage, _protocol_collection_coverage)

    def _run_collection_gap(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetRunCollectionGap(
            uow, SQLAlchemyRunRepository(uow), SQLAlchemyCollectionCoverageQuery(uow)
        )

    container.define(GetRunCollectionGap, _run_collection_gap)

    def _protocol_collection_gap(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetProtocolCollectionGap(
            uow,
            SQLAlchemyProtocolRepository(uow),
            SQLAlchemyCollectionCoverageQuery(uow),
        )

    container.define(GetProtocolCollectionGap, _protocol_collection_gap)
```

> `SQLAlchemyProtocolRepository` is already imported in this module (used by the protocol factories). Confirm the exact class name there and reuse it.

Update the `_list_runs_with_counts` factory to pass the reader:

```python
    def _list_runs_with_counts(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListRunsWithCounts(
            uow=uow,
            run_repo=SQLAlchemyRunRepository(uow),
            readout_data_repo=SQLAlchemyReadoutDataRepository(uow),
            coverage_reader=SQLAlchemyCollectionCoverageQuery(uow),
        )
```

- [ ] **Step 2: Add `*Dep` aliases** in `interface/dependencies/_screening.py`

```python
from cellar.application.screening.get_collection_gap import (
    GetProtocolCollectionGap,
    GetRunCollectionGap,
)
from cellar.application.screening.manage_run_collections import (
    AddRunCollection,
    RemoveRunCollection,
)
from cellar.application.screening.resolve_collection_coverage import (
    GetProtocolCollectionCoverage,
    ResolveRunCollections,
)
```

```python
AddRunCollectionDep = Annotated[AddRunCollection, Depends(_get_use_case(AddRunCollection))]
RemoveRunCollectionDep = Annotated[
    RemoveRunCollection, Depends(_get_use_case(RemoveRunCollection))
]
ResolveRunCollectionsDep = Annotated[
    ResolveRunCollections, Depends(_get_use_case(ResolveRunCollections))
]
GetProtocolCollectionCoverageDep = Annotated[
    GetProtocolCollectionCoverage, Depends(_get_use_case(GetProtocolCollectionCoverage))
]
GetRunCollectionGapDep = Annotated[
    GetRunCollectionGap, Depends(_get_use_case(GetRunCollectionGap))
]
GetProtocolCollectionGapDep = Annotated[
    GetProtocolCollectionGap, Depends(_get_use_case(GetProtocolCollectionGap))
]
```

Add all six names to the module's `__all__`.

- [ ] **Step 3: Verify the container builds**

Run: `cd backend && uv run python -c "from cellar.infrastructure.di import build_container; c = build_container(); from cellar.application.screening.manage_run_collections import AddRunCollection; print(type(c[AddRunCollection]).__name__)"`
Expected: `AddRunCollection` (adjust the `build_container` import to the actual factory name in `infrastructure/di/__init__.py`)

- [ ] **Step 4: Commit**

```bash
git add backend/src/cellar/infrastructure/di/_screening.py backend/src/cellar/interface/dependencies/_screening.py
git commit -m "feat(screening): DI wiring for collection use cases + coverage reader"
```

---

### Task 11: API endpoints + response models

**Files:**
- Create: `backend/src/cellar/interface/routes/_collection_coverage.py`
- Modify: `backend/src/cellar/interface/routes/runs.py`
- Modify: `backend/src/cellar/interface/routes/protocols.py`
- Test: `backend/tests/api/test_run_collections.py`, `backend/tests/api/test_protocol_collection_coverage.py`

- [ ] **Step 1: Write the response models** (`_collection_coverage.py`, mirror `_target_refs.py`)

```python
"""Shared API response models for collection coverage (runs + protocols)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from cellar.domain.screening_assay.collection_coverage import (
    CollectionCoverage,
    EffectiveCollectionCoverage,
)


class CollectionCoverageResponse(BaseModel):
    """A run's coverage of one attached collection."""

    id: uuid.UUID
    name: str
    type: str
    covered: int
    total: int
    fraction: float | None

    @classmethod
    def from_coverage(cls, c: CollectionCoverage) -> CollectionCoverageResponse:
        return cls(
            id=c.ref.id,
            name=c.ref.name,
            type=c.ref.type,
            covered=c.covered,
            total=c.total,
            fraction=c.fraction,
        )


class EffectiveCollectionCoverageResponse(CollectionCoverageResponse):
    """Protocol rollup: adds the count of attaching runs."""

    run_count: int

    @classmethod
    def from_effective(
        cls, e: EffectiveCollectionCoverage
    ) -> EffectiveCollectionCoverageResponse:
        return cls(
            id=e.ref.id,
            name=e.ref.name,
            type=e.ref.type,
            covered=e.covered,
            total=e.total,
            fraction=e.fraction,
            run_count=e.run_count,
        )
```

- [ ] **Step 2: Wire `RunResponse` + endpoints in `runs.py`**

Add imports:

```python
from cellar.application.screening.get_collection_gap import GetRunCollectionGapQuery
from cellar.application.screening.manage_run_collections import (
    AddRunCollectionCommand,
    RemoveRunCollectionCommand,
)
from cellar.application.screening.resolve_collection_coverage import (
    ResolveRunCollectionsQuery,
)
from cellar.interface.dependencies import (
    AddRunCollectionDep,
    GetRunCollectionGapDep,
    RemoveRunCollectionDep,
    ResolveRunCollectionsDep,
)
from cellar.interface.routes._collection_coverage import CollectionCoverageResponse
```

Add the field to `RunResponse` (after `targets`):

```python
    collections: list[CollectionCoverageResponse] = []
```

Add `collections` to `from_domain` signature + body:

```python
        collections: list[CollectionCoverageResponse] | None = None,
```
```python
            collections=collections or [],
```

Add the single-run resolution helper (mirror `_run_targets`):

```python
async def _run_collections(
    coverage_uc: Any, auth: Any, run_id: uuid.UUID
) -> list[CollectionCoverageResponse]:
    result = await coverage_uc(
        ResolveRunCollectionsQuery(workspace_id=auth.workspace_id, run_ids=(run_id,)),
        auth=auth,
    )
    covs = result_to_response(result).get(run_id, [])
    return [CollectionCoverageResponse.from_coverage(c) for c in covs]
```

In the GET-run handler, accept `coverage: ResolveRunCollectionsDep` and pass `collections=await _run_collections(coverage, auth, run_id)` into `RunResponse.from_domain`. In the **list** handler (which maps `RunWithCounts`), pass `collections=[CollectionCoverageResponse.from_coverage(c) for c in rc.collections]`.

Add `collection_ids` to `CreateRunRequest`:

```python
    collection_ids: list[uuid.UUID] = []
```

And thread it into the `CreateRunCommand(...)` construction in the create handler (mirror `target_ids`).

Add the endpoints (after the run-target routes):

```python
@router.post("/runs/{run_id}/collections/{collection_id}", status_code=204)
async def add_run_collection(
    run_id: uuid.UUID,
    collection_id: uuid.UUID,
    auth: AuthDep,
    uc: AddRunCollectionDep,
) -> Response:
    """Attach a collection to a run (idempotent)."""
    result = await uc(
        AddRunCollectionCommand(
            workspace_id=auth.workspace_id, run_id=run_id, collection_id=collection_id
        ),
        auth=auth,
    )
    result_to_response(result)
    return Response(status_code=204)


@router.delete("/runs/{run_id}/collections/{collection_id}", status_code=204)
async def remove_run_collection(
    run_id: uuid.UUID,
    collection_id: uuid.UUID,
    auth: AuthDep,
    uc: RemoveRunCollectionDep,
) -> Response:
    """Detach a collection from a run."""
    result = await uc(
        RemoveRunCollectionCommand(
            workspace_id=auth.workspace_id, run_id=run_id, collection_id=collection_id
        ),
        auth=auth,
    )
    result_to_response(result)
    return Response(status_code=204)


@router.get("/runs/{run_id}/collections/{collection_id}/gap", response_model=list[uuid.UUID])
async def run_collection_gap(
    run_id: uuid.UUID,
    collection_id: uuid.UUID,
    auth: AuthDep,
    uc: GetRunCollectionGapDep,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> list[uuid.UUID]:
    """Collection members not yet screened in this run (paginated)."""
    result = await uc(
        GetRunCollectionGapQuery(
            workspace_id=auth.workspace_id,
            run_id=run_id,
            collection_id=collection_id,
            offset=offset,
            limit=limit,
        ),
        auth=auth,
    )
    return result_to_response(result)
```

- [ ] **Step 3: Wire the protocol endpoints in `protocols.py`**

Add imports:

```python
from cellar.application.screening.get_collection_gap import (
    GetProtocolCollectionGapQuery,
)
from cellar.application.screening.resolve_collection_coverage import (
    GetProtocolCollectionCoverageQuery,
)
from cellar.interface.dependencies import (
    GetProtocolCollectionCoverageDep,
    GetProtocolCollectionGapDep,
)
from cellar.interface.routes._collection_coverage import (
    EffectiveCollectionCoverageResponse,
)
```

```python
@router.get(
    "/protocols/{protocol_id}/collection-coverage",
    response_model=list[EffectiveCollectionCoverageResponse],
    tags=["protocols"],
)
async def list_protocol_collection_coverage(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    uc: GetProtocolCollectionCoverageDep,
) -> list[EffectiveCollectionCoverageResponse]:
    """Cumulative coverage per attached collection across the protocol's runs."""
    result = await uc(
        GetProtocolCollectionCoverageQuery(
            workspace_id=auth.workspace_id, protocol_id=protocol_id
        ),
        auth=auth,
    )
    return [
        EffectiveCollectionCoverageResponse.from_effective(e)
        for e in result_to_response(result)
    ]


@router.get(
    "/protocols/{protocol_id}/collections/{collection_id}/gap",
    response_model=list[uuid.UUID],
    tags=["protocols"],
)
async def protocol_collection_gap(
    protocol_id: uuid.UUID,
    collection_id: uuid.UUID,
    auth: AuthDep,
    uc: GetProtocolCollectionGapDep,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> list[uuid.UUID]:
    """Collection members not yet screened by any attaching run (paginated)."""
    result = await uc(
        GetProtocolCollectionGapQuery(
            workspace_id=auth.workspace_id,
            protocol_id=protocol_id,
            collection_id=collection_id,
            offset=offset,
            limit=limit,
        ),
        auth=auth,
    )
    return result_to_response(result)
```

(Confirm `Query` is imported from `fastapi` in `protocols.py`; if not, add it.)

- [ ] **Step 4: Write the API tests**

```python
import pytest

pytestmark = pytest.mark.asyncio


async def test_attach_collection_then_run_response_shows_coverage(
    client, auth_headers, seeded_run, seeded_collection_with_members, seeded_readouts
):
    run_id, collection_id = seeded_run.id, seeded_collection_with_members.id
    r = await client.post(
        f"/api/v1/runs/{run_id}/collections/{collection_id}", headers=auth_headers
    )
    assert r.status_code == 204

    got = await client.get(f"/api/v1/runs/{run_id}", headers=auth_headers)
    body = got.json()
    cov = next(c for c in body["collections"] if c["id"] == str(collection_id))
    assert cov["total"] == 4
    assert cov["covered"] == 2
    assert cov["fraction"] == 0.5


async def test_attach_is_idempotent_returns_204_twice(
    client, auth_headers, seeded_run, seeded_collection
):
    url = f"/api/v1/runs/{seeded_run.id}/collections/{seeded_collection.id}"
    assert (await client.post(url, headers=auth_headers)).status_code == 204
    assert (await client.post(url, headers=auth_headers)).status_code == 204


async def test_attach_unknown_collection_404(client, auth_headers, seeded_run):
    import uuid

    r = await client.post(
        f"/api/v1/runs/{seeded_run.id}/collections/{uuid.uuid4()}", headers=auth_headers
    )
    assert r.status_code == 404


async def test_run_gap_lists_unscreened(
    client, auth_headers, seeded_run, seeded_collection_with_members, seeded_readouts
):
    run_id, collection_id = seeded_run.id, seeded_collection_with_members.id
    await client.post(
        f"/api/v1/runs/{run_id}/collections/{collection_id}", headers=auth_headers
    )
    r = await client.get(
        f"/api/v1/runs/{run_id}/collections/{collection_id}/gap", headers=auth_headers
    )
    assert r.status_code == 200
    assert len(r.json()) == 2  # 4 members − 2 screened
```

(Build/reuse fixtures from the existing run-target API tests + readout fixtures. `test_protocol_collection_coverage.py` mirrors these against `/protocols/{id}/collection-coverage` asserting `run_count` and cumulative `covered`.)

- [ ] **Step 5: Run the API tests**

Run: `cd backend && uv run pytest tests/api/test_run_collections.py tests/api/test_protocol_collection_coverage.py -v`
Expected: PASS

- [ ] **Step 6: Run the full backend suite + lint**

Run: `cd backend && uv run pytest -q && uv run ruff check src && uv run ruff format --check src`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add backend/src/cellar/interface/routes/_collection_coverage.py backend/src/cellar/interface/routes/runs.py backend/src/cellar/interface/routes/protocols.py backend/tests/api/test_run_collections.py backend/tests/api/test_protocol_collection_coverage.py
git commit -m "feat(screening): run/protocol collection-coverage + gap API"
```

---

# Phase 3 — Frontend

### Task 12: Regenerate API types

**Files:**
- Modify: `frontend/src/shared/lib/api/model/*` (generated), `frontend/src/shared/lib/api/model/index.ts`

- [ ] **Step 1: Start the backend, regenerate**

Run: `cd backend && uv run uvicorn cellar.interface.app:app --port 8000 &` then `cd frontend && pnpm generate:api`
Expected: new generated types `CollectionCoverageResponse`, `EffectiveCollectionCoverageResponse`; `RunResponse` gains `collections`; `CreateRunRequest` gains `collection_ids`.

- [ ] **Step 2: Review the diff** (orval rewrites the whole `model/` dir; changes should be additive)

Run: `git diff --stat frontend/src/shared/lib/api/model/`
Expected: new files + additive field changes only. If a schema file was removed, manually prune its line from `model/index.ts`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/shared/lib/api/model
git commit -m "chore(api): regenerate orval types for collection coverage"
```

---

### Task 13: Collection-type icons

**Files:**
- Create: `frontend/src/features/research-organization/components/collection/collection-type-icon.tsx`
- Modify: `frontend/src/features/research-organization/components/collection/collection-header.tsx`
- Modify: `frontend/src/features/research-organization/components/collection-list.tsx`
- Test: `frontend/src/features/research-organization/components/collection/collection-type-icon.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { COLLECTION_TYPE_ICONS, CollectionTypeIcon } from "./collection-type-icon";

describe("CollectionTypeIcon", () => {
  it("maps every collection type to an icon", () => {
    const types = [
      "generic",
      "reference_set",
      "library",
      "hit_list",
      "series",
      "distribution_set",
    ] as const;
    for (const t of types) expect(COLLECTION_TYPE_ICONS[t]).toBeTruthy();
  });

  it("renders an svg", () => {
    const { container } = render(<CollectionTypeIcon type="library" />);
    expect(container.querySelector("svg")).not.toBeNull();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && pnpm vitest run src/features/research-organization/components/collection/collection-type-icon.test.tsx`
Expected: FAIL — module not found

- [ ] **Step 3: Write the icon map** (the approved mapping)

```tsx
import { cn } from "@/shared/lib/utils";
import {
  BadgeCheck,
  Boxes,
  Flame,
  GitBranch,
  Library,
  type LucideIcon,
  Send,
} from "lucide-react";
import type { CollectionType } from "../../types";

/** Approved per-type iconography (see coverage design §10). `Target`/`Crosshair`
 *  are reserved for the Targets feature; `Share2` is avoided (reads as "shared"
 *  visibility) — distribution uses `Send`. */
export const COLLECTION_TYPE_ICONS: Record<CollectionType, LucideIcon> = {
  generic: Boxes,
  reference_set: BadgeCheck,
  library: Library,
  hit_list: Flame,
  series: GitBranch,
  distribution_set: Send,
};

export function CollectionTypeIcon({
  type,
  className,
}: {
  type: CollectionType;
  className?: string;
}) {
  const Icon = COLLECTION_TYPE_ICONS[type] ?? Boxes;
  return <Icon className={cn("h-3.5 w-3.5", className)} aria-hidden />;
}
```

- [ ] **Step 4: Render it in the type badges**

In `collection-header.tsx`, update the type badge (lines ~53-57):

```tsx
          {collection.type && (
            <Badge variant="outline" className="gap-1 text-xs">
              <CollectionTypeIcon type={collection.type} />
              {COLLECTION_TYPE_LABELS[collection.type]}
            </Badge>
          )}
```

Add `import { CollectionTypeIcon } from "./collection-type-icon";`. Apply the same change to the Type column/badge cell renderer in `collection-list.tsx`.

- [ ] **Step 5: Run the test + the collections feature tests**

Run: `cd frontend && pnpm vitest run src/features/research-organization/components/collection`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/research-organization/components/collection/collection-type-icon.tsx frontend/src/features/research-organization/components/collection/collection-type-icon.test.tsx frontend/src/features/research-organization/components/collection/collection-header.tsx frontend/src/features/research-organization/components/collection-list.tsx
git commit -m "feat(collections): per-type icons across collection surfaces"
```

---

### Task 14: `CoverageBar` + `CoverageGapDialog`

**Files:**
- Create: `frontend/src/features/screening-assay/components/coverage-bar.tsx`
- Create: `frontend/src/features/screening-assay/components/coverage-gap-dialog.tsx`
- Modify: `frontend/src/features/screening-assay/types/index.ts` (add coverage type alias)
- Test: `frontend/src/features/screening-assay/components/coverage-bar.test.tsx`

- [ ] **Step 1: Add the type alias** in `screening-assay/types/index.ts`

```ts
import type {
  CollectionCoverageResponse,
  EffectiveCollectionCoverageResponse,
} from "@/shared/lib/api/model";

export type CollectionCoverage = CollectionCoverageResponse;
export type EffectiveCollectionCoverage = EffectiveCollectionCoverageResponse;
```

Also widen the `Run` type so `run.collections` is typed: ensure the local `Run` alias includes `collections: CollectionCoverage[]` (it derives from `RunResponse`, which now has the field after regen — confirm and alias, do not hand-roll).

- [ ] **Step 2: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CoverageBar } from "./coverage-bar";

const base = { id: "c1", name: "Kinase Set", type: "library" as const };

describe("CoverageBar", () => {
  it("shows covered/total and percent", () => {
    render(
      <CoverageBar coverage={{ ...base, covered: 1840, total: 2000, fraction: 0.92 }} />,
    );
    expect(screen.getByText(/1,840\s*\/\s*2,000/)).toBeInTheDocument();
    expect(screen.getByText(/92%/)).toBeInTheDocument();
  });

  it("renders an em-dash for an empty collection", () => {
    render(<CoverageBar coverage={{ ...base, covered: 0, total: 0, fraction: null }} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("exposes a remaining affordance when onViewGap is provided", () => {
    render(
      <CoverageBar
        coverage={{ ...base, covered: 1840, total: 2000, fraction: 0.92 }}
        onViewGap={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: /160 remaining/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd frontend && pnpm vitest run src/features/screening-assay/components/coverage-bar.test.tsx`
Expected: FAIL — module not found

- [ ] **Step 4: Write `CoverageBar`** (neutral fill; inline progress idiom; remaining beside the action)

```tsx
"use client";

import { CollectionTypeIcon } from "@/features/research-organization/components/collection/collection-type-icon";
import type { CollectionType } from "@/features/research-organization/types";
import { Button } from "@/shared/components/ui/button";
import { cn } from "@/shared/lib/utils";
import type { CollectionCoverage } from "../types";

const fmt = (n: number) => n.toLocaleString("en-US");

export function CoverageBar({
  coverage,
  onViewGap,
  runCount,
  className,
}: {
  coverage: CollectionCoverage;
  /** When provided, renders a "N remaining" button (the gap drill-down). */
  onViewGap?: () => void;
  /** Protocol rollup caption ("across N runs"). */
  runCount?: number;
  className?: string;
}) {
  const { name, type, covered, total, fraction } = coverage;
  const empty = total === 0 || fraction === null;
  const pct = empty ? 0 : Math.round((fraction ?? 0) * 100);
  const remaining = Math.max(0, total - covered);

  return (
    <div className={cn("space-y-1", className)}>
      <div className="flex items-center justify-between gap-2 text-xs">
        <span className="flex min-w-0 items-center gap-1.5">
          <CollectionTypeIcon type={type as CollectionType} className="shrink-0" />
          <span className="truncate font-medium" title={name}>
            {name}
          </span>
        </span>
        {empty ? (
          <span className="text-muted-foreground" title="Collection is empty">
            —
          </span>
        ) : (
          <span className="shrink-0 tabular-nums text-muted-foreground">
            {fmt(covered)} / {fmt(total)} · {pct}%
          </span>
        )}
      </div>

      {!empty && (
        <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
          {/* Neutral accent fill — coverage is progress, not a pass/fail signal. */}
          <div
            className="h-full rounded-full bg-primary transition-all duration-300"
            style={{ width: `${pct}%` }}
          />
        </div>
      )}

      {!empty && (onViewGap || runCount !== undefined) && (
        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
          <span>{runCount !== undefined ? `across ${runCount} run${runCount === 1 ? "" : "s"}` : ""}</span>
          {onViewGap && remaining > 0 && (
            <Button
              type="button"
              variant="link"
              size="sm"
              className="h-auto p-0 text-[11px]"
              onClick={onViewGap}
            >
              {fmt(remaining)} remaining
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Write `CoverageGapDialog`** (lists unscreened molecule ids; reuses molecule resolution)

```tsx
"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { useQuery } from "@tanstack/react-query";
import { MoleculeMiniCard } from "@/features/chemical-registration/components/molecule-mini-card";

interface CoverageGapDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** "/runs/{id}/collections/{cid}" or "/protocols/{id}/collections/{cid}". */
  gapBasePath: string;
  collectionName: string;
}

export function CoverageGapDialog({
  open,
  onOpenChange,
  gapBasePath,
  collectionName,
}: CoverageGapDialogProps) {
  const { data: moleculeIds } = useQuery({
    queryKey: ["coverage-gap", gapBasePath],
    queryFn: () =>
      customInstance<string[]>({
        url: `${API_V1}${gapBasePath}/gap`,
        method: "GET",
        params: { offset: 0, limit: 200 },
      }),
    enabled: open,
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Not yet screened — {collectionName}</DialogTitle>
          <DialogDescription>
            {moleculeIds ? `${moleculeIds.length} compound(s) shown` : "Loading…"}
          </DialogDescription>
        </DialogHeader>
        <div className="grid max-h-[60vh] grid-cols-2 gap-2 overflow-auto sm:grid-cols-3">
          {(moleculeIds ?? []).map((id) => (
            <MoleculeMiniCard key={id} moleculeId={id} />
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

> Confirm the actual molecule-card component name/path the collection detail page uses to render a molecule by id, and substitute it for `MoleculeMiniCard`. If pagination beyond 200 is needed, add a "Load more" button incrementing `offset`.

- [ ] **Step 6: Run the CoverageBar test**

Run: `cd frontend && pnpm vitest run src/features/screening-assay/components/coverage-bar.test.tsx`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/screening-assay/components/coverage-bar.tsx frontend/src/features/screening-assay/components/coverage-gap-dialog.tsx frontend/src/features/screening-assay/components/coverage-bar.test.tsx frontend/src/features/screening-assay/types/index.ts
git commit -m "feat(screening): CoverageBar + CoverageGapDialog"
```

---

### Task 15: Link hooks + `CollectionMultiSelect` + coverage chips

**Files:**
- Create: `frontend/src/features/screening-assay/hooks/create-link-hooks.ts` (generalized)
- Modify: `frontend/src/features/screening-assay/hooks/use-run-targets.ts`, `use-protocol-targets.ts`
- Create: `frontend/src/features/screening-assay/hooks/use-run-collections.ts`
- Create: `frontend/src/features/screening-assay/components/collection-multi-select.tsx`
- Create: `frontend/src/features/screening-assay/components/collection-coverage-chips.tsx`

- [ ] **Step 1: Generalize the link-hook factory** — copy `create-target-link-hooks.ts` to `create-link-hooks.ts`, rename `createTargetLinkHooks` → `createLinkHooks`, add a `linkSegment` config field, and replace the two `/targets/` URL fragments with `/${linkSegment}/`:

```ts
export function createLinkHooks(config: {
  entitySegment: string;
  /** Link kind path segment, e.g. "targets" or "collections". */
  linkSegment: string;
  labels: { addedTo: string; removedFrom: string };
  invalidateKeys: (entityId: string) => QueryKey[];
}) {
  const { entitySegment, linkSegment, labels, invalidateKeys } = config;
  // ... identical body, but both customInstance URLs become:
  //   url: `${API_V1}/${entitySegment}/${entityId}/${linkSegment}/${linkId}`,
  // (rename the `targetId` param to `linkId`)
}
```

- [ ] **Step 2: Point the target hooks at the generalized factory**

In `use-run-targets.ts` and `use-protocol-targets.ts`, import `createLinkHooks` and pass `linkSegment: "targets"`. Keep the existing labels/invalidation. Delete `create-target-link-hooks.ts`.

- [ ] **Step 3: Run the existing target hook tests** (regression gate)

Run: `cd frontend && pnpm vitest run src/features/screening-assay`
Expected: PASS — targets behavior unchanged.

- [ ] **Step 4: Write `use-run-collections.ts`**

```ts
"use client";

import { createLinkHooks } from "./create-link-hooks";
import { PROTOCOLS_KEY, RUNS_KEY } from "./query-keys";

const runCollectionHooks = createLinkHooks({
  entitySegment: "runs",
  linkSegment: "collections",
  labels: { addedTo: "Collection added to run", removedFrom: "Collection removed from run" },
  // Run detail + run lists + protocol queries (coverage rolls up to the protocol).
  invalidateKeys: (runId) => [[...RUNS_KEY, runId], RUNS_KEY, PROTOCOLS_KEY],
});

export const invalidateRunCollectionQueries = runCollectionHooks.invalidateTargetQueries;
export const useAddRunCollection = runCollectionHooks.useAddTarget;
export const useRemoveRunCollection = runCollectionHooks.useRemoveTarget;
```

- [ ] **Step 5: Write `CollectionMultiSelect`** — copy `target-multi-select.tsx`, source from `useCollections()`, render the type icon, sort Library first:

```tsx
"use client";

import { CollectionTypeIcon } from "@/features/research-organization/components/collection/collection-type-icon";
import { useCollections } from "@/features/research-organization/hooks/use-collections";
import { COLLECTION_TYPE_LABELS, type Collection } from "@/features/research-organization/types";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/shared/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { cn } from "@/shared/lib/utils";
import { Check, ChevronsUpDown, X } from "lucide-react";
import { useMemo, useState } from "react";

export function CollectionMultiSelect({
  value,
  onChange,
  disabled,
  placeholder = "Add a collection…",
  projectIds,
  className,
}: {
  value: string[];
  onChange: (ids: string[]) => void;
  disabled?: boolean;
  placeholder?: string;
  projectIds?: string[];
  className?: string;
}) {
  const { data: collections } = useCollections(projectIds, { includeAll: true });
  const [open, setOpen] = useState(false);

  // Library first, then by name — the common case is front (design §9).
  const ordered = useMemo(() => {
    return [...(collections ?? [])].sort((a, b) => {
      const al = a.type === "library" ? 0 : 1;
      const bl = b.type === "library" ? 0 : 1;
      return al - bl || a.name.localeCompare(b.name);
    });
  }, [collections]);

  const byId = new Map((collections ?? []).map((c) => [c.id, c] as const));
  const selected = value.map((id) => byId.get(id)).filter((c): c is Collection => Boolean(c));

  const toggle = (id: string) => {
    if (disabled) return;
    onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id]);
  };

  return (
    <div className={cn("space-y-2", className)}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            role="combobox"
            aria-expanded={open}
            disabled={disabled}
            className={cn(
              "w-full justify-between font-normal",
              selected.length === 0 && "text-muted-foreground",
            )}
          >
            {selected.length > 0
              ? `${selected.length} collection${selected.length === 1 ? "" : "s"} selected`
              : placeholder}
            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
          <Command>
            <CommandInput placeholder="Search collections…" />
            <CommandList>
              <CommandEmpty>No collections found.</CommandEmpty>
              <CommandGroup>
                {ordered.map((c) => (
                  <CommandItem key={c.id} value={c.name} onSelect={() => toggle(c.id)}>
                    <Check
                      className={cn(
                        "mr-2 h-4 w-4",
                        value.includes(c.id) ? "opacity-100" : "opacity-0",
                      )}
                    />
                    <CollectionTypeIcon type={c.type} className="mr-1.5 shrink-0" />
                    <span className="flex-1 truncate">{c.name}</span>
                    <span className="ml-2 shrink-0 text-muted-foreground text-xs">
                      {COLLECTION_TYPE_LABELS[c.type]}
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>

      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {selected.map((c) => (
            <Badge key={c.id} variant="secondary" className="gap-1 font-normal">
              <CollectionTypeIcon type={c.type} />
              {c.name}
              {!disabled && (
                <button
                  type="button"
                  aria-label={`Remove ${c.name}`}
                  onClick={() => toggle(c.id)}
                  className="-mr-0.5 ml-0.5 rounded-sm opacity-60 hover:opacity-100"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Write `collection-coverage-chips.tsx`** (compact run-list cell: `[icon] 92%`, name+counts in tooltip, +N overflow)

```tsx
"use client";

import { CollectionTypeIcon } from "@/features/research-organization/components/collection/collection-type-icon";
import type { CollectionType } from "@/features/research-organization/types";
import { Badge } from "@/shared/components/ui/badge";
import type { CollectionCoverage } from "../types";

const fmt = (n: number) => n.toLocaleString("en-US");

export function CollectionCoverageChips({
  collections,
  max = 2,
}: {
  collections: CollectionCoverage[] | null | undefined;
  max?: number;
}) {
  if (!collections || collections.length === 0) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }
  const shown = collections.slice(0, max);
  const hidden = collections.slice(max);
  return (
    <div className="flex flex-wrap items-center gap-1">
      {shown.map((c) => {
        const pct = c.fraction === null ? "—" : `${Math.round(c.fraction * 100)}%`;
        return (
          <Badge
            key={c.id}
            variant="secondary"
            className="gap-1 font-normal text-[10px]"
            title={`${c.name}: ${fmt(c.covered)} / ${fmt(c.total)}`}
          >
            <CollectionTypeIcon type={c.type as CollectionType} className="h-3 w-3" />
            {pct}
          </Badge>
        );
      })}
      {hidden.length > 0 && (
        <Badge
          variant="outline"
          className="font-normal text-[10px] text-muted-foreground"
          title={hidden.map((c) => c.name).join(", ")}
        >
          +{hidden.length}
        </Badge>
      )}
    </div>
  );
}
```

- [ ] **Step 7: Lint + typecheck**

Run: `cd frontend && pnpm lint && pnpm tsc --noEmit`
Expected: clean (lint gated by exit code, not piped output).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/features/screening-assay/hooks/create-link-hooks.ts frontend/src/features/screening-assay/hooks/use-run-targets.ts frontend/src/features/screening-assay/hooks/use-protocol-targets.ts frontend/src/features/screening-assay/hooks/use-run-collections.ts frontend/src/features/screening-assay/components/collection-multi-select.tsx frontend/src/features/screening-assay/components/collection-coverage-chips.tsx
git rm frontend/src/features/screening-assay/hooks/create-target-link-hooks.ts
git commit -m "feat(screening): collection link hooks, multi-select, coverage chips"
```

---

### Task 16: Wire the three surfaces

**Files:**
- Modify: `frontend/src/features/screening-assay/components/run-detail.tsx`
- Modify: `frontend/src/features/screening-assay/components/run-list.tsx`
- Modify: protocol detail component (locate the file rendering the protocol's effective-targets / header — search for `list_protocol_targets` consumer / `ProtocolTargetRefResponse`)

- [ ] **Step 1: Run detail — Collections card** (after the Targets card, mirror its edit/diff logic)

```tsx
            {/* Collections (library coverage) */}
            <Card>
              <CardHeader>
                <CardTitle>Collections</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {canEditTags && !run.is_locked && (
                  <CollectionMultiSelect
                    value={run.collections.map((c) => c.id)}
                    projectIds={protocol?.project_id ? [protocol.project_id] : undefined}
                    onChange={async (ids) => {
                      const current = run.collections.map((c) => c.id);
                      const mutations = [
                        ...ids
                          .filter((id) => !current.includes(id))
                          .map((id) => addRunCollection.mutateAsync(id)),
                        ...current
                          .filter((id) => !ids.includes(id))
                          .map((id) => removeRunCollection.mutateAsync(id)),
                      ];
                      try {
                        await Promise.all(mutations);
                      } catch {
                        // surfaced by mutation error toasts
                      } finally {
                        await invalidateRunCollectionQueries(qc, runId);
                      }
                    }}
                    disabled={addRunCollection.isPending || removeRunCollection.isPending}
                  />
                )}
                {run.collections.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No collections attached.</p>
                ) : (
                  run.collections.map((c) => (
                    <CoverageBar
                      key={c.id}
                      coverage={c}
                      onViewGap={() => setGap({ path: `/runs/${runId}/collections/${c.id}`, name: c.name })}
                    />
                  ))
                )}
              </CardContent>
            </Card>
```

Add hooks/imports near the top of `run-detail.tsx`:

```tsx
import {
  invalidateRunCollectionQueries,
  useAddRunCollection,
  useRemoveRunCollection,
} from "../hooks/use-run-collections";
import { CoverageBar } from "./coverage-bar";
import { CollectionMultiSelect } from "./collection-multi-select";
import { CoverageGapDialog } from "./coverage-gap-dialog";
```

```tsx
  const addRunCollection = useAddRunCollection(runId);
  const removeRunCollection = useRemoveRunCollection(runId);
  const [gap, setGap] = useState<{ path: string; name: string } | null>(null);
```

Render the dialog once near the component root:

```tsx
      {gap && (
        <CoverageGapDialog
          open
          onOpenChange={(o) => !o && setGap(null)}
          gapBasePath={gap.path}
          collectionName={gap.name}
        />
      )}
```

- [ ] **Step 2: Run list — coverage column** (add to the colDefs, after Targets)

```tsx
      {
        headerName: "Library coverage",
        field: "collections",
        flex: 1,
        minWidth: 150,
        sortable: false,
        getQuickFilterText: (p) =>
          (p.value ?? []).map((c: { name: string }) => c.name).join(" "),
        cellRenderer: (params: ICellRendererParams<Run>) => (
          <CollectionCoverageChips collections={params.data?.collections} />
        ),
      },
```

Add `import { CollectionCoverageChips } from "./collection-coverage-chips";`.

- [ ] **Step 3: Protocol detail — coverage rollup**

Fetch the rollup and render `CoverageBar`s (with `runCount` + gap dialog). Add a hook:

```ts
// frontend/src/features/screening-assay/hooks/use-protocol-collection-coverage.ts
"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import type { EffectiveCollectionCoverage } from "../types";
import { PROTOCOLS_KEY } from "./query-keys";

export function useProtocolCollectionCoverage(protocolId: string) {
  return useQuery({
    queryKey: [...PROTOCOLS_KEY, protocolId, "collection-coverage"],
    queryFn: () =>
      customInstance<EffectiveCollectionCoverage[]>({
        url: `${API_V1}/protocols/${protocolId}/collection-coverage`,
        method: "GET",
      }),
    enabled: Boolean(protocolId),
  });
}
```

In the protocol detail component, render a "Library coverage" section:

```tsx
{coverage && coverage.length > 0 && (
  <Card>
    <CardHeader><CardTitle>Library coverage</CardTitle></CardHeader>
    <CardContent className="space-y-3">
      {coverage.map((c) => (
        <CoverageBar
          key={c.id}
          coverage={c}
          runCount={c.run_count}
          onViewGap={() => setGap({ path: `/protocols/${protocolId}/collections/${c.id}`, name: c.name })}
        />
      ))}
    </CardContent>
  </Card>
)}
```

(Wire `const { data: coverage } = useProtocolCollectionCoverage(protocolId);` + the same `gap` state + `CoverageGapDialog` as in run detail.)

- [ ] **Step 4: Lint + typecheck + component tests**

Run: `cd frontend && pnpm lint && pnpm tsc --noEmit && pnpm vitest run src/features/screening-assay`
Expected: clean + PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/screening-assay/components/run-detail.tsx frontend/src/features/screening-assay/components/run-list.tsx frontend/src/features/screening-assay/hooks/use-protocol-collection-coverage.ts
git add -A frontend/src/features/screening-assay
git commit -m "feat(screening): collections card, coverage column, protocol rollup"
```

---

### Task 17: E2E smoke

**Files:**
- Create: `frontend/tests/e2e/run-collection-coverage.spec.ts`

- [ ] **Step 1: Write a Playwright spec** — attach a collection to a run, assert the coverage bar appears and the gap dialog opens:

```ts
import { expect, test } from "@playwright/test";

test("attach a collection to a run and see coverage", async ({ page }) => {
  await page.goto("/assays"); // navigate to a run detail (use existing test seed helpers)
  // ... open a run, open the Collections card, pick a library
  await page.getByRole("button", { name: /add a collection/i }).click();
  await page.getByPlaceholder(/search collections/i).fill("Kinase");
  await page.getByRole("option", { name: /Kinase Set/i }).click();
  await page.keyboard.press("Escape");
  await expect(page.getByText(/\d+\s*\/\s*\d+\s*·\s*\d+%/)).toBeVisible();
  await page.getByRole("button", { name: /remaining/i }).click();
  await expect(page.getByText(/not yet screened/i)).toBeVisible();
});
```

(Align selectors/navigation with the existing run-detail E2E specs and seed fixtures.)

- [ ] **Step 2: Run it**

Run: `cd frontend && pnpm playwright test run-collection-coverage`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/e2e/run-collection-coverage.spec.ts
git commit -m "test(screening): e2e run collection coverage"
```

---

## Final verification

- [ ] Backend: `cd backend && uv run pytest -q && uv run ruff check src && uv run ruff format --check src`
- [ ] Frontend: `cd frontend && pnpm lint && pnpm tsc --noEmit && pnpm vitest run`
- [ ] Update `docs/implementation-status.md` if this feature has a checklist line.
- [ ] Push the branch.

---

## Spec coverage self-check

| Spec section | Task(s) |
|---|---|
| §3 `run_collections` table (RESTRICT) | 1, 2 |
| §4 coverage queries + gap (NOT EXISTS) | 6 |
| §5 value objects | 3 |
| §6 migration 055 | 1 |
| §7 API (run attach/detach/gap, protocol coverage/gap) | 11 |
| §8 components (repo, read model, use cases, events, list/create) | 4, 5, 7, 8, 9 |
| §9 CoverageBar + 3 surfaces + picker + hooks | 14, 15, 16 |
| §10 collection-type icons | 13 |
| §11 decisions (run-level only, lock guard, neutral fill) | 5, 7, 14 |
| §13 testing (read model, repo, app, API, FE, e2e) | every task (TDD) + 17 |
