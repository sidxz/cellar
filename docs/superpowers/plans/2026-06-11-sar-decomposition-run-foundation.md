# SAR Decomposition-Run Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the compute-and-persist foundation for server-side, unbounded R-group decomposition: a streaming RDKit decomposer with batch-stable labels, the `RGroupDecompositionRun` aggregate, and its persistence (run header + assignment rows + `(membership_hash, core_hash)` cache).

**Architecture:** Mirrors the existing scaffold-tree async-job slice exactly (DDD aggregate with a `pending→running→ready/failed/cancelled` state machine; SQLAlchemy model with `WorkspaceIdMixin`/`VersionMixin`; repo with a `find_cached` partial-index lookup). The one deliberate divergence: the decomposition **result is persisted as queryable assignment rows**, not a JSONB blob, so a later endpoint can paginate/aggregate it for arbitrarily large collections. This plan stops before the async job, routes, and the enriched (molecule+activity) rows query — those are the next plan and build on this.

**Tech Stack:** Python 3.13 · RDKit (`rdRGroupDecomposition`) · SQLAlchemy 2.0 async · Alembic · Postgres · pytest (`asyncio_mode=auto`, testcontainers `uow` fixture). All commands run from `backend/`.

**Spec:** `docs/superpowers/specs/2026-06-11-sar-full-collection-coverage-design.md` (this implements the §3 persistence Pair 1 + the §4 decomposition compute keystone + §8.1).

---

## File Structure

**Create:**
- `src/cellar/infrastructure/rdkit/streaming_rgroup_decomposer.py` — `StreamingRGroupDecomposer` + `RGroupDecompositionSession`. A single stateful `rdRGroupDecomposition.RGroupDecomposition` object accepts molecules across batches (`.add()`) and labels them consistently at `.finish()`. **Solves §8.1** (per-batch *independent* decomposition would produce inconsistent labels).
- `src/cellar/domain/sar_analysis/rgroup_decomposition_run.py` — `RGroupDecompositionRun` aggregate + `RGroupDecompositionRunStatus` + `InvalidRGroupRunTransition`. Header only (labels + counts); assignments are persisted separately.
- `src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/rgroup_decomposition_models.py` — `RGroupDecompositionRunModel` + `RGroupAssignmentModel`.
- `alembic/versions/057_rgroup_decomposition_runs.py` — the two tables + indexes.
- `src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/rgroup_decomposition_run_repository.py` — `SQLAlchemyRGroupDecompositionRunRepository`.

**Modify:**
- `src/cellar/application/sar_analysis/repositories.py` — add the `RGroupDecompositionRunRepository` Protocol.

**Test:**
- `tests/unit/infrastructure/rdkit/test_streaming_rgroup_decomposer.py`
- `tests/unit/domain/sar_analysis/test_rgroup_decomposition_run.py`
- `tests/integration/persistence/sar_analysis/test_rgroup_decomposition_run_repository.py`

**Reuse (no change):** `src/cellar/domain/sar_analysis/rgroup_types.py` (`RGroupAssignment`, `RGroupDecompositionResult`), `src/cellar/infrastructure/rdkit/rgroup_decomposer.py` (the functional `RGroupDecomposer` — used as the test oracle), `src/cellar/infrastructure/persistence/sqlalchemy/base.py` (mixins).

---

## Task 1: Streaming R-group decomposer (the §8.1 keystone)

**Files:**
- Create: `src/cellar/infrastructure/rdkit/streaming_rgroup_decomposer.py`
- Test: `tests/unit/infrastructure/rdkit/test_streaming_rgroup_decomposer.py`

- [ ] **Step 1: Write the failing oracle test** (streaming whole-set == functional `RGroupDecompose`)

Create `tests/unit/infrastructure/rdkit/test_streaming_rgroup_decomposer.py`:

```python
from __future__ import annotations

import uuid

from cellar.infrastructure.rdkit.rgroup_decomposer import RGroupDecomposer
from cellar.infrastructure.rdkit.streaming_rgroup_decomposer import (
    StreamingRGroupDecomposer,
)

CORE = "c1ccccc1"


def _stream(mols):
    session = StreamingRGroupDecomposer().session(core_smiles=CORE)
    for mid, smi in mols:
        session.add(mid, smi)
    return session.finish()


def test_streaming_matches_functional_oracle():
    f_id, cl_id, me_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    mols = [(f_id, "Fc1ccccc1"), (cl_id, "Clc1ccccc1"), (me_id, "Cc1ccccc1")]

    streamed = _stream(mols)
    ref = RGroupDecomposer().decompose(core_smiles=CORE, molecules=mols)

    assert streamed.rgroup_labels == ref.rgroup_labels
    assert {a.molecule_id: a.rgroups for a in streamed.assignments} == {
        a.molecule_id: a.rgroups for a in ref.assignments
    }
    assert set(streamed.unmatched_ids) == set(ref.unmatched_ids)
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/unit/infrastructure/rdkit/test_streaming_rgroup_decomposer.py -v`
Expected: FAIL — `ModuleNotFoundError: streaming_rgroup_decomposer`.

- [ ] **Step 3: Implement the streaming decomposer**

Create `src/cellar/infrastructure/rdkit/streaming_rgroup_decomposer.py`:

```python
"""Streaming R-group decomposition.

A single stateful ``rdRGroupDecomposition.RGroupDecomposition`` accepts
molecules across many batches and labels them consistently only at
``finish()``. This is the streaming-correctness keystone: decomposing each
batch with an *independent* RDKit object could assign different R-labels to the
same physical position across batches (RDKit discovers labels from the set it
sees). One shared object avoids that — memory is O(matched set), which equals
the congeneric series, not the whole collection.
"""

from __future__ import annotations

from typing import Any

import structlog
from rdkit import Chem
from rdkit.Chem import rdRGroupDecomposition

from cellar.domain.sar_analysis.rgroup_types import (
    RGroupAssignment,
    RGroupDecompositionResult,
)

logger = structlog.get_logger(__name__)


class RGroupDecompositionSession:
    """Accumulate molecules, then decompose them against the core in one pass."""

    def __init__(self, core_smiles: str) -> None:
        self._core_smiles = core_smiles
        core = Chem.MolFromSmiles(core_smiles)
        self._added_ids: list[Any] = []
        self._unmatched_ids: list[Any] = []
        if core is None:
            logger.warning("streaming_rgroup_core_unparseable", core=core_smiles)
            self._rgd = None
        else:
            params = rdRGroupDecomposition.RGroupDecompositionParameters()
            self._rgd = rdRGroupDecomposition.RGroupDecomposition([core], params)

    def add(self, molecule_id: Any, smiles: str) -> bool:
        """Add one molecule. Returns True if it matched the core and was added."""
        if self._rgd is None:
            self._unmatched_ids.append(molecule_id)
            return False
        mol = Chem.MolFromSmiles(smiles) if smiles else None
        if mol is None:
            self._unmatched_ids.append(molecule_id)
            return False
        if self._rgd.Add(mol) < 0:
            self._unmatched_ids.append(molecule_id)
            return False
        self._added_ids.append(molecule_id)
        return True

    def finish(self) -> RGroupDecompositionResult:
        if self._rgd is None or not self._added_ids:
            return RGroupDecompositionResult(
                core_smiles=self._core_smiles,
                unmatched_ids=list(self._unmatched_ids),
            )
        try:
            self._rgd.Process()
            rows = self._rgd.GetRGroupsAsRows(asSmiles=True)
            seen: set[str] = set()
            for row in rows:
                for key in row:
                    if key.startswith("R") and key[1:].isdigit():
                        seen.add(key)
            labels = sorted(seen, key=lambda k: int(k[1:]))
            assignments = [
                RGroupAssignment(
                    molecule_id=mid,
                    rgroups={k: row[k] for k in labels if k in row},
                )
                for mid, row in zip(self._added_ids, rows)
            ]
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("streaming_rgroup_failed", core=self._core_smiles, exc=str(exc))
            return RGroupDecompositionResult(
                core_smiles=self._core_smiles,
                unmatched_ids=[*self._added_ids, *self._unmatched_ids],
            )
        return RGroupDecompositionResult(
            core_smiles=self._core_smiles,
            rgroup_labels=labels,
            assignments=assignments,
            unmatched_ids=list(self._unmatched_ids),
        )


class StreamingRGroupDecomposer:
    """Factory for one decomposition session per (core, member-stream)."""

    def session(self, *, core_smiles: str) -> RGroupDecompositionSession:
        return RGroupDecompositionSession(core_smiles)
```

- [ ] **Step 4: Run the oracle test to confirm it passes**

Run: `cd backend && uv run pytest tests/unit/infrastructure/rdkit/test_streaming_rgroup_decomposer.py -v`
Expected: PASS. (If `GetRGroupsAsRows` ordering or default params diverge from the functional API, adjust `RGroupDecompositionParameters` until streaming == oracle — that equality is the contract.)

- [ ] **Step 5: Add the unmatched + batch-stability tests**

Append to the test file:

```python
def test_unmatched_molecule_is_surfaced_not_dropped():
    good, bad, no_smi = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    res = _stream([(good, "Fc1ccccc1"), (bad, "CCO"), (no_smi, "")])

    assert good in {a.molecule_id for a in res.assignments}
    assert bad in res.unmatched_ids       # aliphatic — no benzene core
    assert no_smi in res.unmatched_ids    # empty SMILES
    accounted = {a.molecule_id for a in res.assignments} | set(res.unmatched_ids)
    assert accounted == {good, bad, no_smi}


def test_unparseable_core_marks_all_unmatched():
    a, b = uuid.uuid4(), uuid.uuid4()
    session = StreamingRGroupDecomposer().session(core_smiles="not-a-smiles")
    session.add(a, "Fc1ccccc1")
    session.add(b, "Clc1ccccc1")
    res = session.finish()

    assert res.assignments == []
    assert set(res.unmatched_ids) == {a, b}


def test_labels_consistent_across_molecules_substituting_different_positions():
    # Each molecule varies a different ring position. A per-batch *independent*
    # decomposition could disagree on the label set; the single session must give
    # every assignment labels drawn from one shared, consistent set.
    ids = [uuid.uuid4() for _ in range(3)]
    res = _stream(
        [(ids[0], "Fc1ccccc1"), (ids[1], "Clc1ccc(C)cc1"), (ids[2], "Cc1ccccc1")]
    )
    for asg in res.assignments:
        assert set(asg.rgroups).issubset(set(res.rgroup_labels))
```

- [ ] **Step 6: Run all Task-1 tests**

Run: `cd backend && uv run pytest tests/unit/infrastructure/rdkit/test_streaming_rgroup_decomposer.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/cellar/infrastructure/rdkit/streaming_rgroup_decomposer.py tests/unit/infrastructure/rdkit/test_streaming_rgroup_decomposer.py
git commit -m "feat(sar): streaming R-group decomposer with batch-stable labels" -- src/cellar/infrastructure/rdkit/streaming_rgroup_decomposer.py tests/unit/infrastructure/rdkit/test_streaming_rgroup_decomposer.py
```

---

## Task 2: `RGroupDecompositionRun` domain aggregate

**Files:**
- Create: `src/cellar/domain/sar_analysis/rgroup_decomposition_run.py`
- Test: `tests/unit/domain/sar_analysis/test_rgroup_decomposition_run.py`

- [ ] **Step 1: Write the failing state-machine test**

Create `tests/unit/domain/sar_analysis/test_rgroup_decomposition_run.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from cellar.domain.sar_analysis.rgroup_decomposition_run import (
    InvalidRGroupRunTransition,
    RGroupDecompositionRun,
    RGroupDecompositionRunStatus,
)

_NOW = datetime(2026, 6, 11, tzinfo=timezone.utc)


def _new_run() -> RGroupDecompositionRun:
    return RGroupDecompositionRun.create(
        workspace_id=uuid.uuid4(),
        requested_by=uuid.uuid4(),
        membership_hash="m-hash",
        core_smiles="c1ccccc1",
        core_hash="c-hash",
        now=_NOW,
    )


def test_create_starts_pending_with_zero_counts():
    run = _new_run()
    assert run.status == RGroupDecompositionRunStatus.PENDING
    assert run.rgroup_labels == []
    assert run.matched_count == 0
    assert run.total_count == 0


def test_mark_ready_records_labels_and_counts():
    run = _new_run().mark_running(_NOW)
    ready = run.mark_ready(
        rgroup_labels=["R1", "R2"],
        matched_count=8,
        unmatched_count=2,
        total_count=10,
        now=_NOW,
    )
    assert ready.status == RGroupDecompositionRunStatus.READY
    assert ready.rgroup_labels == ["R1", "R2"]
    assert ready.matched_count == 8
    assert ready.unmatched_count == 2
    assert ready.total_count == 10
    assert ready.completed_at == _NOW


def test_cannot_mark_ready_from_pending():
    with pytest.raises(InvalidRGroupRunTransition):
        _new_run().mark_ready(
            rgroup_labels=[], matched_count=0, unmatched_count=0, total_count=0, now=_NOW
        )


def test_mark_failed_from_running_records_error():
    failed = _new_run().mark_running(_NOW).mark_failed("boom", _NOW)
    assert failed.status == RGroupDecompositionRunStatus.FAILED
    assert failed.error_message == "boom"


def test_ready_is_terminal():
    ready = _new_run().mark_running(_NOW).mark_ready(
        rgroup_labels=[], matched_count=0, unmatched_count=0, total_count=0, now=_NOW
    )
    with pytest.raises(InvalidRGroupRunTransition):
        ready.mark_cancelled(_NOW)
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/unit/domain/sar_analysis/test_rgroup_decomposition_run.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the aggregate**

Create `src/cellar/domain/sar_analysis/rgroup_decomposition_run.py`:

```python
"""RGroupDecompositionRun — persisted async R-group decomposition over a member
set against one core.

State machine (mirrors ScaffoldTreeJob):
  pending -> running -> {ready | failed | cancelled}
  pending             ->  cancelled

The aggregate holds only the *header* (discovered labels + counts). The
per-molecule assignments are persisted as separate rows (see the repository),
so the result scales past what a single JSONB blob could hold.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import UUID


class RGroupDecompositionRunStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InvalidRGroupRunTransition(Exception):
    pass


_TERMINAL = {
    RGroupDecompositionRunStatus.READY,
    RGroupDecompositionRunStatus.FAILED,
    RGroupDecompositionRunStatus.CANCELLED,
}


@dataclass(frozen=True)
class RGroupDecompositionRun:
    id: UUID
    workspace_id: UUID
    requested_by: UUID
    membership_hash: str
    core_smiles: str
    core_hash: str
    requested_at: datetime
    status: RGroupDecompositionRunStatus = RGroupDecompositionRunStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    rgroup_labels: list[str] = field(default_factory=list)
    matched_count: int = 0
    unmatched_count: int = 0
    total_count: int = 0
    version: int = 1

    @classmethod
    def create(
        cls,
        *,
        workspace_id: UUID,
        requested_by: UUID,
        membership_hash: str,
        core_smiles: str,
        core_hash: str,
        now: datetime,
    ) -> RGroupDecompositionRun:
        return cls(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            requested_by=requested_by,
            membership_hash=membership_hash,
            core_smiles=core_smiles,
            core_hash=core_hash,
            requested_at=now,
        )

    def mark_running(self, now: datetime) -> RGroupDecompositionRun:
        if self.status != RGroupDecompositionRunStatus.PENDING:
            raise InvalidRGroupRunTransition(f"Cannot mark RUNNING from {self.status}")
        return replace(self, status=RGroupDecompositionRunStatus.RUNNING, started_at=now)

    def mark_ready(
        self,
        *,
        rgroup_labels: list[str],
        matched_count: int,
        unmatched_count: int,
        total_count: int,
        now: datetime,
    ) -> RGroupDecompositionRun:
        if self.status != RGroupDecompositionRunStatus.RUNNING:
            raise InvalidRGroupRunTransition(f"Cannot mark READY from {self.status}")
        return replace(
            self,
            status=RGroupDecompositionRunStatus.READY,
            completed_at=now,
            rgroup_labels=list(rgroup_labels),
            matched_count=matched_count,
            unmatched_count=unmatched_count,
            total_count=total_count,
        )

    def mark_failed(self, error: str, now: datetime) -> RGroupDecompositionRun:
        if self.status not in {
            RGroupDecompositionRunStatus.PENDING,
            RGroupDecompositionRunStatus.RUNNING,
        }:
            raise InvalidRGroupRunTransition(f"Cannot mark FAILED from {self.status}")
        return replace(
            self,
            status=RGroupDecompositionRunStatus.FAILED,
            completed_at=now,
            error_message=error,
        )

    def mark_cancelled(self, now: datetime) -> RGroupDecompositionRun:
        if self.status in _TERMINAL:
            raise InvalidRGroupRunTransition(f"Cannot CANCEL terminal {self.status}")
        return replace(
            self,
            status=RGroupDecompositionRunStatus.CANCELLED,
            completed_at=now,
        )
```

> Note: `mark_ready` uses keyword-only args (`*`), so the Task-2 test calls it with keywords. Keep this signature — Task 4's repo and the next plan's runner both call it by keyword.

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `cd backend && uv run pytest tests/unit/domain/sar_analysis/test_rgroup_decomposition_run.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cellar/domain/sar_analysis/rgroup_decomposition_run.py tests/unit/domain/sar_analysis/test_rgroup_decomposition_run.py
git commit -m "feat(sar): RGroupDecompositionRun aggregate (header + state machine)" -- src/cellar/domain/sar_analysis/rgroup_decomposition_run.py tests/unit/domain/sar_analysis/test_rgroup_decomposition_run.py
```

---

## Task 3: SQLAlchemy models

**Files:**
- Create: `src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/rgroup_decomposition_models.py`

- [ ] **Step 1: Write the models** (no test of its own — exercised by Task 5's migration + Task 6's repo tests)

Create `src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/rgroup_decomposition_models.py`:

```python
"""SQLAlchemy models for the RGroupDecompositionRun aggregate + its assignment
rows. Columns match migration 057_rgroup_decomposition_runs exactly."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cellar.infrastructure.persistence.sqlalchemy.base import (
    Base,
    VersionMixin,
    WorkspaceIdMixin,
)


class RGroupDecompositionRunModel(Base, WorkspaceIdMixin, VersionMixin):
    __tablename__ = "rgroup_decomposition_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    membership_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    core_smiles: Mapped[str] = mapped_column(Text, nullable=False)
    core_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    rgroup_labels: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    unmatched_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class RGroupAssignmentModel(Base):
    __tablename__ = "rgroup_assignments"

    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("rgroup_decomposition_runs.id", ondelete="CASCADE"), primary_key=True
    )
    molecule_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    rgroups: Mapped[dict] = mapped_column(JSONB, nullable=False)
```

- [ ] **Step 2: Verify it imports**

Run: `cd backend && uv run python -c "from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.rgroup_decomposition_models import RGroupDecompositionRunModel, RGroupAssignmentModel; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/rgroup_decomposition_models.py
git commit -m "feat(sar): SQLAlchemy models for decomposition run + assignment rows" -- src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/rgroup_decomposition_models.py
```

---

## Task 4: Alembic migration 057

**Files:**
- Create: `alembic/versions/057_rgroup_decomposition_runs.py`

- [ ] **Step 1: Confirm the current head**

Run: `cd backend && uv run alembic heads`
Expected: a single head ending in `056_run_hit_criteria` (the `down_revision` below). If it differs, set `down_revision` to the reported head.

- [ ] **Step 2: Write the migration**

Create `alembic/versions/057_rgroup_decomposition_runs.py`:

```python
"""057 — rgroup_decomposition_runs + rgroup_assignments.

Persisted RGroupDecompositionRun aggregate. The run header doubles as a
(membership_hash, core_hash) cache via a partial index WHERE status='ready'.
Assignments are queryable rows (not a JSONB blob) so a large decomposition can
be paginated/aggregated.

Revision ID: 057_rgroup_decomposition_runs
Revises: 056_run_hit_criteria
Create Date: 2026-06-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "057_rgroup_decomposition_runs"
down_revision: str | None = "056_run_hit_criteria"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "rgroup_decomposition_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("membership_hash", sa.Text(), nullable=False),
        sa.Column("core_smiles", sa.Text(), nullable=False),
        sa.Column("core_hash", sa.Text(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("rgroup_labels", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("matched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unmatched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index(
        "rgroup_runs_workspace_status",
        "rgroup_decomposition_runs",
        ["workspace_id", "status"],
    )
    op.create_index(
        "rgroup_runs_cache",
        "rgroup_decomposition_runs",
        ["membership_hash", "core_hash", sa.text("completed_at DESC")],
        postgresql_where=sa.text("status = 'ready'"),
    )

    op.create_table(
        "rgroup_assignments",
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("rgroup_decomposition_runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("molecule_id", sa.Uuid(), primary_key=True),
        sa.Column("rgroups", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("rgroup_assignments")
    op.drop_index("rgroup_runs_cache", table_name="rgroup_decomposition_runs")
    op.drop_index("rgroup_runs_workspace_status", table_name="rgroup_decomposition_runs")
    op.drop_table("rgroup_decomposition_runs")
```

- [ ] **Step 3: Apply + roll back to prove the migration is reversible**

Run: `cd backend && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: no errors; final state at `057_rgroup_decomposition_runs`. (Requires a dev Postgres — same prerequisite as any migration here.)

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/057_rgroup_decomposition_runs.py
git commit -m "feat(sar): migration 057 — rgroup_decomposition_runs + rgroup_assignments" -- alembic/versions/057_rgroup_decomposition_runs.py
```

---

## Task 5: Repository — save run, find_by_id, find_cached

**Files:**
- Modify: `src/cellar/application/sar_analysis/repositories.py`
- Create: `src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/rgroup_decomposition_run_repository.py`
- Test: `tests/integration/persistence/sar_analysis/test_rgroup_decomposition_run_repository.py`

- [ ] **Step 1: Add the repo Protocol**

In `src/cellar/application/sar_analysis/repositories.py`, add the import and the Protocol (append after the existing `ScaffoldTreeJobRepository`):

```python
from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRun
from cellar.domain.sar_analysis.rgroup_types import RGroupAssignment


class RGroupDecompositionRunRepository(Protocol):
    async def save(self, run: RGroupDecompositionRun) -> None: ...

    async def find_by_id(
        self, run_id: UUID, *, workspace_id: UUID
    ) -> RGroupDecompositionRun | None: ...

    async def find_cached(
        self, *, membership_hash: str, core_hash: str
    ) -> RGroupDecompositionRun | None:
        """Return the latest READY run for this (membership_hash, core_hash), or
        None. No TTL: a ready run is valid until membership or core changes (each
        of which changes a hash). Assignment rows for the returned run are already
        persisted under its id."""
        ...

    async def write_assignments(
        self, run_id: UUID, assignments: list[RGroupAssignment]
    ) -> None: ...

    async def fetch_assignments(
        self, run_id: UUID, *, workspace_id: UUID, offset: int, limit: int
    ) -> list[RGroupAssignment]: ...

    async def count_assignments(self, run_id: UUID, *, workspace_id: UUID) -> int: ...
```

- [ ] **Step 2: Write the failing integration test** (save / find_by_id / find_cached)

Create `tests/integration/persistence/sar_analysis/test_rgroup_decomposition_run_repository.py`:

```python
"""Integration tests for SQLAlchemyRGroupDecompositionRunRepository."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from cellar.domain.sar_analysis.rgroup_decomposition_run import (
    RGroupDecompositionRun,
    RGroupDecompositionRunStatus,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.rgroup_decomposition_run_repository import (
    SQLAlchemyRGroupDecompositionRunRepository,
)

_NOW = datetime.now(timezone.utc)


def _ready_run(*, workspace_id, membership_hash, core_hash) -> RGroupDecompositionRun:
    return (
        RGroupDecompositionRun.create(
            workspace_id=workspace_id,
            requested_by=uuid.uuid4(),
            membership_hash=membership_hash,
            core_smiles="c1ccccc1",
            core_hash=core_hash,
            now=_NOW,
        )
        .mark_running(_NOW)
        .mark_ready(
            rgroup_labels=["R1"], matched_count=2, unmatched_count=0, total_count=2, now=_NOW
        )
    )


@pytest.mark.asyncio
async def test_save_and_find_by_id(uow):
    ws = uuid.uuid4()
    run = RGroupDecompositionRun.create(
        workspace_id=ws,
        requested_by=uuid.uuid4(),
        membership_hash="m1",
        core_smiles="c1ccccc1",
        core_hash="c1",
        now=_NOW,
    )
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.save(run)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        fetched = await repo.find_by_id(run.id, workspace_id=ws)

    assert fetched is not None
    assert fetched.status == RGroupDecompositionRunStatus.PENDING
    assert fetched.membership_hash == "m1"


@pytest.mark.asyncio
async def test_save_updates_status_labels_counts(uow):
    ws = uuid.uuid4()
    run = RGroupDecompositionRun.create(
        workspace_id=ws,
        requested_by=uuid.uuid4(),
        membership_hash="m2",
        core_smiles="c1ccccc1",
        core_hash="c2",
        now=_NOW,
    )
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.save(run)
        await uow.commit()

    ready = run.mark_running(_NOW).mark_ready(
        rgroup_labels=["R1", "R2"], matched_count=5, unmatched_count=1, total_count=6, now=_NOW
    )
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.save(ready)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        fetched = await repo.find_by_id(run.id, workspace_id=ws)

    assert fetched.status == RGroupDecompositionRunStatus.READY
    assert fetched.rgroup_labels == ["R1", "R2"]
    assert fetched.matched_count == 5
    assert fetched.total_count == 6


@pytest.mark.asyncio
async def test_find_cached_returns_latest_ready_for_hash_pair(uow):
    ws = uuid.uuid4()
    run = _ready_run(workspace_id=ws, membership_hash="mh", core_hash="ch")
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.save(run)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        cached = await repo.find_cached(membership_hash="mh", core_hash="ch")

    assert cached is not None
    assert cached.id == run.id


@pytest.mark.asyncio
async def test_find_cached_misses_on_different_core(uow):
    ws = uuid.uuid4()
    run = _ready_run(workspace_id=ws, membership_hash="mh2", core_hash="ch-A")
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.save(run)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        miss = await repo.find_cached(membership_hash="mh2", core_hash="ch-B")

    assert miss is None  # version-aware membership / core change ⇒ cache miss


@pytest.mark.asyncio
async def test_find_cached_ignores_pending(uow):
    ws = uuid.uuid4()
    run = RGroupDecompositionRun.create(
        workspace_id=ws,
        requested_by=uuid.uuid4(),
        membership_hash="mh3",
        core_smiles="c1ccccc1",
        core_hash="ch3",
        now=_NOW,
    )
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.save(run)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        cached = await repo.find_cached(membership_hash="mh3", core_hash="ch3")

    assert cached is None
```

- [ ] **Step 3: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/integration/persistence/sar_analysis/test_rgroup_decomposition_run_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: ...rgroup_decomposition_run_repository`.

- [ ] **Step 4: Implement the repository (header methods)**

Create `src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/rgroup_decomposition_run_repository.py`:

```python
"""SQLAlchemy implementation of RGroupDecompositionRunRepository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select

from cellar.domain.sar_analysis.rgroup_decomposition_run import (
    RGroupDecompositionRun,
    RGroupDecompositionRunStatus,
)
from cellar.domain.sar_analysis.rgroup_types import RGroupAssignment
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.rgroup_decomposition_models import (
    RGroupAssignmentModel,
    RGroupDecompositionRunModel,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyRGroupDecompositionRunRepository:
    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def save(self, run: RGroupDecompositionRun) -> None:
        session = self._uow.session
        existing = await session.get(RGroupDecompositionRunModel, run.id)
        if existing is None:
            session.add(_to_model(run))
        else:
            _apply_to_model(existing, run)

    async def find_by_id(
        self, run_id: UUID, *, workspace_id: UUID
    ) -> RGroupDecompositionRun | None:
        session = self._uow.session
        stmt = select(RGroupDecompositionRunModel).where(
            RGroupDecompositionRunModel.id == run_id,
            RGroupDecompositionRunModel.workspace_id == workspace_id,
        )
        model = (await session.execute(stmt)).scalar_one_or_none()
        return _to_domain(model) if model else None

    async def find_cached(
        self, *, membership_hash: str, core_hash: str
    ) -> RGroupDecompositionRun | None:
        session = self._uow.session
        stmt = (
            select(RGroupDecompositionRunModel)
            .where(
                RGroupDecompositionRunModel.membership_hash == membership_hash,
                RGroupDecompositionRunModel.core_hash == core_hash,
                RGroupDecompositionRunModel.status == RGroupDecompositionRunStatus.READY.value,
            )
            .order_by(RGroupDecompositionRunModel.completed_at.desc())
            .limit(1)
        )
        model = (await session.execute(stmt)).scalar_one_or_none()
        return _to_domain(model) if model else None

    # --- assignment rows: implemented in Task 6 -----------------------------
    async def write_assignments(
        self, run_id: UUID, assignments: list[RGroupAssignment]
    ) -> None:
        raise NotImplementedError  # Task 6

    async def fetch_assignments(
        self, run_id: UUID, *, workspace_id: UUID, offset: int, limit: int
    ) -> list[RGroupAssignment]:
        raise NotImplementedError  # Task 6

    async def count_assignments(self, run_id: UUID, *, workspace_id: UUID) -> int:
        raise NotImplementedError  # Task 6


def _to_model(run: RGroupDecompositionRun) -> RGroupDecompositionRunModel:
    return RGroupDecompositionRunModel(
        id=run.id,
        workspace_id=run.workspace_id,
        requested_by=run.requested_by,
        membership_hash=run.membership_hash,
        core_smiles=run.core_smiles,
        core_hash=run.core_hash,
        requested_at=run.requested_at,
        status=run.status.value,
        started_at=run.started_at,
        completed_at=run.completed_at,
        error_message=run.error_message,
        rgroup_labels=list(run.rgroup_labels),
        matched_count=run.matched_count,
        unmatched_count=run.unmatched_count,
        total_count=run.total_count,
        version=run.version,
    )


def _apply_to_model(model: RGroupDecompositionRunModel, run: RGroupDecompositionRun) -> None:
    model.status = run.status.value
    model.started_at = run.started_at
    model.completed_at = run.completed_at
    model.error_message = run.error_message
    model.rgroup_labels = list(run.rgroup_labels)
    model.matched_count = run.matched_count
    model.unmatched_count = run.unmatched_count
    model.total_count = run.total_count
    model.version = run.version


def _to_domain(model: RGroupDecompositionRunModel) -> RGroupDecompositionRun:
    return RGroupDecompositionRun(
        id=model.id,
        workspace_id=model.workspace_id,
        requested_by=model.requested_by,
        membership_hash=model.membership_hash,
        core_smiles=model.core_smiles,
        core_hash=model.core_hash,
        requested_at=model.requested_at,
        status=RGroupDecompositionRunStatus(model.status),
        started_at=model.started_at,
        completed_at=model.completed_at,
        error_message=model.error_message,
        rgroup_labels=list(model.rgroup_labels or []),
        matched_count=model.matched_count,
        unmatched_count=model.unmatched_count,
        total_count=model.total_count,
        version=model.version,
    )
```

- [ ] **Step 5: Run the Task-5 tests to confirm they pass**

Run: `cd backend && uv run pytest tests/integration/persistence/sar_analysis/test_rgroup_decomposition_run_repository.py -v`
Expected: the five Task-5 tests PASS (assignment-row tests don't exist yet).

- [ ] **Step 6: Commit**

```bash
git add src/cellar/application/sar_analysis/repositories.py src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/rgroup_decomposition_run_repository.py tests/integration/persistence/sar_analysis/test_rgroup_decomposition_run_repository.py
git commit -m "feat(sar): decomposition-run repository — save + find_by_id + (membership,core) cache" -- src/cellar/application/sar_analysis/repositories.py src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/rgroup_decomposition_run_repository.py tests/integration/persistence/sar_analysis/test_rgroup_decomposition_run_repository.py
```

---

## Task 6: Repository — assignment rows (write / fetch / count)

**Files:**
- Modify: `src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/rgroup_decomposition_run_repository.py`
- Test: `tests/integration/persistence/sar_analysis/test_rgroup_decomposition_run_repository.py`

- [ ] **Step 1: Write the failing assignment-row tests**

Append to `tests/integration/persistence/sar_analysis/test_rgroup_decomposition_run_repository.py`:

```python
from cellar.domain.sar_analysis.rgroup_types import RGroupAssignment


async def _persist_run(uow, *, workspace_id, membership_hash="mh-a", core_hash="ch-a"):
    run = RGroupDecompositionRun.create(
        workspace_id=workspace_id,
        requested_by=uuid.uuid4(),
        membership_hash=membership_hash,
        core_smiles="c1ccccc1",
        core_hash=core_hash,
        now=_NOW,
    )
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.save(run)
        await uow.commit()
    return run


@pytest.mark.asyncio
async def test_write_and_count_assignments(uow):
    ws = uuid.uuid4()
    run = await _persist_run(uow, workspace_id=ws)
    rows = [
        RGroupAssignment(molecule_id=uuid.uuid4(), rgroups={"R1": "F"}),
        RGroupAssignment(molecule_id=uuid.uuid4(), rgroups={"R1": "Cl"}),
        RGroupAssignment(molecule_id=uuid.uuid4(), rgroups={"R1": "Br"}),
    ]
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.write_assignments(run.id, rows)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        n = await repo.count_assignments(run.id, workspace_id=ws)

    assert n == 3


@pytest.mark.asyncio
async def test_fetch_assignments_paginates_stably(uow):
    ws = uuid.uuid4()
    run = await _persist_run(uow, workspace_id=ws, membership_hash="mh-b", core_hash="ch-b")
    rows = [
        RGroupAssignment(molecule_id=uuid.uuid4(), rgroups={"R1": str(i)}) for i in range(5)
    ]
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.write_assignments(run.id, rows)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        page1 = await repo.fetch_assignments(run.id, workspace_id=ws, offset=0, limit=2)
        page2 = await repo.fetch_assignments(run.id, workspace_id=ws, offset=2, limit=2)
        page3 = await repo.fetch_assignments(run.id, workspace_id=ws, offset=4, limit=2)

    seen = [a.molecule_id for a in (*page1, *page2, *page3)]
    assert len(seen) == 5
    assert len(set(seen)) == 5  # no overlap across pages — stable ordering


@pytest.mark.asyncio
async def test_fetch_count_scoped_to_workspace(uow):
    ws = uuid.uuid4()
    run = await _persist_run(uow, workspace_id=ws, membership_hash="mh-c", core_hash="ch-c")
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.write_assignments(
            run.id, [RGroupAssignment(molecule_id=uuid.uuid4(), rgroups={"R1": "F"})]
        )
        await uow.commit()

    other_ws = uuid.uuid4()
    async with uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        n = await repo.count_assignments(run.id, workspace_id=other_ws)
        rows = await repo.fetch_assignments(run.id, workspace_id=other_ws, offset=0, limit=10)

    assert n == 0        # the run belongs to ws, not other_ws
    assert rows == []
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/integration/persistence/sar_analysis/test_rgroup_decomposition_run_repository.py -k assignments -v`
Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: Implement the assignment-row methods**

In `rgroup_decomposition_run_repository.py`, add the import for `insert` at the top:

```python
from sqlalchemy import func, insert, select
```

Replace the three `raise NotImplementedError` stubs with:

```python
    async def write_assignments(
        self, run_id: UUID, assignments: list[RGroupAssignment]
    ) -> None:
        session = self._uow.session
        BATCH = 1000
        rows = [
            {"run_id": run_id, "molecule_id": a.molecule_id, "rgroups": a.rgroups}
            for a in assignments
        ]
        for i in range(0, len(rows), BATCH):
            await session.execute(insert(RGroupAssignmentModel), rows[i : i + BATCH])

    async def fetch_assignments(
        self, run_id: UUID, *, workspace_id: UUID, offset: int, limit: int
    ) -> list[RGroupAssignment]:
        session = self._uow.session
        stmt = (
            select(RGroupAssignmentModel)
            .join(
                RGroupDecompositionRunModel,
                RGroupDecompositionRunModel.id == RGroupAssignmentModel.run_id,
            )
            .where(
                RGroupAssignmentModel.run_id == run_id,
                RGroupDecompositionRunModel.workspace_id == workspace_id,
            )
            .order_by(RGroupAssignmentModel.molecule_id)
            .offset(offset)
            .limit(limit)
        )
        models = (await session.execute(stmt)).scalars().all()
        return [
            RGroupAssignment(molecule_id=m.molecule_id, rgroups=dict(m.rgroups))
            for m in models
        ]

    async def count_assignments(self, run_id: UUID, *, workspace_id: UUID) -> int:
        session = self._uow.session
        stmt = (
            select(func.count())
            .select_from(RGroupAssignmentModel)
            .join(
                RGroupDecompositionRunModel,
                RGroupDecompositionRunModel.id == RGroupAssignmentModel.run_id,
            )
            .where(
                RGroupAssignmentModel.run_id == run_id,
                RGroupDecompositionRunModel.workspace_id == workspace_id,
            )
        )
        return int((await session.execute(stmt)).scalar_one())
```

- [ ] **Step 4: Run the full repo test file to confirm everything passes**

Run: `cd backend && uv run pytest tests/integration/persistence/sar_analysis/test_rgroup_decomposition_run_repository.py -v`
Expected: all PASS (Task 5 + Task 6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/rgroup_decomposition_run_repository.py tests/integration/persistence/sar_analysis/test_rgroup_decomposition_run_repository.py
git commit -m "feat(sar): assignment-row write/fetch/count (batched, workspace-scoped)" -- src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/rgroup_decomposition_run_repository.py tests/integration/persistence/sar_analysis/test_rgroup_decomposition_run_repository.py
```

---

## Final verification

- [ ] **Run the whole SAR test surface touched by this plan:**

Run:
```bash
cd backend && uv run pytest \
  tests/unit/infrastructure/rdkit/test_streaming_rgroup_decomposer.py \
  tests/unit/domain/sar_analysis/test_rgroup_decomposition_run.py \
  tests/integration/persistence/sar_analysis/test_rgroup_decomposition_run_repository.py -v
```
Expected: all PASS.

- [ ] **Import-linter (Clean Architecture boundaries):**

Run: `cd backend && uv run lint-imports`
Expected: PASS — domain imports nothing outward; the decomposer lives in infrastructure.

---

## What this plan deliberately leaves for the next plan (Unit A, Part 1b)

- **Membership streaming + version-aware hash** (`compute_membership_hash` over `(id, version)` pairs; `core_hash` via RDKit canonicalization) and the batched collection-member iterator.
- **`StartDecompositionRun` / `RunDecomposition` use cases** (cache → inline ≤N → schedule; stream members → `session.add` → `session.finish` → `write_assignments` + `mark_ready`).
- **Temporal workflow + activity + Null orchestrator + DI wiring** (mirror `infrastructure/temporal/{workflows,orchestrators}/scaffold_tree.py`).
- **Routes** `POST /sar/decomposition`, `GET …/jobs/{id}`, `POST …/cancel`, and the enriched **`POST …/{run_id}/rows`** (the molecule + activity join — activity arrives with the Part 2 activity-projection plan).

---

## Self-Review

**Spec coverage (this slice):** §3 Pair-1 tables ✓ (Task 3/4) · run aggregate + state machine ✓ (Task 2) · assignments-as-rows not blob ✓ (Task 3/4/6) · `(membership_hash, core_hash)` cache ✓ (Task 5) · §8.1 streaming label stability ✓ (Task 1). Out-of-slice spec items (jobs, routes, activity, FE) are explicitly deferred above — not gaps.

**Placeholder scan:** none. The two `raise NotImplementedError` stubs in Task 5 are intentional, asserted-against by Task 6 Step 2, and replaced in Task 6 Step 3.

**Type consistency:** `mark_ready(*, rgroup_labels, matched_count, unmatched_count, total_count, now)` is called keyword-only in Task 2's test, Task 5's helpers, and the model mapping — consistent. `RGroupAssignment(molecule_id, rgroups)` (reused from `rgroup_types.py`) is used identically in Task 1, 5, 6. Repo method names (`save`, `find_by_id`, `find_cached`, `write_assignments`, `fetch_assignments`, `count_assignments`) match between the Protocol (Task 5 Step 1) and the impl (Tasks 5/6). `find_cached` signature is `(membership_hash, core_hash)` everywhere (no `ttl_seconds` — this cache is membership/core-keyed, never time-keyed).
