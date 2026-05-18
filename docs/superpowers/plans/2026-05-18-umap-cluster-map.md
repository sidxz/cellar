# V3 — UMAP Cluster Map + Diversify Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `?view=clusters` on `/collections/{id}` and `/search` — a Plotly UMAP scatter with peer Lasso + Diversify actions that terminate at "save as new collection".

**Architecture:** New members under the existing `sar_analysis` bounded context. Mirrors scaffold-tree V2 beat-for-beat: a `umap_jobs` table doubles as Postgres-backed cache (key = `ids_hash` + `picker` + `picker_param_hash`, 1h TTL), sync path for ≤500 mols, Temporal workflow otherwise, split-pane FE view (scatter left, `CardGrid` right).

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy async / `umap-learn` (jaccard metric) / RDKit `SimDivFilters.MaxMinPicker` + `ML.Cluster.Butina` / Temporal / Lagom DI / Next.js 16 / React Query / `react-plotly.js` (Scattergl).

**Parent spec:** `docs/superpowers/specs/2026-05-18-umap-cluster-map-design.md`.

**V2 reference patterns (read before starting):**
- `docs/superpowers/plans/2026-05-17-scaffold-tree-v2.md` — direct precedent for nearly every task here.
- `backend/src/cellar/domain/sar_analysis/scaffold_tree_job.py` — state-machine aggregate template.
- `backend/src/cellar/application/sar_analysis/start_scaffold_tree_job.py` — 3-path dispatch (cache hit / sync / async).
- `backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/scaffold_tree_job_repository.py` — `find_cached` shape.
- `backend/src/cellar/infrastructure/temporal/{workflows,activities,orchestrators}/scaffold_tree.py` — Temporal triad.
- `frontend/src/features/sar-analysis/components/scaffold-tree-view.tsx` — split-pane composition.
- `frontend/src/features/sar-analysis/hooks/use-scaffold-tree.ts` — sync/poll hook pattern.

---

## Task ordering at a glance

| # | Task | Layer |
|---|---|---|
| 1 | Add `umap-learn` dependency | BE-deps |
| 2 | Migration 039 — `umap_jobs` table + cache index | BE-data |
| 3 | `UmapPoint` / `ClusterAssignment` / `RepresentativePick` / `UmapResult` dataclasses | BE-compute |
| 4 | `UmapJob` aggregate + state machine | BE-async |
| 5 | `UmapJobRepository` (CRUD + cache lookup) | BE-async |
| 6 | `UmapEmbedder` infra (umap-learn wrapper) | BE-compute |
| 7 | `ButinaClusterer` infra (cluster + medoid picker) | BE-compute |
| 8 | `MaxMinPickerAdapter` infra | BE-compute |
| 9 | `ComputeUmapCluster` use case (cache-aware pipeline) | BE-compute |
| 10 | `StartUmapClusterJob` (sync/async dispatch) | BE-async |
| 11 | `UmapClusterWorkflow` + activity + orchestrator | BE-async |
| 12 | `GetUmapClusterJob` + `CancelUmapClusterJob` | BE-async |
| 13 | DI wiring (`_sar_analysis.py` extension + container) | BE-async |
| 14 | API routes (`umap_cluster.py` + register) | BE-API |
| 15 | Regenerate orval FE client | FE-types |
| 16 | FE wire types (extend `sar-analysis/types/index.ts`) | FE-types |
| 17 | `lasso-math.ts` (point-in-polygon) | FE-compute |
| 18 | `cluster-palette.ts` (palette + activity gradient adapters) | FE-compute |
| 19 | `usePickerConfig` + `useColorMode` URL hooks | FE-data |
| 20 | `useUmapCluster` hook (sync + async poll) | FE-data |
| 21 | `<ClusterScatter />` (Plotly + lasso) | FE-component |
| 22 | `<ColorModePicker />` (color-by dropdown + protocol sub-picker) | FE-component |
| 23 | `<ClusterToolbar />` (picker + N/threshold + Diversify + Save) | FE-component |
| 24 | `<ClusterSelectionPane />` (right-pane CardGrid wrapper) | FE-component |
| 25 | `<SaveSelectionDialog />` (modal preview before save) | FE-component |
| 26 | `<ClusterMapView />` (split-pane composition + selection state) | FE-component |
| 27 | View-mode toggle extension + `ResultsSurface` wiring + URL | FE-wire |

Manual smoke checklist at the end of this doc covers verification after Task 27.

---

## Task 1: Add `umap-learn` dependency

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock` (regenerated)

- [ ] **Step 1: Add dep**

```bash
cd /Users/sidx/workspace/chem-vault2/backend
uv add umap-learn
```

This pulls in `numba` + `pynndescent` transitively.

- [ ] **Step 2: Verify import**

```bash
uv run python -c "import umap; print(umap.__version__)"
```

Expected: a version string prints (typically 0.5.x), no ImportError.

- [ ] **Step 3: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock
git commit -m "chore(deps): add umap-learn for V3 cluster map"
```

---

## Task 2: Migration 039 — `umap_jobs` table

**Files:**
- Create: `backend/alembic/versions/039_umap_jobs.py`

- [ ] **Step 1: Create the migration**

```python
"""Add umap_jobs table for V3 cluster map.

Mirrors scaffold_tree_jobs from migration 038 but cache key includes picker.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "umap_jobs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ids_hash", sa.Text, nullable=False),
        sa.Column("picker", sa.Text, nullable=False),
        sa.Column("picker_params", sa.dialects.postgresql.JSONB, nullable=False),
        sa.Column("picker_param_hash", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("result_json", sa.dialects.postgresql.JSONB),
        sa.Column("error_message", sa.Text),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.CheckConstraint(
            "picker IN ('maxmin','butina')",
            name="ck_umap_jobs_picker",
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','ready','failed','cancelled')",
            name="ck_umap_jobs_status",
        ),
    )
    op.create_index(
        "umap_jobs_cache",
        "umap_jobs",
        ["ids_hash", "picker", "picker_param_hash", "completed_at"],
        unique=False,
        postgresql_where=sa.text("status = 'ready'"),
    )
    op.create_index(
        "umap_jobs_workspace",
        "umap_jobs",
        ["workspace_id", "requested_at"],
    )


def downgrade() -> None:
    op.drop_index("umap_jobs_workspace", table_name="umap_jobs")
    op.drop_index("umap_jobs_cache", table_name="umap_jobs")
    op.drop_table("umap_jobs")
```

- [ ] **Step 2: Apply against dev DB**

```bash
cd /Users/sidx/workspace/chem-vault2/backend
uv run alembic upgrade head
```

Expected: migration `039` applies; `\d umap_jobs` in psql shows the table.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/039_umap_jobs.py
git commit -m "feat(persistence): migration 039 — umap_jobs table for V3 cluster map"
```

---

## Task 3: `UmapResult` types

**Files:**
- Create: `backend/src/cellar/domain/sar_analysis/umap_types.py`
- Test: `backend/tests/unit/domain/sar_analysis/test_umap_types.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for UMAP cluster result dataclasses."""

from __future__ import annotations

from uuid import uuid4

from cellar.domain.sar_analysis.umap_types import (
    ClusterAssignment,
    RepresentativePick,
    UmapPoint,
    UmapResult,
)


def test_umap_point_round_trip() -> None:
    mid = uuid4()
    p = UmapPoint(molecule_id=mid, x=1.5, y=-0.3)
    assert p.molecule_id == mid
    assert p.x == 1.5
    assert p.y == -0.3


def test_umap_result_carries_full_payload() -> None:
    m1, m2 = uuid4(), uuid4()
    result = UmapResult(
        points=[UmapPoint(m1, 0.0, 0.0), UmapPoint(m2, 1.0, 1.0)],
        clusters=[ClusterAssignment(m1, 0), ClusterAssignment(m2, 1)],
        representatives=[RepresentativePick(m1, 0)],
        cluster_count=2,
        picker="maxmin",
        picker_params={"n": 1},
        skipped_molecule_ids=[],
    )
    assert len(result.points) == 2
    assert result.cluster_count == 2
    assert result.picker == "maxmin"
```

- [ ] **Step 2: Run + fail**

```bash
cd /Users/sidx/workspace/chem-vault2/backend
uv run pytest tests/unit/domain/sar_analysis/test_umap_types.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement**

```python
"""Pure dataclasses for the UMAP + cluster + picker result payload."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class UmapPoint:
    molecule_id: UUID
    x: float
    y: float


@dataclass(frozen=True)
class ClusterAssignment:
    molecule_id: UUID
    cluster_id: int


@dataclass(frozen=True)
class RepresentativePick:
    molecule_id: UUID
    cluster_id: int


@dataclass(frozen=True)
class UmapResult:
    points: list[UmapPoint]
    clusters: list[ClusterAssignment]
    representatives: list[RepresentativePick]
    cluster_count: int
    picker: str  # "maxmin" | "butina"
    picker_params: dict[str, Any]
    skipped_molecule_ids: list[UUID] = field(default_factory=list)
```

- [ ] **Step 4: Run + pass**

```bash
uv run pytest tests/unit/domain/sar_analysis/test_umap_types.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/domain/sar_analysis/umap_types.py backend/tests/unit/domain/sar_analysis/test_umap_types.py
git commit -m "feat(domain): UmapResult + UmapPoint + cluster types for V3"
```

---

## Task 4: `UmapJob` aggregate + state machine

**Files:**
- Create: `backend/src/cellar/domain/sar_analysis/umap_job.py`
- Test: `backend/tests/unit/domain/sar_analysis/test_umap_job.py`

Mirror `scaffold_tree_job.py` exactly, swapping the result type for `UmapResult` and adding the `picker` + `picker_params` + `picker_param_hash` fields.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for the UmapJob state machine."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from cellar.domain.sar_analysis.umap_job import (
    InvalidUmapJobTransition,
    UmapJob,
    UmapJobStatus,
)
from cellar.domain.sar_analysis.umap_types import UmapResult


def _now() -> datetime:
    return datetime(2026, 5, 18, 12, 0, 0, tzinfo=timezone.utc)


def _empty_result() -> UmapResult:
    return UmapResult(
        points=[],
        clusters=[],
        representatives=[],
        cluster_count=0,
        picker="maxmin",
        picker_params={"n": 50},
    )


def test_create_starts_pending() -> None:
    job = UmapJob.create(
        workspace_id=uuid4(),
        requested_by=uuid4(),
        ids_hash="h",
        picker="maxmin",
        picker_params={"n": 50},
        picker_param_hash="ph",
        now=_now(),
    )
    assert job.status == UmapJobStatus.PENDING


def test_pending_to_running_to_ready() -> None:
    job = UmapJob.create(
        workspace_id=uuid4(),
        requested_by=uuid4(),
        ids_hash="h",
        picker="maxmin",
        picker_params={"n": 50},
        picker_param_hash="ph",
        now=_now(),
    )
    job = job.mark_running(_now())
    assert job.status == UmapJobStatus.RUNNING
    job = job.mark_ready(_empty_result(), _now())
    assert job.status == UmapJobStatus.READY
    assert job.result is not None


def test_cannot_ready_from_pending() -> None:
    job = UmapJob.create(
        workspace_id=uuid4(),
        requested_by=uuid4(),
        ids_hash="h",
        picker="maxmin",
        picker_params={"n": 50},
        picker_param_hash="ph",
        now=_now(),
    )
    with pytest.raises(InvalidUmapJobTransition):
        job.mark_ready(_empty_result(), _now())


def test_cannot_cancel_terminal() -> None:
    job = (
        UmapJob.create(
            workspace_id=uuid4(),
            requested_by=uuid4(),
            ids_hash="h",
            picker="maxmin",
            picker_params={"n": 50},
            picker_param_hash="ph",
            now=_now(),
        )
        .mark_running(_now())
        .mark_failed("oops", _now())
    )
    with pytest.raises(InvalidUmapJobTransition):
        job.mark_cancelled(_now())
```

- [ ] **Step 2: Run + fail**

```bash
uv run pytest tests/unit/domain/sar_analysis/test_umap_job.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement**

```python
"""UmapJob — persisted unit of async UMAP compute.

State machine:
  pending -> running -> {ready | failed | cancelled}
  pending             ->  cancelled

ready / failed / cancelled are terminal.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any
from uuid import UUID

from cellar.domain.sar_analysis.umap_types import UmapResult


class UmapJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InvalidUmapJobTransition(Exception):
    pass


_TERMINAL = {
    UmapJobStatus.READY,
    UmapJobStatus.FAILED,
    UmapJobStatus.CANCELLED,
}


@dataclass(frozen=True)
class UmapJob:
    id: UUID
    workspace_id: UUID
    requested_by: UUID
    ids_hash: str
    picker: str
    picker_params: dict[str, Any]
    picker_param_hash: str
    requested_at: datetime
    status: UmapJobStatus = UmapJobStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    result: UmapResult | None = None
    version: int = 1

    @classmethod
    def create(
        cls,
        *,
        workspace_id: UUID,
        requested_by: UUID,
        ids_hash: str,
        picker: str,
        picker_params: dict[str, Any],
        picker_param_hash: str,
        now: datetime,
    ) -> "UmapJob":
        return cls(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            requested_by=requested_by,
            ids_hash=ids_hash,
            picker=picker,
            picker_params=dict(picker_params),
            picker_param_hash=picker_param_hash,
            requested_at=now,
        )

    def mark_running(self, now: datetime) -> "UmapJob":
        if self.status != UmapJobStatus.PENDING:
            raise InvalidUmapJobTransition(f"Cannot mark RUNNING from {self.status}")
        return replace(self, status=UmapJobStatus.RUNNING, started_at=now)

    def mark_ready(self, result: UmapResult, now: datetime) -> "UmapJob":
        if self.status != UmapJobStatus.RUNNING:
            raise InvalidUmapJobTransition(f"Cannot mark READY from {self.status}")
        return replace(
            self,
            status=UmapJobStatus.READY,
            completed_at=now,
            result=result,
        )

    def mark_failed(self, error: str, now: datetime) -> "UmapJob":
        if self.status not in {UmapJobStatus.PENDING, UmapJobStatus.RUNNING}:
            raise InvalidUmapJobTransition(f"Cannot mark FAILED from {self.status}")
        return replace(
            self,
            status=UmapJobStatus.FAILED,
            completed_at=now,
            error_message=error,
        )

    def mark_cancelled(self, now: datetime) -> "UmapJob":
        if self.status in _TERMINAL:
            raise InvalidUmapJobTransition(f"Cannot CANCEL terminal {self.status}")
        return replace(
            self,
            status=UmapJobStatus.CANCELLED,
            completed_at=now,
        )
```

- [ ] **Step 4: Run + pass**

```bash
uv run pytest tests/unit/domain/sar_analysis/test_umap_job.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/domain/sar_analysis/umap_job.py backend/tests/unit/domain/sar_analysis/test_umap_job.py
git commit -m "feat(domain): UmapJob aggregate + state machine"
```

---

## Task 5: `UmapJobRepository`

**Files:**
- Modify: `backend/src/cellar/application/sar_analysis/repositories.py` (extend with `UmapJobRepository` Protocol)
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/umap_job_repository.py`
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/umap_job_model.py`
- Test: `backend/tests/integration/persistence/sar_analysis/test_umap_job_repository.py`

Mirror `scaffold_tree_job_repository.py` exactly. The only difference is `find_cached` keys on three columns instead of one: `(ids_hash, picker, picker_param_hash)`.

- [ ] **Step 1: Extend the repositories Protocol module**

Edit `backend/src/cellar/application/sar_analysis/repositories.py` — add `UmapJobRepository`:

```python
from typing import Protocol
from uuid import UUID

from cellar.domain.sar_analysis.umap_job import UmapJob


class UmapJobRepository(Protocol):
    async def save(self, job: UmapJob) -> None: ...
    async def find_by_id(self, job_id: UUID) -> UmapJob | None: ...
    async def find_cached(
        self,
        *,
        ids_hash: str,
        picker: str,
        picker_param_hash: str,
        ttl_seconds: int,
    ) -> UmapJob | None: ...
```

(Keep existing `ScaffoldTreeJobRepository` Protocol in place — append, don't replace.)

- [ ] **Step 2: Create the SQLAlchemy model**

```python
"""UmapJobModel — SQLAlchemy table mapping for umap_jobs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from cellar.infrastructure.persistence.sqlalchemy.base import Base


class UmapJobModel(Base):
    __tablename__ = "umap_jobs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    requested_by: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    ids_hash: Mapped[str] = mapped_column(Text, nullable=False)
    picker: Mapped[str] = mapped_column(Text, nullable=False)
    picker_params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    picker_param_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    __table_args__ = (
        CheckConstraint("picker IN ('maxmin','butina')", name="ck_umap_jobs_picker"),
        CheckConstraint(
            "status IN ('pending','running','ready','failed','cancelled')",
            name="ck_umap_jobs_status",
        ),
    )
```

- [ ] **Step 3: Write the failing repository test**

Mirror `tests/integration/persistence/sar_analysis/test_scaffold_tree_job_repository.py`:

```python
"""Integration tests for UmapJobRepository.

Round-trip save+find, plus the cache lookup (ids_hash + picker + picker_param_hash + ttl)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from cellar.domain.sar_analysis.umap_job import UmapJob, UmapJobStatus
from cellar.domain.sar_analysis.umap_types import UmapResult
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.umap_job_repository import (
    SQLAlchemyUmapJobRepository,
)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _empty_result(picker: str = "maxmin") -> UmapResult:
    return UmapResult(
        points=[],
        clusters=[],
        representatives=[],
        cluster_count=0,
        picker=picker,
        picker_params={"n": 50} if picker == "maxmin" else {"threshold": 0.4},
    )


@pytest.mark.asyncio
async def test_round_trip(session) -> None:
    repo = SQLAlchemyUmapJobRepository(session)
    job = UmapJob.create(
        workspace_id=uuid4(),
        requested_by=uuid4(),
        ids_hash="abc",
        picker="maxmin",
        picker_params={"n": 50},
        picker_param_hash="ph",
        now=_now(),
    )
    await repo.save(job)
    await session.commit()
    found = await repo.find_by_id(job.id)
    assert found is not None
    assert found.id == job.id
    assert found.status == UmapJobStatus.PENDING


@pytest.mark.asyncio
async def test_find_cached_hits_ready_within_ttl(session) -> None:
    repo = SQLAlchemyUmapJobRepository(session)
    now = _now()
    job = (
        UmapJob.create(
            workspace_id=uuid4(),
            requested_by=uuid4(),
            ids_hash="X",
            picker="maxmin",
            picker_params={"n": 50},
            picker_param_hash="ph",
            now=now - timedelta(minutes=5),
        )
        .mark_running(now - timedelta(minutes=4))
        .mark_ready(_empty_result(), now - timedelta(minutes=3))
    )
    await repo.save(job)
    await session.commit()
    found = await repo.find_cached(
        ids_hash="X", picker="maxmin", picker_param_hash="ph", ttl_seconds=3600
    )
    assert found is not None
    assert found.status == UmapJobStatus.READY


@pytest.mark.asyncio
async def test_find_cached_misses_on_different_picker(session) -> None:
    repo = SQLAlchemyUmapJobRepository(session)
    now = _now()
    job = (
        UmapJob.create(
            workspace_id=uuid4(),
            requested_by=uuid4(),
            ids_hash="X",
            picker="maxmin",
            picker_params={"n": 50},
            picker_param_hash="phA",
            now=now - timedelta(minutes=3),
        )
        .mark_running(now - timedelta(minutes=2))
        .mark_ready(_empty_result(), now - timedelta(minutes=1))
    )
    await repo.save(job)
    await session.commit()
    miss = await repo.find_cached(
        ids_hash="X", picker="butina", picker_param_hash="phA", ttl_seconds=3600
    )
    assert miss is None


@pytest.mark.asyncio
async def test_find_cached_misses_past_ttl(session) -> None:
    repo = SQLAlchemyUmapJobRepository(session)
    now = _now()
    job = (
        UmapJob.create(
            workspace_id=uuid4(),
            requested_by=uuid4(),
            ids_hash="X",
            picker="maxmin",
            picker_params={"n": 50},
            picker_param_hash="ph",
            now=now - timedelta(hours=3),
        )
        .mark_running(now - timedelta(hours=2, minutes=59))
        .mark_ready(_empty_result(), now - timedelta(hours=2))
    )
    await repo.save(job)
    await session.commit()
    miss = await repo.find_cached(
        ids_hash="X", picker="maxmin", picker_param_hash="ph", ttl_seconds=3600
    )
    assert miss is None
```

- [ ] **Step 4: Implement the repo**

Mirror `scaffold_tree_job_repository.py` shape; key differences are the extra cache columns and the `UmapResult` JSON encoding. Show full implementation:

```python
"""SQLAlchemy implementation of UmapJobRepository."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cellar.domain.sar_analysis.umap_job import UmapJob, UmapJobStatus
from cellar.domain.sar_analysis.umap_types import (
    ClusterAssignment,
    RepresentativePick,
    UmapPoint,
    UmapResult,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.umap_job_model import (
    UmapJobModel,
)


def _encode_result(result: UmapResult) -> dict[str, Any]:
    return {
        "points": [
            {"molecule_id": str(p.molecule_id), "x": p.x, "y": p.y}
            for p in result.points
        ],
        "clusters": [
            {"molecule_id": str(c.molecule_id), "cluster_id": c.cluster_id}
            for c in result.clusters
        ],
        "representatives": [
            {"molecule_id": str(r.molecule_id), "cluster_id": r.cluster_id}
            for r in result.representatives
        ],
        "cluster_count": result.cluster_count,
        "picker": result.picker,
        "picker_params": result.picker_params,
        "skipped_molecule_ids": [str(m) for m in result.skipped_molecule_ids],
    }


def _decode_result(payload: dict[str, Any]) -> UmapResult:
    return UmapResult(
        points=[
            UmapPoint(molecule_id=UUID(p["molecule_id"]), x=p["x"], y=p["y"])
            for p in payload["points"]
        ],
        clusters=[
            ClusterAssignment(molecule_id=UUID(c["molecule_id"]), cluster_id=c["cluster_id"])
            for c in payload["clusters"]
        ],
        representatives=[
            RepresentativePick(
                molecule_id=UUID(r["molecule_id"]), cluster_id=r["cluster_id"]
            )
            for r in payload["representatives"]
        ],
        cluster_count=payload["cluster_count"],
        picker=payload["picker"],
        picker_params=payload["picker_params"],
        skipped_molecule_ids=[UUID(m) for m in payload.get("skipped_molecule_ids", [])],
    )


def _model_to_domain(m: UmapJobModel) -> UmapJob:
    return UmapJob(
        id=m.id,
        workspace_id=m.workspace_id,
        requested_by=m.requested_by,
        ids_hash=m.ids_hash,
        picker=m.picker,
        picker_params=m.picker_params,
        picker_param_hash=m.picker_param_hash,
        requested_at=m.requested_at,
        status=UmapJobStatus(m.status),
        started_at=m.started_at,
        completed_at=m.completed_at,
        error_message=m.error_message,
        result=_decode_result(m.result_json) if m.result_json else None,
        version=m.version,
    )


def _domain_to_model(j: UmapJob) -> UmapJobModel:
    return UmapJobModel(
        id=j.id,
        workspace_id=j.workspace_id,
        requested_by=j.requested_by,
        ids_hash=j.ids_hash,
        picker=j.picker,
        picker_params=j.picker_params,
        picker_param_hash=j.picker_param_hash,
        status=j.status.value,
        result_json=_encode_result(j.result) if j.result else None,
        error_message=j.error_message,
        requested_at=j.requested_at,
        started_at=j.started_at,
        completed_at=j.completed_at,
        version=j.version,
    )


class SQLAlchemyUmapJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, job: UmapJob) -> None:
        await self._session.merge(_domain_to_model(job))

    async def find_by_id(self, job_id: UUID) -> UmapJob | None:
        m = await self._session.get(UmapJobModel, job_id)
        return _model_to_domain(m) if m else None

    async def find_cached(
        self,
        *,
        ids_hash: str,
        picker: str,
        picker_param_hash: str,
        ttl_seconds: int,
    ) -> UmapJob | None:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(seconds=ttl_seconds)
        stmt = (
            select(UmapJobModel)
            .where(
                UmapJobModel.ids_hash == ids_hash,
                UmapJobModel.picker == picker,
                UmapJobModel.picker_param_hash == picker_param_hash,
                UmapJobModel.status == UmapJobStatus.READY.value,
                UmapJobModel.completed_at >= cutoff,
            )
            .order_by(UmapJobModel.completed_at.desc())
            .limit(1)
        )
        m = (await self._session.execute(stmt)).scalar_one_or_none()
        return _model_to_domain(m) if m else None
```

- [ ] **Step 5: Run tests + pass**

```bash
uv run pytest tests/integration/persistence/sar_analysis/test_umap_job_repository.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/application/sar_analysis/repositories.py \
        backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/umap_job_repository.py \
        backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/umap_job_model.py \
        backend/tests/integration/persistence/sar_analysis/test_umap_job_repository.py
git commit -m "feat(persistence): UmapJobRepository with picker-aware cache lookup"
```

---

## Task 6: `UmapEmbedder` infra (umap-learn wrapper)

**Files:**
- Create: `backend/src/cellar/infrastructure/rdkit/umap_embedder.py`
- Test: `backend/tests/unit/infrastructure/rdkit/test_umap_embedder.py`

- [ ] **Step 1: Write the failing test**

```python
"""UmapEmbedder unit tests — small-fingerprint golden + determinism."""

from __future__ import annotations

import numpy as np

from cellar.infrastructure.rdkit.umap_embedder import UmapEmbedder


def _make_random_bit_fps(n: int, dim: int = 2048, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, 2, size=(n, dim), dtype=np.uint8)


def test_embedder_returns_shape_n_by_2() -> None:
    fps = _make_random_bit_fps(30)
    emb = UmapEmbedder()
    coords = emb.embed(fps)
    assert coords.shape == (30, 2)


def test_embedder_is_deterministic_with_fixed_seed() -> None:
    fps = _make_random_bit_fps(30)
    a = UmapEmbedder().embed(fps)
    b = UmapEmbedder().embed(fps)
    np.testing.assert_allclose(a, b)
```

- [ ] **Step 2: Run + fail**

```bash
uv run pytest tests/unit/infrastructure/rdkit/test_umap_embedder.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement**

```python
"""UMAP embedding wrapper — Tanimoto-equivalent jaccard metric on binary FPs.

Pinned defaults: n_neighbors=15, min_dist=0.1, metric=jaccard, random_state=42.
"""

from __future__ import annotations

import numpy as np
import umap


class UmapEmbedder:
    """Thin wrapper around umap-learn with cheminformatics defaults locked.

    Defaults intentionally not user-tunable in V3 (see spec §3).
    """

    def __init__(
        self,
        *,
        n_neighbors: int = 15,
        min_dist: float = 0.1,
        metric: str = "jaccard",
        random_state: int = 42,
    ) -> None:
        self._n_neighbors = n_neighbors
        self._min_dist = min_dist
        self._metric = metric
        self._random_state = random_state

    def embed(self, fingerprints: np.ndarray) -> np.ndarray:
        """Embed a stack of binary fingerprints to 2D coords.

        Caller is responsible for ensuring at least 10 rows (spec §4.8).
        """
        # umap-learn refuses n_neighbors > n_samples - 1; clamp.
        effective_neighbors = min(self._n_neighbors, max(2, fingerprints.shape[0] - 1))
        reducer = umap.UMAP(
            n_components=2,
            n_neighbors=effective_neighbors,
            min_dist=self._min_dist,
            metric=self._metric,
            random_state=self._random_state,
        )
        return reducer.fit_transform(fingerprints)
```

- [ ] **Step 4: Run + pass**

```bash
uv run pytest tests/unit/infrastructure/rdkit/test_umap_embedder.py -v
```

Expected: 2 passed (slow first time — `numba` JITs).

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/rdkit/umap_embedder.py backend/tests/unit/infrastructure/rdkit/test_umap_embedder.py
git commit -m "feat(rdkit): UmapEmbedder — jaccard metric + pinned defaults"
```

---

## Task 7: `ButinaClusterer` infra

**Files:**
- Create: `backend/src/cellar/infrastructure/rdkit/butina_clusterer.py`
- Test: `backend/tests/unit/infrastructure/rdkit/test_butina_clusterer.py`

- [ ] **Step 1: Write the failing test**

```python
"""ButinaClusterer unit tests — cluster count varies with threshold, medoid picked."""

from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import AllChem

from cellar.infrastructure.rdkit.butina_clusterer import ButinaClusterer


def _ecfp4(smiles: str):
    mol = Chem.MolFromSmiles(smiles)
    return AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048)


def test_butina_groups_similar_compounds() -> None:
    # Two clear chemotype islands: simple benzenes + pyridines.
    smiles = ["c1ccccc1", "Cc1ccccc1", "CCc1ccccc1", "c1ccncc1", "Cc1ccncc1"]
    fps = [_ecfp4(s) for s in smiles]
    clusterer = ButinaClusterer(threshold=0.4)
    clusters, medoids = clusterer.cluster(fps)
    assert len(clusters) == len(fps)
    # Each compound has a cluster id; medoid list has one entry per distinct cluster.
    assert set(clusters) == set(range(max(clusters) + 1))
    assert len(medoids) == max(clusters) + 1
```

- [ ] **Step 2: Run + fail**

- [ ] **Step 3: Implement**

```python
"""Butina clustering wrapper — returns per-compound cluster ids + per-cluster medoid index."""

from __future__ import annotations

from rdkit import DataStructs
from rdkit.ML.Cluster import Butina


class ButinaClusterer:
    """Threshold-based clustering on Tanimoto distance.

    Returns:
        clusters: list[int] of length n, mapping compound index -> cluster id.
        medoid_indices: list[int] of length cluster_count, first member of each cluster
            (RDKit Butina returns clusters as tuples where index 0 is the cluster centroid).
    """

    def __init__(self, *, threshold: float = 0.4) -> None:
        self._threshold = threshold

    def cluster(self, fingerprints: list) -> tuple[list[int], list[int]]:
        n = len(fingerprints)
        # Compute lower-triangle Tanimoto-distance matrix.
        dists: list[float] = []
        for i in range(1, n):
            sims = DataStructs.BulkTanimotoSimilarity(fingerprints[i], fingerprints[:i])
            dists.extend(1.0 - s for s in sims)

        cluster_tuples = Butina.ClusterData(
            dists, n, self._threshold, isDistData=True
        )
        # Butina convention: tuples[k][0] is the cluster centroid (medoid) compound index.
        cluster_ids = [0] * n
        medoid_indices: list[int] = []
        for cid, members in enumerate(cluster_tuples):
            medoid_indices.append(members[0])
            for m in members:
                cluster_ids[m] = cid
        return cluster_ids, medoid_indices
```

- [ ] **Step 4: Run + pass**

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/rdkit/butina_clusterer.py backend/tests/unit/infrastructure/rdkit/test_butina_clusterer.py
git commit -m "feat(rdkit): ButinaClusterer — threshold-based clustering + medoid pick"
```

---

## Task 8: `MaxMinPickerAdapter` infra

**Files:**
- Create: `backend/src/cellar/infrastructure/rdkit/maxmin_picker.py`
- Test: `backend/tests/unit/infrastructure/rdkit/test_maxmin_picker.py`

- [ ] **Step 1: Write the failing test**

```python
"""MaxMinPickerAdapter — picks N diverse indices via RDKit SimDivFilters."""

from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import AllChem

from cellar.infrastructure.rdkit.maxmin_picker import MaxMinPickerAdapter


def _ecfp4(smiles: str):
    mol = Chem.MolFromSmiles(smiles)
    return AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048)


def test_maxmin_picks_distinct_indices_in_range() -> None:
    smiles = ["c1ccccc1", "Cc1ccccc1", "CCc1ccccc1", "c1ccncc1", "Cc1ccncc1", "CCO", "O=C(O)CCC"]
    fps = [_ecfp4(s) for s in smiles]
    picker = MaxMinPickerAdapter()
    picks = picker.pick(fps, n=4)
    assert len(picks) == 4
    assert len(set(picks)) == 4  # no duplicates
    assert all(0 <= p < len(fps) for p in picks)


def test_maxmin_returns_all_when_n_exceeds_size() -> None:
    smiles = ["c1ccccc1", "CCO"]
    fps = [_ecfp4(s) for s in smiles]
    picker = MaxMinPickerAdapter()
    picks = picker.pick(fps, n=10)
    assert sorted(picks) == [0, 1]
```

- [ ] **Step 2: Run + fail**

- [ ] **Step 3: Implement**

```python
"""MaxMin diverse-subset picker wrapper."""

from __future__ import annotations

from rdkit import DataStructs
from rdkit.SimDivFilters import MaxMinPicker


class MaxMinPickerAdapter:
    """Greedy diverse-subset selection on Tanimoto similarity.

    Wraps RDKit's MaxMinPicker.LazyBitVectorPick — at each step picks the compound
    farthest from all already-picked compounds. Deterministic given firstPicks (seed).
    """

    def __init__(self, *, seed: int = 42) -> None:
        self._seed = seed

    def pick(self, fingerprints: list, *, n: int) -> list[int]:
        size = len(fingerprints)
        if n >= size:
            return list(range(size))

        def dist_fn(i: int, j: int) -> float:
            return 1.0 - DataStructs.TanimotoSimilarity(fingerprints[i], fingerprints[j])

        picker = MaxMinPicker()
        picks = picker.LazyPick(dist_fn, size, n, seed=self._seed)
        return list(picks)
```

- [ ] **Step 4: Run + pass**

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/rdkit/maxmin_picker.py backend/tests/unit/infrastructure/rdkit/test_maxmin_picker.py
git commit -m "feat(rdkit): MaxMinPickerAdapter — diverse subset selection"
```

---

## Task 9: `ComputeUmapCluster` use case

**Files:**
- Create: `backend/src/cellar/application/sar_analysis/compute_umap_cluster.py`
- Test: `backend/tests/unit/application/sar_analysis/test_compute_umap_cluster.py`

This is the pure runner consumed by both the sync path AND the Temporal activity. Loads fingerprints from the molecule repo, runs embed + butina + picker, returns a `UmapResult`.

- [ ] **Step 1: Write the failing test**

```python
"""ComputeUmapCluster — orchestrates embed + cluster + pick.

Uses fakes for the FP loader so tests stay deterministic + fast."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from uuid import UUID, uuid4

import pytest

from cellar.application.sar_analysis.compute_umap_cluster import (
    ComputeUmapCluster,
    ComputeUmapClusterInput,
)


@dataclass
class _FakeFp:
    bits: tuple[int, ...]


class _FakeFingerprintLoader:
    def __init__(self, items: dict[UUID, _FakeFp]) -> None:
        self._items = items

    async def load_morgan(self, ids: Iterable[UUID]) -> dict[UUID, object]:
        return {i: self._items[i] for i in ids if i in self._items}


class _FakeEmbedder:
    def embed(self, fps):
        # Just give each row coords = (row_index, 0).
        return [[float(i), 0.0] for i in range(len(fps))]


class _FakeButina:
    def cluster(self, fps):
        # All in one cluster, medoid = 0.
        return [0] * len(fps), [0]


class _FakeMaxMin:
    def pick(self, fps, *, n):
        return list(range(min(n, len(fps))))


@pytest.mark.asyncio
async def test_compute_returns_full_result_payload() -> None:
    ids = [uuid4() for _ in range(12)]
    fps = {i: _FakeFp(bits=(0,) * 8) for i in ids}
    runner = ComputeUmapCluster(
        fingerprint_loader=_FakeFingerprintLoader(fps),
        embedder=_FakeEmbedder(),
        clusterer=_FakeButina(),
        maxmin_picker=_FakeMaxMin(),
    )
    out = await runner.execute(
        ComputeUmapClusterInput(
            molecule_ids=ids,
            picker="maxmin",
            picker_params={"n": 5},
        )
    )
    assert len(out.points) == 12
    assert out.cluster_count == 1
    assert len(out.representatives) == 5
    assert out.picker == "maxmin"


@pytest.mark.asyncio
async def test_compute_uses_butina_medoids_when_picker_butina() -> None:
    ids = [uuid4() for _ in range(8)]
    fps = {i: _FakeFp(bits=(0,) * 8) for i in ids}
    runner = ComputeUmapCluster(
        fingerprint_loader=_FakeFingerprintLoader(fps),
        embedder=_FakeEmbedder(),
        clusterer=_FakeButina(),
        maxmin_picker=_FakeMaxMin(),
    )
    out = await runner.execute(
        ComputeUmapClusterInput(
            molecule_ids=ids,
            picker="butina",
            picker_params={"threshold": 0.4},
        )
    )
    # With our fake butina, 1 cluster -> 1 medoid.
    assert len(out.representatives) == 1


@pytest.mark.asyncio
async def test_compute_skips_missing_fingerprints() -> None:
    ids = [uuid4() for _ in range(5)]
    # Only first 3 have fps.
    fps = {ids[0]: _FakeFp(()), ids[1]: _FakeFp(()), ids[2]: _FakeFp(())}
    runner = ComputeUmapCluster(
        fingerprint_loader=_FakeFingerprintLoader(fps),
        embedder=_FakeEmbedder(),
        clusterer=_FakeButina(),
        maxmin_picker=_FakeMaxMin(),
    )
    out = await runner.execute(
        ComputeUmapClusterInput(
            molecule_ids=ids,
            picker="maxmin",
            picker_params={"n": 2},
        )
    )
    assert len(out.points) == 3
    assert len(out.skipped_molecule_ids) == 2
```

- [ ] **Step 2: Run + fail**

- [ ] **Step 3: Implement**

```python
"""ComputeUmapCluster — pure runner: load FPs -> embed -> cluster -> pick.

Always runs Butina (used for color=cluster even when picker=maxmin).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Protocol
from uuid import UUID

import numpy as np

from cellar.domain.sar_analysis.umap_types import (
    ClusterAssignment,
    RepresentativePick,
    UmapPoint,
    UmapResult,
)


@dataclass(frozen=True)
class ComputeUmapClusterInput:
    molecule_ids: list[UUID]
    picker: str  # "maxmin" | "butina"
    picker_params: dict[str, Any]


class FingerprintLoader(Protocol):
    async def load_morgan(self, ids: Iterable[UUID]) -> dict[UUID, Any]: ...


class Embedder(Protocol):
    def embed(self, fingerprints) -> Any: ...


class Clusterer(Protocol):
    def cluster(self, fingerprints) -> tuple[list[int], list[int]]: ...


class MaxMinPickerProto(Protocol):
    def pick(self, fingerprints, *, n: int) -> list[int]: ...


def compute_ids_hash(ids: list[UUID]) -> str:
    h = hashlib.sha256()
    for i in sorted(str(x) for x in ids):
        h.update(i.encode())
    return h.hexdigest()


def compute_picker_param_hash(picker: str, params: dict[str, Any]) -> str:
    payload = json.dumps({"picker": picker, "params": params}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


class ComputeUmapCluster:
    def __init__(
        self,
        *,
        fingerprint_loader: FingerprintLoader,
        embedder: Embedder,
        clusterer: Clusterer,
        maxmin_picker: MaxMinPickerProto,
    ) -> None:
        self._loader = fingerprint_loader
        self._embedder = embedder
        self._clusterer = clusterer
        self._maxmin = maxmin_picker

    async def execute(self, payload: ComputeUmapClusterInput) -> UmapResult:
        loaded = await self._loader.load_morgan(payload.molecule_ids)
        ordered_ids = [i for i in payload.molecule_ids if i in loaded]
        skipped = [i for i in payload.molecule_ids if i not in loaded]
        if not ordered_ids:
            return UmapResult(
                points=[],
                clusters=[],
                representatives=[],
                cluster_count=0,
                picker=payload.picker,
                picker_params=payload.picker_params,
                skipped_molecule_ids=skipped,
            )

        fps = [loaded[i] for i in ordered_ids]

        # Embed -> 2D coords.
        embed_input = np.array([list(getattr(f, "bits", f)) for f in fps])
        coords = np.asarray(self._embedder.embed(embed_input))

        # Always cluster (used for coloring even when picker=maxmin).
        cluster_ids, medoid_indices = self._clusterer.cluster(fps)

        # Pick.
        if payload.picker == "maxmin":
            n = int(payload.picker_params.get("n", 50))
            pick_indices = self._maxmin.pick(fps, n=n)
            rep_assignments = [
                (idx, cluster_ids[idx]) for idx in pick_indices
            ]
        elif payload.picker == "butina":
            rep_assignments = [(idx, cluster_ids[idx]) for idx in medoid_indices]
        else:  # pragma: no cover - guarded at API layer
            raise ValueError(f"Unknown picker: {payload.picker}")

        points = [
            UmapPoint(molecule_id=mid, x=float(coords[i, 0]), y=float(coords[i, 1]))
            for i, mid in enumerate(ordered_ids)
        ]
        clusters = [
            ClusterAssignment(molecule_id=mid, cluster_id=cluster_ids[i])
            for i, mid in enumerate(ordered_ids)
        ]
        representatives = [
            RepresentativePick(molecule_id=ordered_ids[idx], cluster_id=cid)
            for idx, cid in rep_assignments
        ]

        return UmapResult(
            points=points,
            clusters=clusters,
            representatives=representatives,
            cluster_count=max(cluster_ids) + 1 if cluster_ids else 0,
            picker=payload.picker,
            picker_params=payload.picker_params,
            skipped_molecule_ids=skipped,
        )
```

- [ ] **Step 4: Run + pass**

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/application/sar_analysis/compute_umap_cluster.py backend/tests/unit/application/sar_analysis/test_compute_umap_cluster.py
git commit -m "feat(sar): ComputeUmapCluster — embed + cluster + pick pipeline"
```

---

## Task 10: `StartUmapClusterJob` (sync/async dispatch)

**Files:**
- Create: `backend/src/cellar/application/sar_analysis/start_umap_cluster_job.py`
- Test: `backend/tests/unit/application/sar_analysis/test_start_umap_cluster_job.py`

Mirror `StartScaffoldTreeJob`. The only structural differences: 3-key cache lookup (`ids_hash + picker + picker_param_hash`), and the orchestrator passes `picker` + `picker_params` to the workflow.

- [ ] **Step 1: Write the failing test**

```python
"""StartUmapClusterJob — 3-path dispatch: cache hit / sync / async."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest

from cellar.application.sar_analysis.compute_umap_cluster import (
    ComputeUmapCluster,
    ComputeUmapClusterInput,
)
from cellar.application.sar_analysis.start_umap_cluster_job import (
    StartUmapClusterJob,
    StartUmapClusterJobInput,
)
from cellar.domain.sar_analysis.umap_job import UmapJob, UmapJobStatus
from cellar.domain.sar_analysis.umap_types import UmapResult


class _FakeRepo:
    def __init__(self) -> None:
        self.saved: list[UmapJob] = []
        self.cached: UmapJob | None = None

    async def save(self, job: UmapJob) -> None:
        self.saved.append(job)

    async def find_by_id(self, _id: UUID) -> UmapJob | None:
        return None

    async def find_cached(self, **_kwargs) -> UmapJob | None:
        return self.cached


class _FakeUow:
    async def __aenter__(self) -> "_FakeUow":
        return self

    async def __aexit__(self, *args: Any) -> None: ...

    async def commit(self) -> None: ...


class _FakeCompute:
    def __init__(self) -> None:
        self.calls: list[ComputeUmapClusterInput] = []

    async def execute(self, payload: ComputeUmapClusterInput) -> UmapResult:
        self.calls.append(payload)
        return UmapResult(
            points=[],
            clusters=[],
            representatives=[],
            cluster_count=0,
            picker=payload.picker,
            picker_params=payload.picker_params,
        )


class _FakeOrchestrator:
    def __init__(self) -> None:
        self.scheduled: list[dict[str, Any]] = []

    async def schedule(self, **kwargs: Any) -> None:
        self.scheduled.append(kwargs)

    async def cancel(self, *, job_id: UUID) -> None: ...


@pytest.mark.asyncio
async def test_cache_hit_returns_result_no_compute() -> None:
    repo = _FakeRepo()
    repo.cached = UmapJob.create(
        workspace_id=uuid4(),
        requested_by=uuid4(),
        ids_hash="h",
        picker="maxmin",
        picker_params={"n": 50},
        picker_param_hash="ph",
        now=datetime.now(timezone.utc),
    ).mark_running(datetime.now(timezone.utc)).mark_ready(
        UmapResult([], [], [], 0, "maxmin", {"n": 50}),
        datetime.now(timezone.utc),
    )
    compute = _FakeCompute()
    use_case = StartUmapClusterJob(
        compute=compute,
        repository=repo,
        orchestrator=_FakeOrchestrator(),
        uow=_FakeUow(),
        sync_limit=500,
    )
    out = await use_case.execute(
        StartUmapClusterJobInput(
            molecule_ids=[uuid4() for _ in range(10)],
            picker="maxmin",
            picker_params={"n": 50},
            workspace_id=uuid4(),
            requested_by=uuid4(),
            now=datetime.now(timezone.utc),
        )
    )
    assert out.result is not None
    assert out.job is None
    assert compute.calls == []


@pytest.mark.asyncio
async def test_sync_path_computes_and_persists_ready() -> None:
    repo = _FakeRepo()
    compute = _FakeCompute()
    use_case = StartUmapClusterJob(
        compute=compute,
        repository=repo,
        orchestrator=_FakeOrchestrator(),
        uow=_FakeUow(),
        sync_limit=500,
    )
    out = await use_case.execute(
        StartUmapClusterJobInput(
            molecule_ids=[uuid4() for _ in range(50)],
            picker="maxmin",
            picker_params={"n": 10},
            workspace_id=uuid4(),
            requested_by=uuid4(),
            now=datetime.now(timezone.utc),
        )
    )
    assert out.result is not None
    assert out.job is None
    assert len(compute.calls) == 1
    # Persisted as READY for future cache hit.
    assert len(repo.saved) == 1
    assert repo.saved[0].status == UmapJobStatus.READY


@pytest.mark.asyncio
async def test_async_path_schedules_when_above_limit() -> None:
    repo = _FakeRepo()
    orch = _FakeOrchestrator()
    use_case = StartUmapClusterJob(
        compute=_FakeCompute(),
        repository=repo,
        orchestrator=orch,
        uow=_FakeUow(),
        sync_limit=500,
    )
    out = await use_case.execute(
        StartUmapClusterJobInput(
            molecule_ids=[uuid4() for _ in range(800)],
            picker="butina",
            picker_params={"threshold": 0.4},
            workspace_id=uuid4(),
            requested_by=uuid4(),
            now=datetime.now(timezone.utc),
        )
    )
    assert out.result is None
    assert out.job is not None
    assert out.job.status == UmapJobStatus.PENDING
    assert len(orch.scheduled) == 1
    assert orch.scheduled[0]["picker"] == "butina"
```

- [ ] **Step 2: Run + fail**

- [ ] **Step 3: Implement**

```python
"""StartUmapClusterJob — 3-path dispatch (cache / sync / async)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from cellar.application.sar_analysis.compute_umap_cluster import (
    ComputeUmapCluster,
    ComputeUmapClusterInput,
    compute_ids_hash,
    compute_picker_param_hash,
)
from cellar.application.sar_analysis.repositories import UmapJobRepository
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.umap_job import UmapJob
from cellar.domain.sar_analysis.umap_types import UmapResult


@dataclass(frozen=True)
class StartUmapClusterJobInput:
    molecule_ids: list[UUID]
    picker: str
    picker_params: dict[str, Any]
    workspace_id: UUID
    requested_by: UUID
    now: datetime


@dataclass(frozen=True)
class StartUmapClusterJobOutput:
    result: UmapResult | None
    job: UmapJob | None


class UmapClusterOrchestrator(Protocol):
    async def schedule(
        self,
        *,
        job_id: UUID,
        workspace_id: UUID,
        molecule_ids: list[UUID],
        picker: str,
        picker_params: dict[str, Any],
    ) -> None: ...

    async def cancel(self, *, job_id: UUID) -> None: ...


class StartUmapClusterJob:
    def __init__(
        self,
        *,
        compute: ComputeUmapCluster,
        repository: UmapJobRepository,
        orchestrator: UmapClusterOrchestrator,
        uow: UnitOfWork,
        sync_limit: int = 500,
    ) -> None:
        self._compute = compute
        self._repo = repository
        self._orchestrator = orchestrator
        self._uow = uow
        self._sync_limit = sync_limit

    async def execute(
        self, payload: StartUmapClusterJobInput
    ) -> StartUmapClusterJobOutput:
        ids_hash = compute_ids_hash(payload.molecule_ids)
        pp_hash = compute_picker_param_hash(payload.picker, payload.picker_params)

        async with self._uow:
            cached = await self._repo.find_cached(
                ids_hash=ids_hash,
                picker=payload.picker,
                picker_param_hash=pp_hash,
                ttl_seconds=3600,
            )
        if cached is not None and cached.result is not None:
            return StartUmapClusterJobOutput(result=cached.result, job=None)

        if len(payload.molecule_ids) <= self._sync_limit:
            result = await self._compute.execute(
                ComputeUmapClusterInput(
                    molecule_ids=payload.molecule_ids,
                    picker=payload.picker,
                    picker_params=payload.picker_params,
                )
            )
            job = (
                UmapJob.create(
                    workspace_id=payload.workspace_id,
                    requested_by=payload.requested_by,
                    ids_hash=ids_hash,
                    picker=payload.picker,
                    picker_params=payload.picker_params,
                    picker_param_hash=pp_hash,
                    now=payload.now,
                )
                .mark_running(payload.now)
                .mark_ready(result, payload.now)
            )
            async with self._uow:
                await self._repo.save(job)
                await self._uow.commit()
            return StartUmapClusterJobOutput(result=result, job=None)

        # Async path.
        job = UmapJob.create(
            workspace_id=payload.workspace_id,
            requested_by=payload.requested_by,
            ids_hash=ids_hash,
            picker=payload.picker,
            picker_params=payload.picker_params,
            picker_param_hash=pp_hash,
            now=payload.now,
        )
        async with self._uow:
            await self._repo.save(job)
            await self._uow.commit()
        await self._orchestrator.schedule(
            job_id=job.id,
            workspace_id=payload.workspace_id,
            molecule_ids=list(payload.molecule_ids),
            picker=payload.picker,
            picker_params=payload.picker_params,
        )
        return StartUmapClusterJobOutput(result=None, job=job)
```

- [ ] **Step 4: Run + pass**

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/application/sar_analysis/start_umap_cluster_job.py backend/tests/unit/application/sar_analysis/test_start_umap_cluster_job.py
git commit -m "feat(sar): StartUmapClusterJob — cache/sync/async dispatch"
```

---

## Task 11: `UmapClusterWorkflow` + activity + orchestrator

**Files:**
- Create: `backend/src/cellar/infrastructure/temporal/workflows/umap_cluster.py`
- Create: `backend/src/cellar/infrastructure/temporal/activities/umap_cluster.py`
- Create: `backend/src/cellar/infrastructure/temporal/orchestrators/umap_cluster.py`
- Test: `backend/tests/unit/infrastructure/temporal/test_umap_cluster_orchestrator.py`

Mirror `scaffold_tree.py` in each of these three folders. The only structural difference: workflow input + activity input carry `picker` + `picker_params`. Show full workflow:

- [ ] **Step 1: Write the failing test** (null-orchestrator inline-runs the workflow under `TEMPORAL_DISABLED=1`):

```python
"""NullUmapClusterOrchestrator runs the workflow inline."""

from __future__ import annotations

from uuid import uuid4

import pytest

from cellar.infrastructure.temporal.orchestrators.umap_cluster import (
    NullUmapClusterOrchestrator,
)


@pytest.mark.asyncio
async def test_null_orchestrator_calls_runner_inline(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_runner(**kwargs):
        calls.append(kwargs)

    orch = NullUmapClusterOrchestrator(runner=fake_runner)
    await orch.schedule(
        job_id=uuid4(),
        workspace_id=uuid4(),
        molecule_ids=[uuid4()],
        picker="maxmin",
        picker_params={"n": 5},
    )
    assert len(calls) == 1
    assert calls[0]["picker"] == "maxmin"
```

- [ ] **Step 2: Run + fail**

- [ ] **Step 3: Implement workflow** (mirror scaffold-tree):

```python
"""Temporal workflow for UMAP cluster computation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from cellar.infrastructure.temporal.activities.umap_cluster import (
        RunUmapClusterActivityInput,
        run_umap_cluster_activity,
    )


@dataclass
class UmapClusterWorkflowInput:
    job_id: UUID
    workspace_id: UUID
    molecule_ids: list[UUID]
    picker: str
    picker_params: dict[str, Any]


@workflow.defn(name="UmapClusterWorkflow")
class UmapClusterWorkflow:
    @workflow.run
    async def run(self, payload: UmapClusterWorkflowInput) -> None:
        await workflow.execute_activity(
            run_umap_cluster_activity,
            RunUmapClusterActivityInput(
                job_id=payload.job_id,
                workspace_id=payload.workspace_id,
                molecule_ids=payload.molecule_ids,
                picker=payload.picker,
                picker_params=payload.picker_params,
            ),
            start_to_close_timeout=timedelta(minutes=30),
        )
```

- [ ] **Step 4: Implement activity**

```python
"""Temporal activity wrapping the in-process run_umap_cluster runner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from temporalio import activity


@dataclass
class RunUmapClusterActivityInput:
    job_id: UUID
    workspace_id: UUID
    molecule_ids: list[UUID]
    picker: str
    picker_params: dict[str, Any]


@activity.defn(name="run_umap_cluster_activity")
async def run_umap_cluster_activity(payload: RunUmapClusterActivityInput) -> None:
    # Lazy import — keeps Temporal worker startup independent from app DI bootstrap.
    from cellar.infrastructure.di import get_container

    container = get_container()
    from cellar.application.sar_analysis.run_umap_cluster import RunUmapCluster

    runner = container.resolve(RunUmapCluster)
    await runner.execute(
        job_id=payload.job_id,
        workspace_id=payload.workspace_id,
        molecule_ids=payload.molecule_ids,
        picker=payload.picker,
        picker_params=payload.picker_params,
    )
```

- [ ] **Step 5: Implement orchestrator (both Null + Temporal)**

```python
"""UmapClusterOrchestrator implementations.

NullUmapClusterOrchestrator is used under TEMPORAL_DISABLED=1 (tests + local without worker).
TemporalUmapClusterOrchestrator hands off to the Temporal worker.
"""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable
from uuid import UUID

from temporalio.client import Client

from cellar.infrastructure.temporal.workflows.umap_cluster import (
    UmapClusterWorkflow,
    UmapClusterWorkflowInput,
)

RunnerFn = Callable[..., Awaitable[None]]


class NullUmapClusterOrchestrator:
    """Runs the runner inline (no Temporal). For tests + TEMPORAL_DISABLED=1."""

    def __init__(self, *, runner: RunnerFn) -> None:
        self._runner = runner

    async def schedule(
        self,
        *,
        job_id: UUID,
        workspace_id: UUID,
        molecule_ids: list[UUID],
        picker: str,
        picker_params: dict[str, Any],
    ) -> None:
        await self._runner(
            job_id=job_id,
            workspace_id=workspace_id,
            molecule_ids=molecule_ids,
            picker=picker,
            picker_params=picker_params,
        )

    async def cancel(self, *, job_id: UUID) -> None:  # pragma: no cover
        # Cancellation is best-effort; the runner has no signal channel in the inline path.
        return


class TemporalUmapClusterOrchestrator:
    def __init__(self, *, client: Client, task_queue: str) -> None:
        self._client = client
        self._task_queue = task_queue

    async def schedule(
        self,
        *,
        job_id: UUID,
        workspace_id: UUID,
        molecule_ids: list[UUID],
        picker: str,
        picker_params: dict[str, Any],
    ) -> None:
        await self._client.start_workflow(
            UmapClusterWorkflow.run,
            UmapClusterWorkflowInput(
                job_id=job_id,
                workspace_id=workspace_id,
                molecule_ids=molecule_ids,
                picker=picker,
                picker_params=picker_params,
            ),
            id=f"umap-cluster-{job_id}",
            task_queue=self._task_queue,
        )

    async def cancel(self, *, job_id: UUID) -> None:
        handle = self._client.get_workflow_handle(f"umap-cluster-{job_id}")
        await handle.cancel()
```

- [ ] **Step 6: Create `RunUmapCluster` use case**

```python
# backend/src/cellar/application/sar_analysis/run_umap_cluster.py
"""RunUmapCluster — Temporal-activity-side: load job, mark running, compute, mark ready/failed."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from cellar.application.sar_analysis.compute_umap_cluster import (
    ComputeUmapCluster,
    ComputeUmapClusterInput,
)
from cellar.application.sar_analysis.repositories import UmapJobRepository
from cellar.application.shared.unit_of_work import UnitOfWork


class RunUmapCluster:
    def __init__(
        self,
        *,
        compute: ComputeUmapCluster,
        repository: UmapJobRepository,
        uow: UnitOfWork,
    ) -> None:
        self._compute = compute
        self._repo = repository
        self._uow = uow

    async def execute(
        self,
        *,
        job_id: UUID,
        workspace_id: UUID,
        molecule_ids: list[UUID],
        picker: str,
        picker_params: dict[str, Any],
    ) -> None:
        async with self._uow:
            job = await self._repo.find_by_id(job_id)
            if job is None:
                return
            job = job.mark_running(datetime.now(timezone.utc))
            await self._repo.save(job)
            await self._uow.commit()

        try:
            result = await self._compute.execute(
                ComputeUmapClusterInput(
                    molecule_ids=molecule_ids,
                    picker=picker,
                    picker_params=picker_params,
                )
            )
        except Exception as exc:  # noqa: BLE001
            async with self._uow:
                job = await self._repo.find_by_id(job_id)
                if job:
                    await self._repo.save(job.mark_failed(str(exc), datetime.now(timezone.utc)))
                    await self._uow.commit()
            raise

        async with self._uow:
            job = await self._repo.find_by_id(job_id)
            if job:
                await self._repo.save(job.mark_ready(result, datetime.now(timezone.utc)))
                await self._uow.commit()
```

- [ ] **Step 7: Run all the new tests + pass**

```bash
uv run pytest tests/unit/infrastructure/temporal/test_umap_cluster_orchestrator.py -v
```

- [ ] **Step 8: Register the workflow + activity with the worker**

Edit `backend/src/cellar/infrastructure/temporal/worker.py` (or wherever the worker registers `ScaffoldTreeWorkflow`): add `UmapClusterWorkflow` to the `workflows=[...]` list and `run_umap_cluster_activity` to the `activities=[...]` list.

- [ ] **Step 9: Commit**

```bash
git add backend/src/cellar/infrastructure/temporal/workflows/umap_cluster.py \
        backend/src/cellar/infrastructure/temporal/activities/umap_cluster.py \
        backend/src/cellar/infrastructure/temporal/orchestrators/umap_cluster.py \
        backend/src/cellar/application/sar_analysis/run_umap_cluster.py \
        backend/src/cellar/infrastructure/temporal/worker.py \
        backend/tests/unit/infrastructure/temporal/test_umap_cluster_orchestrator.py
git commit -m "feat(temporal): UmapClusterWorkflow + activity + Null/Temporal orchestrators"
```

---

## Task 12: `GetUmapClusterJob` + `CancelUmapClusterJob`

**Files:**
- Create: `backend/src/cellar/application/sar_analysis/get_umap_cluster_job.py`
- Create: `backend/src/cellar/application/sar_analysis/cancel_umap_cluster_job.py`
- Test: `backend/tests/unit/application/sar_analysis/test_get_umap_cluster_job.py`
- Test: `backend/tests/unit/application/sar_analysis/test_cancel_umap_cluster_job.py`

Mirror `get_scaffold_tree_job.py` + `cancel_scaffold_tree_job.py` line-for-line. The only difference is the repo type. Cancel is idempotent on terminal states (returns the existing job).

(Show test stubs + tiny implementations:)

- [ ] **Step 1: GetUmapClusterJob test**

```python
import pytest
from uuid import uuid4

from cellar.application.sar_analysis.get_umap_cluster_job import GetUmapClusterJob


class _Repo:
    def __init__(self, job=None):
        self.job = job
    async def find_by_id(self, _id):
        return self.job


@pytest.mark.asyncio
async def test_returns_none_when_missing():
    out = await GetUmapClusterJob(_Repo()).execute(uuid4())
    assert out is None
```

- [ ] **Step 2: Implement**

```python
# get_umap_cluster_job.py
from uuid import UUID
from cellar.application.sar_analysis.repositories import UmapJobRepository
from cellar.domain.sar_analysis.umap_job import UmapJob

class GetUmapClusterJob:
    def __init__(self, repository: UmapJobRepository):
        self._repo = repository
    async def execute(self, job_id: UUID) -> UmapJob | None:
        return await self._repo.find_by_id(job_id)
```

- [ ] **Step 3: CancelUmapClusterJob test**

```python
import pytest
from datetime import datetime, timezone
from uuid import uuid4

from cellar.application.sar_analysis.cancel_umap_cluster_job import CancelUmapClusterJob
from cellar.domain.sar_analysis.umap_job import UmapJob, UmapJobStatus


class _Repo:
    def __init__(self, job): self.job = job; self.saved = []
    async def find_by_id(self, _): return self.job
    async def save(self, j): self.saved.append(j)


class _Uow:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass
    async def commit(self): pass


class _Orch:
    def __init__(self): self.cancelled = []
    async def cancel(self, *, job_id): self.cancelled.append(job_id)


@pytest.mark.asyncio
async def test_cancels_pending_job():
    job = UmapJob.create(
        workspace_id=uuid4(), requested_by=uuid4(), ids_hash="h",
        picker="maxmin", picker_params={"n": 50}, picker_param_hash="ph",
        now=datetime.now(timezone.utc),
    )
    repo = _Repo(job); orch = _Orch()
    await CancelUmapClusterJob(repository=repo, uow=_Uow(), orchestrator=orch).execute(job.id)
    assert repo.saved[0].status == UmapJobStatus.CANCELLED
    assert orch.cancelled == [job.id]
```

- [ ] **Step 4: Implement**

```python
# cancel_umap_cluster_job.py
from datetime import datetime, timezone
from uuid import UUID

from cellar.application.sar_analysis.repositories import UmapJobRepository
from cellar.application.sar_analysis.start_umap_cluster_job import UmapClusterOrchestrator
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.umap_job import InvalidUmapJobTransition


class CancelUmapClusterJob:
    def __init__(
        self,
        *,
        repository: UmapJobRepository,
        uow: UnitOfWork,
        orchestrator: UmapClusterOrchestrator,
    ) -> None:
        self._repo = repository
        self._uow = uow
        self._orchestrator = orchestrator

    async def execute(self, job_id: UUID) -> None:
        async with self._uow:
            job = await self._repo.find_by_id(job_id)
            if job is None:
                return
            try:
                await self._repo.save(job.mark_cancelled(datetime.now(timezone.utc)))
                await self._uow.commit()
            except InvalidUmapJobTransition:
                # Already terminal — idempotent no-op.
                return
        await self._orchestrator.cancel(job_id=job_id)
```

- [ ] **Step 5: Run + pass**

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/application/sar_analysis/get_umap_cluster_job.py \
        backend/src/cellar/application/sar_analysis/cancel_umap_cluster_job.py \
        backend/tests/unit/application/sar_analysis/test_get_umap_cluster_job.py \
        backend/tests/unit/application/sar_analysis/test_cancel_umap_cluster_job.py
git commit -m "feat(sar): GetUmapClusterJob + CancelUmapClusterJob"
```

---

## Task 13: DI wiring

**Files:**
- Modify: `backend/src/cellar/infrastructure/di/_sar_analysis.py` (extend, append; don't break scaffold-tree wiring)
- Modify: `backend/src/cellar/app.py` (lifespan-time binding of `UmapClusterOrchestrator`, parallel to `ScaffoldTreeOrchestrator`)

Mirror the existing scaffold-tree wiring patterns. Need a `MorganFingerprintLoader` that reads `Molecule.fingerprints` from the molecule repo (Morgan FP is already stored — see V2 Task 5 prerequisite). It returns a `dict[UUID, ExplicitBitVect]` for `FingerprintLoader.load_morgan`. Implement that adapter under `infrastructure/sar_analysis/morgan_fingerprint_loader.py` (or wherever the existing molecule-fingerprint reader pattern lives — check `application/screening/molecule_activity_service.py` for the canonical FP reader).

- [ ] **Step 1: Add the FP loader adapter**

```python
# backend/src/cellar/infrastructure/sar_analysis/morgan_fingerprint_loader.py
"""Adapts MoleculeRepository to FingerprintLoader Protocol used by ComputeUmapCluster."""

from __future__ import annotations

from typing import Iterable
from uuid import UUID

from rdkit import DataStructs
from rdkit.DataStructs import ExplicitBitVect

from cellar.application.chemical_registration.repositories import MoleculeRepository


class MorganFingerprintLoader:
    def __init__(self, *, repository: MoleculeRepository) -> None:
        self._repo = repository

    async def load_morgan(self, ids: Iterable[UUID]) -> dict[UUID, ExplicitBitVect]:
        loaded = await self._repo.find_many_by_id(list(ids))
        out: dict[UUID, ExplicitBitVect] = {}
        for mol in loaded:
            fp_bytes = mol.fingerprints.get("morgan") if mol.fingerprints else None
            if not fp_bytes:
                continue
            bv = ExplicitBitVect(2048)
            DataStructs.CreateFromBinaryText(bv, fp_bytes)
            out[mol.id] = bv
        return out
```

Note: confirm `Molecule.fingerprints["morgan"]` is the persisted shape; if your codebase stores it as `morgan_fp` bytes column directly on the model, adapt accordingly (check `infrastructure/persistence/sqlalchemy/chemical_registration/molecule_model.py`).

- [ ] **Step 2: Extend `_sar_analysis.py` with the new bindings**

Append (don't disturb existing scaffold-tree bindings):

```python
# Inside register_sar_analysis(container, ...):

from cellar.application.sar_analysis.compute_umap_cluster import ComputeUmapCluster
from cellar.application.sar_analysis.start_umap_cluster_job import StartUmapClusterJob
from cellar.application.sar_analysis.get_umap_cluster_job import GetUmapClusterJob
from cellar.application.sar_analysis.cancel_umap_cluster_job import CancelUmapClusterJob
from cellar.application.sar_analysis.run_umap_cluster import RunUmapCluster
from cellar.application.sar_analysis.repositories import UmapJobRepository
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.umap_job_repository import (
    SQLAlchemyUmapJobRepository,
)
from cellar.infrastructure.rdkit.umap_embedder import UmapEmbedder
from cellar.infrastructure.rdkit.butina_clusterer import ButinaClusterer
from cellar.infrastructure.rdkit.maxmin_picker import MaxMinPickerAdapter
from cellar.infrastructure.sar_analysis.morgan_fingerprint_loader import (
    MorganFingerprintLoader,
)

container[UmapJobRepository] = lambda c: SQLAlchemyUmapJobRepository(c[AsyncSession])
container[MorganFingerprintLoader] = lambda c: MorganFingerprintLoader(
    repository=c[MoleculeRepository]
)
container[UmapEmbedder] = lambda c: UmapEmbedder()
container[ButinaClusterer] = lambda c: ButinaClusterer(threshold=0.4)
container[MaxMinPickerAdapter] = lambda c: MaxMinPickerAdapter()

container[ComputeUmapCluster] = lambda c: ComputeUmapCluster(
    fingerprint_loader=c[MorganFingerprintLoader],
    embedder=c[UmapEmbedder],
    clusterer=c[ButinaClusterer],
    maxmin_picker=c[MaxMinPickerAdapter],
)
container[RunUmapCluster] = lambda c: RunUmapCluster(
    compute=c[ComputeUmapCluster],
    repository=c[UmapJobRepository],
    uow=c[UnitOfWork],
)
container[StartUmapClusterJob] = lambda c: StartUmapClusterJob(
    compute=c[ComputeUmapCluster],
    repository=c[UmapJobRepository],
    orchestrator=c[UmapClusterOrchestrator],
    uow=c[UnitOfWork],
)
container[GetUmapClusterJob] = lambda c: GetUmapClusterJob(c[UmapJobRepository])
container[CancelUmapClusterJob] = lambda c: CancelUmapClusterJob(
    repository=c[UmapJobRepository],
    uow=c[UnitOfWork],
    orchestrator=c[UmapClusterOrchestrator],
)
```

- [ ] **Step 3: Extend `app.py` lifespan to bind the orchestrator**

Inside the existing `lifespan` startup block (next to where `ScaffoldTreeOrchestrator` is bound — see the V2 plan Task 17 + the live `app.py` for the exact location):

```python
from cellar.infrastructure.temporal.orchestrators.umap_cluster import (
    NullUmapClusterOrchestrator,
    TemporalUmapClusterOrchestrator,
)
from cellar.application.sar_analysis.start_umap_cluster_job import UmapClusterOrchestrator
from cellar.application.sar_analysis.run_umap_cluster import RunUmapCluster

if os.getenv("TEMPORAL_DISABLED") == "1":
    container[UmapClusterOrchestrator] = lambda c: NullUmapClusterOrchestrator(
        runner=lambda **kw: c[RunUmapCluster].execute(**kw),
    )
else:
    container[UmapClusterOrchestrator] = lambda c: TemporalUmapClusterOrchestrator(
        client=temporal_client,
        task_queue=settings.temporal_task_queue,
    )
```

- [ ] **Step 4: Run the full sar_analysis test suite**

```bash
uv run pytest tests/unit/application/sar_analysis tests/unit/domain/sar_analysis -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/sar_analysis/morgan_fingerprint_loader.py \
        backend/src/cellar/infrastructure/di/_sar_analysis.py \
        backend/src/cellar/app.py
git commit -m "feat(di): wire UMAP cluster use cases + orchestrator (Null/Temporal)"
```

---

## Task 14: API routes

**Files:**
- Create: `backend/src/cellar/interface/routes/umap_cluster.py`
- Modify: `backend/src/cellar/interface/routes/__init__.py` (register the new router)
- Test: `backend/tests/api/sar_analysis/test_umap_cluster.py`

- [ ] **Step 1: Write the failing API tests**

```python
"""POST /api/v1/sar/umap-cluster — sync, async, validation, cache."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_returns_inline_result_for_small_set(
    client: AsyncClient, seed_molecules
) -> None:
    mol_ids = await seed_molecules(count=20)  # fixture creates 20 mols with Morgan FPs
    resp = await client.post(
        "/api/v1/sar/umap-cluster",
        json={
            "molecule_ids": [str(m) for m in mol_ids],
            "picker": "maxmin",
            "n": 5,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["job"] is None
    assert body["result"] is not None
    assert len(body["result"]["points"]) == 20
    assert len(body["result"]["representatives"]) == 5


@pytest.mark.asyncio
async def test_rejects_below_minimum_size(client, seed_molecules):
    mol_ids = await seed_molecules(count=5)
    resp = await client.post(
        "/api/v1/sar/umap-cluster",
        json={"molecule_ids": [str(m) for m in mol_ids], "picker": "maxmin", "n": 2},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_rejects_above_max_size(client):
    # Use synthetic uuids; size-check fires before any DB read.
    from uuid import uuid4
    mol_ids = [str(uuid4()) for _ in range(50001)]
    resp = await client.post(
        "/api/v1/sar/umap-cluster",
        json={"molecule_ids": mol_ids, "picker": "maxmin", "n": 50},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_requires_n_when_maxmin(client, seed_molecules):
    mol_ids = await seed_molecules(count=20)
    resp = await client.post(
        "/api/v1/sar/umap-cluster",
        json={"molecule_ids": [str(m) for m in mol_ids], "picker": "maxmin"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_returns_404_for_missing_job(client):
    from uuid import uuid4
    resp = await client.get(f"/api/v1/sar/umap-cluster/jobs/{uuid4()}")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run + fail**

- [ ] **Step 3: Implement the route**

```python
"""Routes for V3 UMAP cluster map."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from cellar.application.sar_analysis.cancel_umap_cluster_job import CancelUmapClusterJob
from cellar.application.sar_analysis.get_umap_cluster_job import GetUmapClusterJob
from cellar.application.sar_analysis.start_umap_cluster_job import (
    StartUmapClusterJob,
    StartUmapClusterJobInput,
)
from cellar.application.research_organization.repositories import CollectionRepository
from cellar.domain.sar_analysis.umap_job import UmapJob, UmapJobStatus
from cellar.domain.sar_analysis.umap_types import UmapResult
from cellar.interface.dependencies import (
    Container,
    Principal,
    get_container,
    get_principal,
)

router = APIRouter(prefix="/api/v1/sar", tags=["sar"])

MIN_SET_SIZE = 10
MAX_SET_SIZE = 50_000


class StartUmapClusterBody(BaseModel):
    collection_id: UUID | None = None
    molecule_ids: list[UUID] | None = None
    picker: str = Field(..., pattern="^(maxmin|butina)$")
    n: int | None = Field(None, ge=1, le=10_000)
    threshold: float | None = Field(None, ge=0.05, le=0.95)

    @model_validator(mode="after")
    def _check_exactly_one_source(self) -> "StartUmapClusterBody":
        if bool(self.collection_id) == bool(self.molecule_ids):
            raise ValueError("Provide exactly one of collection_id or molecule_ids.")
        return self

    @model_validator(mode="after")
    def _check_picker_params(self) -> "StartUmapClusterBody":
        if self.picker == "maxmin" and self.n is None:
            raise ValueError("n is required when picker=maxmin.")
        if self.picker == "butina" and self.threshold is None:
            raise ValueError("threshold is required when picker=butina.")
        return self


class UmapPointDto(BaseModel):
    molecule_id: UUID
    x: float
    y: float


class ClusterAssignmentDto(BaseModel):
    molecule_id: UUID
    cluster_id: int


class RepresentativeDto(BaseModel):
    molecule_id: UUID
    cluster_id: int


class UmapResultDto(BaseModel):
    points: list[UmapPointDto]
    clusters: list[ClusterAssignmentDto]
    representatives: list[RepresentativeDto]
    cluster_count: int
    picker: str
    picker_params: dict
    skipped_molecule_ids: list[UUID]


class UmapJobDto(BaseModel):
    id: UUID
    status: UmapJobStatus
    picker: str
    picker_params: dict
    error_message: str | None = None


class StartUmapClusterResponse(BaseModel):
    result: UmapResultDto | None
    job: UmapJobDto | None


def _result_to_dto(r: UmapResult) -> UmapResultDto:
    return UmapResultDto(
        points=[UmapPointDto(molecule_id=p.molecule_id, x=p.x, y=p.y) for p in r.points],
        clusters=[ClusterAssignmentDto(**c.__dict__) for c in r.clusters],
        representatives=[RepresentativeDto(**rp.__dict__) for rp in r.representatives],
        cluster_count=r.cluster_count,
        picker=r.picker,
        picker_params=r.picker_params,
        skipped_molecule_ids=r.skipped_molecule_ids,
    )


def _job_to_dto(j: UmapJob) -> UmapJobDto:
    return UmapJobDto(
        id=j.id,
        status=j.status,
        picker=j.picker,
        picker_params=j.picker_params,
        error_message=j.error_message,
    )


async def _resolve_molecule_ids(
    body: StartUmapClusterBody,
    collections: CollectionRepository,
    workspace_id: UUID,
) -> list[UUID]:
    if body.molecule_ids:
        return list(dict.fromkeys(body.molecule_ids))  # dedupe preserving order
    members = await collections.list_member_ids(body.collection_id, workspace_id=workspace_id)
    return list(members)


@router.post("/umap-cluster", response_model=StartUmapClusterResponse)
async def start_umap_cluster(
    body: StartUmapClusterBody,
    container: Annotated[Container, Depends(get_container)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> StartUmapClusterResponse:
    mol_ids = await _resolve_molecule_ids(
        body,
        container.resolve(CollectionRepository),
        principal.workspace_id,
    )
    if len(mol_ids) < MIN_SET_SIZE:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Need at least {MIN_SET_SIZE} molecules for UMAP.",
        )
    if len(mol_ids) > MAX_SET_SIZE:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Cluster map capped at {MAX_SET_SIZE} molecules; refine the filter.",
        )

    picker_params: dict = (
        {"n": body.n} if body.picker == "maxmin" else {"threshold": body.threshold}
    )
    use_case = container.resolve(StartUmapClusterJob)
    out = await use_case.execute(
        StartUmapClusterJobInput(
            molecule_ids=mol_ids,
            picker=body.picker,
            picker_params=picker_params,
            workspace_id=principal.workspace_id,
            requested_by=principal.user_id,
            now=datetime.now(timezone.utc),
        )
    )
    return StartUmapClusterResponse(
        result=_result_to_dto(out.result) if out.result else None,
        job=_job_to_dto(out.job) if out.job else None,
    )


@router.get("/umap-cluster/jobs/{job_id}", response_model=StartUmapClusterResponse)
async def get_umap_cluster_job(
    job_id: UUID,
    container: Annotated[Container, Depends(get_container)],
) -> StartUmapClusterResponse:
    use_case = container.resolve(GetUmapClusterJob)
    job = await use_case.execute(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found.")
    return StartUmapClusterResponse(
        result=_result_to_dto(job.result) if job.result else None,
        job=_job_to_dto(job),
    )


@router.post("/umap-cluster/jobs/{job_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_umap_cluster_job(
    job_id: UUID,
    container: Annotated[Container, Depends(get_container)],
) -> None:
    await container.resolve(CancelUmapClusterJob).execute(job_id)
```

- [ ] **Step 4: Register router**

Edit `backend/src/cellar/interface/routes/__init__.py` (or wherever routers are aggregated — check the scaffold_tree route registration as the precedent):

```python
from cellar.interface.routes.umap_cluster import router as umap_cluster_router
# ...
app.include_router(umap_cluster_router)
```

- [ ] **Step 5: Run + pass**

```bash
TEMPORAL_DISABLED=1 uv run pytest tests/api/sar_analysis/test_umap_cluster.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/interface/routes/umap_cluster.py \
        backend/src/cellar/interface/routes/__init__.py \
        backend/tests/api/sar_analysis/test_umap_cluster.py
git commit -m "feat(api): /api/v1/sar/umap-cluster endpoints (start, poll, cancel)"
```

---

## Task 15: Regenerate orval FE client

**Files:**
- Modify: `frontend/src/shared/api/` (regenerated)

- [ ] **Step 1: Regenerate**

```bash
cd /Users/sidx/workspace/chem-vault2/frontend
pnpm orval
```

- [ ] **Step 2: Verify diff**

Confirm the new generated code includes hooks/types for the three new endpoints. Expected new exports (orval names depend on the project's config; check pattern from scaffold-tree's regen commit `7a1f7ac7`):
- `useStartUmapCluster`
- `useGetUmapClusterJob`
- `useCancelUmapClusterJob`
- Types: `StartUmapClusterBody`, `StartUmapClusterResponse`, `UmapResultDto`, `UmapJobDto`, etc.

- [ ] **Step 3: Type-check**

```bash
pnpm exec tsc --noEmit
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/shared/api
git commit -m "chore(api): regenerate orval client for /sar/umap-cluster endpoints"
```

---

## Task 16: FE wire types

**Files:**
- Modify: `frontend/src/features/sar-analysis/types/index.ts`

- [ ] **Step 1: Append the V3 types**

```ts
// frontend/src/features/sar-analysis/types/index.ts (append; don't replace V2 exports)

import type { UmapResultDto, UmapJobDto } from "@/shared/api";

export type UmapPicker = "maxmin" | "butina";

export interface UmapPoint {
  moleculeId: string;
  x: number;
  y: number;
}

export interface ClusterAssignment {
  moleculeId: string;
  clusterId: number;
}

export interface RepresentativePick {
  moleculeId: string;
  clusterId: number;
}

export interface UmapResult {
  points: UmapPoint[];
  clusters: ClusterAssignment[];
  representatives: RepresentativePick[];
  clusterCount: number;
  picker: UmapPicker;
  pickerParams: Record<string, unknown>;
  skippedMoleculeIds: string[];
}

export interface UmapJob {
  id: string;
  status: "pending" | "running" | "ready" | "failed" | "cancelled";
  picker: UmapPicker;
  pickerParams: Record<string, unknown>;
  errorMessage?: string | null;
}

export type ColorMode = "cluster" | "activity" | "scaffold" | "none";

export function dtoToUmapResult(dto: UmapResultDto): UmapResult {
  return {
    points: dto.points.map((p) => ({ moleculeId: p.molecule_id, x: p.x, y: p.y })),
    clusters: dto.clusters.map((c) => ({
      moleculeId: c.molecule_id,
      clusterId: c.cluster_id,
    })),
    representatives: dto.representatives.map((r) => ({
      moleculeId: r.molecule_id,
      clusterId: r.cluster_id,
    })),
    clusterCount: dto.cluster_count,
    picker: dto.picker as UmapPicker,
    pickerParams: dto.picker_params,
    skippedMoleculeIds: dto.skipped_molecule_ids,
  };
}

export function dtoToUmapJob(dto: UmapJobDto): UmapJob {
  return {
    id: dto.id,
    status: dto.status,
    picker: dto.picker as UmapPicker,
    pickerParams: dto.picker_params,
    errorMessage: dto.error_message ?? null,
  };
}
```

- [ ] **Step 2: Type-check + commit**

```bash
pnpm exec tsc --noEmit
git add frontend/src/features/sar-analysis/types/index.ts
git commit -m "feat(sar): FE wire types for UMAP cluster result + job"
```

---

## Task 17: `lasso-math.ts`

**Files:**
- Create: `frontend/src/features/sar-analysis/lib/lasso-math.ts`
- Test: `frontend/src/features/sar-analysis/lib/lasso-math.test.ts`

- [ ] **Step 1: Failing test**

```ts
import { describe, expect, it } from "vitest";
import { pointInPolygon, idsInsidePolygon } from "./lasso-math";

const SQUARE = [
  { x: 0, y: 0 },
  { x: 0, y: 10 },
  { x: 10, y: 10 },
  { x: 10, y: 0 },
];

describe("pointInPolygon", () => {
  it("returns true for clearly inside", () => {
    expect(pointInPolygon({ x: 5, y: 5 }, SQUARE)).toBe(true);
  });

  it("returns false for clearly outside", () => {
    expect(pointInPolygon({ x: 50, y: 50 }, SQUARE)).toBe(false);
  });

  it("handles concave polygon", () => {
    const C = [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 10 },
      { x: 5, y: 5 },
      { x: 0, y: 10 },
    ];
    expect(pointInPolygon({ x: 5, y: 8 }, C)).toBe(false);
    expect(pointInPolygon({ x: 2, y: 2 }, C)).toBe(true);
  });
});

describe("idsInsidePolygon", () => {
  it("filters points by polygon membership", () => {
    const points = [
      { moleculeId: "a", x: 5, y: 5 },
      { moleculeId: "b", x: 100, y: 100 },
      { moleculeId: "c", x: 2, y: 8 },
    ];
    const ids = idsInsidePolygon(points, SQUARE);
    expect(new Set(ids)).toEqual(new Set(["a", "c"]));
  });
});
```

- [ ] **Step 2: Implement**

```ts
// Ray-casting point-in-polygon.

export interface Point {
  x: number;
  y: number;
}

export interface IdPoint {
  moleculeId: string;
  x: number;
  y: number;
}

export function pointInPolygon(p: Point, poly: Point[]): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i].x, yi = poly[i].y;
    const xj = poly[j].x, yj = poly[j].y;
    const intersect =
      ((yi > p.y) !== (yj > p.y)) &&
      p.x < ((xj - xi) * (p.y - yi)) / (yj - yi || Number.EPSILON) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

export function idsInsidePolygon(points: IdPoint[], poly: Point[]): string[] {
  if (poly.length < 3) return [];
  return points.filter((pt) => pointInPolygon(pt, poly)).map((pt) => pt.moleculeId);
}
```

- [ ] **Step 3: Run + pass**

```bash
cd /Users/sidx/workspace/chem-vault2/frontend
pnpm vitest run src/features/sar-analysis/lib/lasso-math.test.ts
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/sar-analysis/lib/lasso-math.ts frontend/src/features/sar-analysis/lib/lasso-math.test.ts
git commit -m "feat(sar): lasso-math — point-in-polygon for cluster map"
```

---

## Task 18: `cluster-palette.ts`

**Files:**
- Create: `frontend/src/features/sar-analysis/lib/cluster-palette.ts`
- Test: `frontend/src/features/sar-analysis/lib/cluster-palette.test.ts`

Produces per-point fill color based on `ColorMode`. Reuses:
- The categorical palette from `frontend/src/shared/lib/chart-colors.ts` for `cluster` mode.
- The 4-bin pIC50 classification colors from the search-grid's `activity-bin.ts` (or equivalent) for `activity` mode.
- The Bemis-Murcko scaffold palette for `scaffold` mode (V2 already ships this — confirm exported helper).
- `#a1a1aa` for `none`.

- [ ] **Step 1: Failing test**

```ts
import { describe, expect, it } from "vitest";
import { colorForPoint } from "./cluster-palette";

describe("colorForPoint", () => {
  it("returns palette color for cluster mode", () => {
    const c = colorForPoint(
      { mode: "cluster" },
      { clusterId: 0, activityPic50: null, scaffoldId: null },
    );
    expect(c).toMatch(/^#/);
  });

  it("returns grey for none mode", () => {
    expect(
      colorForPoint(
        { mode: "none" },
        { clusterId: 0, activityPic50: null, scaffoldId: null },
      ),
    ).toBe("#a1a1aa");
  });

  it("returns hollow ring fill for activity mode with no curve", () => {
    const c = colorForPoint(
      { mode: "activity", protocolId: "p1" },
      { clusterId: 0, activityPic50: null, scaffoldId: null },
    );
    expect(c).toBe("transparent");
  });

  it("returns gradient color for activity with pIC50", () => {
    const c = colorForPoint(
      { mode: "activity", protocolId: "p1" },
      { clusterId: 0, activityPic50: 7.0, scaffoldId: null },
    );
    expect(c).toMatch(/^#/);
  });
});
```

- [ ] **Step 2: Implement**

```ts
import { CHART_COLORS } from "@/shared/lib/chart-colors";
import { activityColorForPic50 } from "@/features/research-organization/lib/activity-color";
// ^ verify the actual export path for the existing 4-bin activity color helper.
// If named differently in your repo, swap the import; the function exists from V2's
// search-grid color-by-protocol implementation.
import { scaffoldColorForBucket } from "@/features/sar-analysis/lib/scaffold-palette";
// ^ V2 shipped this helper; if named differently, swap the import.

export type ColorOption =
  | { mode: "cluster" }
  | { mode: "activity"; protocolId: string }
  | { mode: "scaffold" }
  | { mode: "none" };

export interface PointPaint {
  clusterId: number;
  activityPic50: number | null;
  scaffoldId: string | null;
}

const MUTED_GREY = "#a1a1aa";

export function colorForPoint(opt: ColorOption, paint: PointPaint): string {
  switch (opt.mode) {
    case "cluster":
      return CHART_COLORS[paint.clusterId % CHART_COLORS.length];
    case "activity":
      if (paint.activityPic50 == null) return "transparent";
      return activityColorForPic50(paint.activityPic50);
    case "scaffold":
      return paint.scaffoldId
        ? scaffoldColorForBucket(paint.scaffoldId)
        : MUTED_GREY;
    case "none":
      return MUTED_GREY;
  }
}
```

- [ ] **Step 3: Run + pass**

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/sar-analysis/lib/cluster-palette.ts \
        frontend/src/features/sar-analysis/lib/cluster-palette.test.ts
git commit -m "feat(sar): cluster-palette — color-by Cluster/Activity/Scaffold/None"
```

---

## Task 19: `usePickerConfig` + `useColorMode` URL hooks

**Files:**
- Create: `frontend/src/features/sar-analysis/lib/use-picker-config.ts`
- Create: `frontend/src/features/sar-analysis/lib/use-color-mode.ts`
- Test: each gets a `.test.ts` next to it.

Both mirror the URL-state pattern in `frontend/src/features/sar-analysis/lib/use-tree-sub-mode.ts` (V2). Same pub/sub mechanism for cross-subscriber sync.

- [ ] **Step 1: usePickerConfig test**

```ts
import { renderHook, act } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { usePickerConfig } from "./use-picker-config";

describe("usePickerConfig", () => {
  it("defaults to maxmin n=50", () => {
    const { result } = renderHook(() => usePickerConfig());
    expect(result.current.picker).toBe("maxmin");
    expect(result.current.n).toBe(50);
  });

  it("switching to butina swaps n for threshold default", () => {
    const { result } = renderHook(() => usePickerConfig());
    act(() => result.current.setPicker("butina"));
    expect(result.current.picker).toBe("butina");
    expect(result.current.threshold).toBe(0.4);
  });
});
```

- [ ] **Step 2: usePickerConfig impl**

```ts
"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";
import type { UmapPicker } from "@/features/sar-analysis/types";

export interface PickerConfig {
  picker: UmapPicker;
  n: number;       // maxmin
  threshold: number; // butina
  setPicker: (p: UmapPicker) => void;
  setN: (n: number) => void;
  setThreshold: (t: number) => void;
}

const DEFAULT_N = 50;
const DEFAULT_THRESHOLD = 0.4;

export function usePickerConfig(): PickerConfig {
  const router = useRouter();
  const params = useSearchParams();

  const picker = (params.get("picker") as UmapPicker) ?? "maxmin";
  const n = Number(params.get("n") ?? DEFAULT_N);
  const threshold = Number(params.get("t") ?? DEFAULT_THRESHOLD);

  const update = useCallback(
    (next: Record<string, string | null>) => {
      const sp = new URLSearchParams(params.toString());
      for (const [k, v] of Object.entries(next)) {
        if (v == null) sp.delete(k);
        else sp.set(k, v);
      }
      router.replace(`?${sp.toString()}`, { scroll: false });
    },
    [params, router],
  );

  return {
    picker,
    n,
    threshold,
    setPicker: (p) => {
      if (p === "maxmin") update({ picker: "maxmin", t: null });
      else update({ picker: "butina", n: null });
    },
    setN: (val) => update({ n: String(val) }),
    setThreshold: (val) => update({ t: String(val) }),
  };
}
```

- [ ] **Step 3: useColorMode test**

```ts
import { renderHook, act } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useColorMode } from "./use-color-mode";

describe("useColorMode", () => {
  it("defaults to cluster", () => {
    const { result } = renderHook(() => useColorMode({ defaultMode: "cluster" }));
    expect(result.current.mode).toBe("cluster");
  });

  it("switching to activity preserves protocol id", () => {
    const { result } = renderHook(() => useColorMode({ defaultMode: "cluster" }));
    act(() => result.current.setMode("activity", "proto-1"));
    expect(result.current.mode).toBe("activity");
    expect(result.current.protocolId).toBe("proto-1");
  });
});
```

- [ ] **Step 4: useColorMode impl**

```ts
"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";
import type { ColorMode } from "@/features/sar-analysis/types";

export function useColorMode(opts: { defaultMode: ColorMode }) {
  const router = useRouter();
  const params = useSearchParams();
  const mode = (params.get("color") as ColorMode) ?? opts.defaultMode;
  const protocolId = params.get("color-protocol");

  const setMode = useCallback(
    (next: ColorMode, protocol?: string) => {
      const sp = new URLSearchParams(params.toString());
      if (next === opts.defaultMode) sp.delete("color");
      else sp.set("color", next);
      if (next === "activity" && protocol) sp.set("color-protocol", protocol);
      else sp.delete("color-protocol");
      router.replace(`?${sp.toString()}`, { scroll: false });
    },
    [params, router, opts.defaultMode],
  );

  return { mode, protocolId, setMode };
}
```

- [ ] **Step 5: Run + pass + commit**

```bash
pnpm vitest run src/features/sar-analysis/lib/use-picker-config.test.ts src/features/sar-analysis/lib/use-color-mode.test.ts
git add frontend/src/features/sar-analysis/lib/use-picker-config.ts \
        frontend/src/features/sar-analysis/lib/use-color-mode.ts \
        frontend/src/features/sar-analysis/lib/use-picker-config.test.ts \
        frontend/src/features/sar-analysis/lib/use-color-mode.test.ts
git commit -m "feat(sar): usePickerConfig + useColorMode URL state hooks"
```

---

## Task 20: `useUmapCluster` hook

**Files:**
- Create: `frontend/src/features/sar-analysis/hooks/use-umap-cluster.ts`
- Test: `frontend/src/features/sar-analysis/hooks/use-umap-cluster.test.tsx`

Mirror `useScaffoldTree` exactly. Sync path returns inline; async path polls every 500ms then 2s.

- [ ] **Step 1: Implement** (mirror the V2 hook shape directly — see `use-scaffold-tree.ts` for the canonical pattern):

```ts
"use client";

import { useEffect, useState } from "react";
import {
  useStartUmapCluster,
  useGetUmapClusterJob,
} from "@/shared/api";
import {
  dtoToUmapJob,
  dtoToUmapResult,
  type UmapJob,
  type UmapPicker,
  type UmapResult,
} from "@/features/sar-analysis/types";

export interface UseUmapClusterInput {
  collectionId?: string;
  moleculeIds?: string[];
  picker: UmapPicker;
  n?: number;
  threshold?: number;
  enabled: boolean;
}

export interface UseUmapClusterReturn {
  result: UmapResult | null;
  job: UmapJob | null;
  loading: boolean;
  error: string | null;
  cancel: () => void;
}

export function useUmapCluster(input: UseUmapClusterInput): UseUmapClusterReturn {
  const [result, setResult] = useState<UmapResult | null>(null);
  const [job, setJob] = useState<UmapJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  const start = useStartUmapCluster();
  const poll = useGetUmapClusterJob(job?.id ?? "", {
    query: {
      enabled: job !== null && job.status !== "ready" && job.status !== "failed",
      refetchInterval: job?.status === "pending" ? 500 : 2000,
    },
  });

  useEffect(() => {
    if (!input.enabled) return;
    setResult(null);
    setJob(null);
    setError(null);
    start
      .mutateAsync({
        data: {
          collection_id: input.collectionId,
          molecule_ids: input.moleculeIds,
          picker: input.picker,
          n: input.n,
          threshold: input.threshold,
        },
      })
      .then((resp) => {
        if (resp.result) setResult(dtoToUmapResult(resp.result));
        else if (resp.job) setJob(dtoToUmapJob(resp.job));
      })
      .catch((e) => setError(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    input.enabled,
    input.collectionId,
    JSON.stringify(input.moleculeIds),
    input.picker,
    input.n,
    input.threshold,
  ]);

  useEffect(() => {
    if (!poll.data) return;
    if (poll.data.result) setResult(dtoToUmapResult(poll.data.result));
    if (poll.data.job) setJob(dtoToUmapJob(poll.data.job));
    if (poll.data.job?.status === "failed")
      setError(poll.data.job.error_message ?? "Failed");
  }, [poll.data]);

  return {
    result,
    job,
    loading: start.isPending || (job != null && job.status !== "ready" && job.status !== "failed"),
    error,
    cancel: () => {
      // Implement via useCancelUmapClusterJob when in async mode.
    },
  };
}
```

- [ ] **Step 2: Smoke test** (mock the orval hooks):

```tsx
// abbreviated for brevity — model on tests/features/sar-analysis/use-scaffold-tree.test.tsx
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/sar-analysis/hooks/use-umap-cluster.ts \
        frontend/src/features/sar-analysis/hooks/use-umap-cluster.test.tsx
git commit -m "feat(sar): useUmapCluster hook (sync + async poll)"
```

---

## Task 21: `<ClusterScatter />`

**Files:**
- Create: `frontend/src/features/sar-analysis/components/cluster-scatter.tsx`
- Test: `frontend/src/features/sar-analysis/components/cluster-scatter.test.tsx`

Wraps `react-plotly.js` Scattergl with:
- Two traces: base points + representative stars.
- Custom modebar: `["lasso2d", "pan2d"]`.
- `onSelected` callback bubbling lasso polygon.
- Hover template with depiction image URL.

- [ ] **Step 1: Failing test** (mock react-plotly.js):

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// Mock react-plotly.js to avoid pulling Plotly.js into JSDOM
vi.mock("react-plotly.js", () => ({
  default: (props: any) => (
    <div data-testid="plotly" data-traces={String(props.data?.length ?? 0)} />
  ),
}));

import { ClusterScatter } from "./cluster-scatter";

describe("ClusterScatter", () => {
  it("renders two traces (base + stars) when representatives present", () => {
    render(
      <ClusterScatter
        points={[{ moleculeId: "a", x: 0, y: 0 }]}
        clusters={[{ moleculeId: "a", clusterId: 0 }]}
        representatives={[{ moleculeId: "a", clusterId: 0 }]}
        colorMode={{ mode: "cluster" }}
        activityPic50={{}}
        scaffoldByMol={{}}
        onSelected={() => {}}
        onPointClick={() => {}}
      />,
    );
    expect(screen.getByTestId("plotly").dataset.traces).toBe("2");
  });

  it("renders one trace when no representatives picked yet", () => {
    render(
      <ClusterScatter
        points={[{ moleculeId: "a", x: 0, y: 0 }]}
        clusters={[{ moleculeId: "a", clusterId: 0 }]}
        representatives={[]}
        colorMode={{ mode: "none" }}
        activityPic50={{}}
        scaffoldByMol={{}}
        onSelected={() => {}}
        onPointClick={() => {}}
      />,
    );
    expect(screen.getByTestId("plotly").dataset.traces).toBe("1");
  });
});
```

- [ ] **Step 2: Implement**

```tsx
"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";
import type {
  ClusterAssignment,
  RepresentativePick,
  UmapPoint,
} from "@/features/sar-analysis/types";
import {
  colorForPoint,
  type ColorOption,
} from "@/features/sar-analysis/lib/cluster-palette";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface ClusterScatterProps {
  points: UmapPoint[];
  clusters: ClusterAssignment[];
  representatives: RepresentativePick[];
  colorMode: ColorOption;
  activityPic50: Record<string, number | null>;
  scaffoldByMol: Record<string, string | null>;
  onSelected: (polygon: { x: number; y: number }[] | null) => void;
  onPointClick: (moleculeId: string) => void;
  lassoActive?: boolean;
}

export function ClusterScatter({
  points,
  clusters,
  representatives,
  colorMode,
  activityPic50,
  scaffoldByMol,
  onSelected,
  onPointClick,
}: ClusterScatterProps) {
  const clusterById = useMemo(
    () => new Map(clusters.map((c) => [c.moleculeId, c.clusterId])),
    [clusters],
  );

  const fillColors = useMemo(
    () =>
      points.map((p) =>
        colorForPoint(colorMode, {
          clusterId: clusterById.get(p.moleculeId) ?? 0,
          activityPic50: activityPic50[p.moleculeId] ?? null,
          scaffoldId: scaffoldByMol[p.moleculeId] ?? null,
        }),
      ),
    [points, colorMode, clusterById, activityPic50, scaffoldByMol],
  );

  const baseTrace = {
    type: "scattergl",
    mode: "markers",
    x: points.map((p) => p.x),
    y: points.map((p) => p.y),
    marker: { color: fillColors, size: 8, line: { width: 0.5, color: "#fff" } },
    customdata: points.map((p) => p.moleculeId),
    hovertemplate: "%{customdata}<extra></extra>",
  } as const;

  const repIds = new Set(representatives.map((r) => r.moleculeId));
  const starTrace = representatives.length
    ? {
        type: "scattergl",
        mode: "markers",
        x: points.filter((p) => repIds.has(p.moleculeId)).map((p) => p.x),
        y: points.filter((p) => repIds.has(p.moleculeId)).map((p) => p.y),
        marker: {
          symbol: "star",
          size: 16,
          color: "rgba(0,0,0,0)",
          line: { width: 1.5, color: "#ffffff" },
        },
        hoverinfo: "skip" as const,
      }
    : null;

  const data = starTrace ? [baseTrace, starTrace] : [baseTrace];

  return (
    <Plot
      data={data as any}
      layout={{
        autosize: true,
        margin: { l: 24, r: 8, t: 8, b: 24 },
        xaxis: { showgrid: false, zeroline: false, visible: false },
        yaxis: { showgrid: false, zeroline: false, visible: false },
        dragmode: "lasso",
        showlegend: false,
      }}
      config={{
        displaylogo: false,
        modeBarButtonsToRemove: [
          "zoom2d",
          "select2d",
          "zoomIn2d",
          "zoomOut2d",
          "autoScale2d",
          "resetScale2d",
        ],
      }}
      style={{ width: "100%", height: "100%" }}
      useResizeHandler
      onSelected={(ev: any) => {
        if (!ev || !ev.range) {
          onSelected(null);
          return;
        }
        // Plotly's onSelected gives box range OR a polygon path; capture polygon vertices.
        const polygon =
          ev.lassoPoints?.x?.map((x: number, i: number) => ({
            x,
            y: ev.lassoPoints.y[i],
          })) ?? null;
        onSelected(polygon);
      }}
      onClick={(ev: any) => {
        const pt = ev?.points?.[0];
        if (pt?.customdata) onPointClick(pt.customdata as string);
      }}
    />
  );
}
```

- [ ] **Step 3: Run + pass + commit**

```bash
pnpm vitest run src/features/sar-analysis/components/cluster-scatter.test.tsx
git add frontend/src/features/sar-analysis/components/cluster-scatter.tsx \
        frontend/src/features/sar-analysis/components/cluster-scatter.test.tsx
git commit -m "feat(sar): ClusterScatter — Plotly Scattergl + lasso + star reps"
```

---

## Task 22: `<ColorModePicker />`

**Files:**
- Create: `frontend/src/features/sar-analysis/components/color-mode-picker.tsx`

Renders a `Select` (shadcn) with four options. When `activity` is picked, an inline second `Select` of protocol names appears (sourced from the result-set's activity-columns metadata, passed in as a prop). Mirrors the scaffold-tree `ColorPicker` shape (`scaffold-color-picker.tsx`).

- [ ] **Step 1: Implement (skip a unit test — same shape as V2's color picker, which has zero unit tests):**

```tsx
"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/components/ui/select";
import type { ColorMode } from "@/features/sar-analysis/types";

export interface ProtocolOption {
  id: string;
  name: string;
}

interface ColorModePickerProps {
  mode: ColorMode;
  protocolId: string | null;
  protocols: ProtocolOption[];
  onChange: (mode: ColorMode, protocolId?: string) => void;
}

export function ColorModePicker({ mode, protocolId, protocols, onChange }: ColorModePickerProps) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-muted-foreground">Color by:</span>
      <Select
        value={mode}
        onValueChange={(v) => onChange(v as ColorMode, protocolId ?? protocols[0]?.id)}
      >
        <SelectTrigger className="h-8 w-32"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value="cluster">Cluster</SelectItem>
          <SelectItem value="activity" disabled={protocols.length === 0}>Activity</SelectItem>
          <SelectItem value="scaffold">Scaffold</SelectItem>
          <SelectItem value="none">None</SelectItem>
        </SelectContent>
      </Select>
      {mode === "activity" && protocols.length > 0 && (
        <Select
          value={protocolId ?? protocols[0].id}
          onValueChange={(v) => onChange("activity", v)}
        >
          <SelectTrigger className="h-8 w-40"><SelectValue /></SelectTrigger>
          <SelectContent>
            {protocols.map((p) => (
              <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/features/sar-analysis/components/color-mode-picker.tsx
git commit -m "feat(sar): ColorModePicker — color-by dropdown + protocol sub-picker"
```

---

## Task 23: `<ClusterToolbar />`

**Files:**
- Create: `frontend/src/features/sar-analysis/components/cluster-toolbar.tsx`
- Test: `frontend/src/features/sar-analysis/components/cluster-toolbar.test.tsx`

Toolbar layout: ColorModePicker (left) → Picker `Select` → N input OR Threshold slider (swaps with picker) → `Diversify` button → `Save selection (N)` button (count badge).

- [ ] **Step 1: Failing test**

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ClusterToolbar } from "./cluster-toolbar";

describe("ClusterToolbar", () => {
  it("shows N input when picker=maxmin", () => {
    render(
      <ClusterToolbar
        picker="maxmin"
        n={50}
        threshold={0.4}
        selectedCount={0}
        onPickerChange={() => {}}
        onNChange={() => {}}
        onThresholdChange={() => {}}
        onDiversify={() => {}}
        onSave={() => {}}
        colorPicker={null}
      />,
    );
    expect(screen.getByLabelText(/^n$/i)).toBeInTheDocument();
  });

  it("shows Threshold when picker=butina", () => {
    render(
      <ClusterToolbar
        picker="butina"
        n={50}
        threshold={0.4}
        selectedCount={0}
        onPickerChange={() => {}}
        onNChange={() => {}}
        onThresholdChange={() => {}}
        onDiversify={() => {}}
        onSave={() => {}}
        colorPicker={null}
      />,
    );
    expect(screen.getByLabelText(/threshold/i)).toBeInTheDocument();
  });

  it("Save button shows live count and is disabled at zero", () => {
    const save = vi.fn();
    render(
      <ClusterToolbar
        picker="maxmin"
        n={50}
        threshold={0.4}
        selectedCount={12}
        onPickerChange={() => {}}
        onNChange={() => {}}
        onThresholdChange={() => {}}
        onDiversify={() => {}}
        onSave={save}
        colorPicker={null}
      />,
    );
    const saveBtn = screen.getByRole("button", { name: /save selection \(12\)/i });
    expect(saveBtn).not.toBeDisabled();
    fireEvent.click(saveBtn);
    expect(save).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Implement**

```tsx
"use client";

import { ReactNode } from "react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/shared/components/ui/select";
import { Slider } from "@/shared/components/ui/slider";
import type { UmapPicker } from "@/features/sar-analysis/types";

interface ClusterToolbarProps {
  picker: UmapPicker;
  n: number;
  threshold: number;
  selectedCount: number;
  onPickerChange: (p: UmapPicker) => void;
  onNChange: (n: number) => void;
  onThresholdChange: (t: number) => void;
  onDiversify: () => void;
  onSave: () => void;
  colorPicker: ReactNode;
}

export function ClusterToolbar(props: ClusterToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-3 border-b px-3 py-2">
      {props.colorPicker}
      <div className="flex items-center gap-2 text-xs">
        <span className="text-muted-foreground">Picker:</span>
        <Select value={props.picker} onValueChange={(v) => props.onPickerChange(v as UmapPicker)}>
          <SelectTrigger className="h-8 w-28"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="maxmin">MaxMin</SelectItem>
            <SelectItem value="butina">Butina</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {props.picker === "maxmin" ? (
        <div className="flex items-center gap-2 text-xs">
          <Label htmlFor="cluster-n">N</Label>
          <Input
            id="cluster-n"
            type="number"
            min={1}
            max={1000}
            value={props.n}
            onChange={(e) => props.onNChange(Number(e.target.value))}
            className="h-8 w-20"
          />
        </div>
      ) : (
        <div className="flex items-center gap-2 text-xs">
          <Label htmlFor="cluster-t">Threshold</Label>
          <div className="w-40">
            <Slider
              id="cluster-t"
              min={0.05}
              max={0.95}
              step={0.05}
              value={[props.threshold]}
              onValueChange={(v) => props.onThresholdChange(v[0])}
            />
          </div>
          <span className="font-mono text-xs">{props.threshold.toFixed(2)}</span>
        </div>
      )}

      <Button size="sm" variant="outline" onClick={props.onDiversify}>
        Diversify
      </Button>

      <Button
        size="sm"
        onClick={props.onSave}
        disabled={props.selectedCount === 0}
      >
        Save selection ({props.selectedCount})
      </Button>
    </div>
  );
}
```

- [ ] **Step 3: Run + pass + commit**

```bash
pnpm vitest run src/features/sar-analysis/components/cluster-toolbar.test.tsx
git add frontend/src/features/sar-analysis/components/cluster-toolbar.tsx \
        frontend/src/features/sar-analysis/components/cluster-toolbar.test.tsx
git commit -m "feat(sar): ClusterToolbar — picker + N/threshold + Diversify + Save"
```

---

## Task 24: `<ClusterSelectionPane />`

**Files:**
- Create: `frontend/src/features/sar-analysis/components/cluster-selection-pane.tsx`

Simply renders `<CardGrid />` filtered to a set of molecule IDs. If `selectedIds` is empty, shows all molecules in the compound-set with a muted hint "Lasso a region or click Diversify to make a selection".

- [ ] **Step 1: Implement** (no separate unit test — covered by ClusterMapView integration):

```tsx
"use client";

import { CardGrid } from "@/features/research-organization/components/results/card-grid";
import type { SearchMolecule } from "@/features/research-organization/types";

interface ClusterSelectionPaneProps {
  allMolecules: SearchMolecule[];
  selectedIds: Set<string>;
}

export function ClusterSelectionPane({ allMolecules, selectedIds }: ClusterSelectionPaneProps) {
  const filtered = selectedIds.size > 0
    ? allMolecules.filter((m) => selectedIds.has(m.id))
    : allMolecules;

  return (
    <div className="flex h-full flex-col">
      {selectedIds.size === 0 && (
        <p className="px-4 py-2 text-xs text-muted-foreground">
          Lasso a region or click Diversify to make a selection.
        </p>
      )}
      <div className="flex-1 overflow-auto">
        <CardGrid molecules={filtered} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/features/sar-analysis/components/cluster-selection-pane.tsx
git commit -m "feat(sar): ClusterSelectionPane — right-pane CardGrid wrapper"
```

---

## Task 25: `<SaveSelectionDialog />`

**Files:**
- Create: `frontend/src/features/sar-analysis/components/save-selection-dialog.tsx`
- Test: `frontend/src/features/sar-analysis/components/save-selection-dialog.test.tsx`

shadcn `Dialog` + name input + project picker + scrollable card grid preview + Save/Cancel.

- [ ] **Step 1: Failing test**

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SaveSelectionDialog } from "./save-selection-dialog";

describe("SaveSelectionDialog", () => {
  it("prefills the name from defaultName", () => {
    render(
      <SaveSelectionDialog
        open
        onClose={() => {}}
        onSave={async () => {}}
        selectedMolecules={[{ id: "a", name: "X", reg_number: "R-1" } as any]}
        defaultName="Diversify-5 from My Set"
        projects={[{ id: "p1", name: "P1" }]}
        defaultProjectId="p1"
      />,
    );
    expect(screen.getByDisplayValue(/Diversify-5 from My Set/)).toBeInTheDocument();
  });

  it("calls onSave with name + projectId + ids", async () => {
    const onSave = vi.fn();
    render(
      <SaveSelectionDialog
        open
        onClose={() => {}}
        onSave={onSave}
        selectedMolecules={[{ id: "a", name: "X", reg_number: "R-1" } as any, { id: "b" } as any]}
        defaultName="My collection"
        projects={[{ id: "p1", name: "P1" }]}
        defaultProjectId="p1"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /save & open/i }));
    expect(onSave).toHaveBeenCalledWith({
      name: "My collection",
      projectId: "p1",
      moleculeIds: ["a", "b"],
    });
  });
});
```

- [ ] **Step 2: Implement** — mirror an existing dialog (e.g. the search "Save search" dialog) for project picker + name input shape. Show the new component file with the save signature `(args: { name: string; projectId: string | null; moleculeIds: string[] }) => Promise<void>`.

- [ ] **Step 3: Run + pass + commit**

```bash
git add frontend/src/features/sar-analysis/components/save-selection-dialog.tsx \
        frontend/src/features/sar-analysis/components/save-selection-dialog.test.tsx
git commit -m "feat(sar): SaveSelectionDialog — modal preview before save-as-collection"
```

---

## Task 26: `<ClusterMapView />`

**Files:**
- Create: `frontend/src/features/sar-analysis/components/cluster-map-view.tsx`
- Test: `frontend/src/features/sar-analysis/components/cluster-map-view.test.tsx`

Top-level composition. Owns: `selectedIds`, `lassoPolygon`, `previewOpen`, derives `picker config`, `color mode`. Mirrors `scaffold-tree-view.tsx` shape (split-pane via `react-resizable-panels`, mounts toolbar + scatter on left + CardGrid on right).

Key logic:
- On `Diversify` click: call `useUmapCluster` again with the lassoed subset (if a lasso is active) as `moleculeIds`.
- On Plotly `onSelected`: store polygon, compute `idsInsidePolygon` on the current `result.points`, update `selectedIds`.
- On point click: open compound side sheet.
- On `Save selection`: open `<SaveSelectionDialog />` with the selected molecules + a sensible default name.

- [ ] **Step 1: Implement** (this file ties everything together — code shown abbreviated; mirror `scaffold-tree-view.tsx` for the split-pane scaffolding):

```tsx
"use client";

import { useMemo, useState } from "react";
import { PanelGroup, Panel, PanelResizeHandle } from "react-resizable-panels";
import { ClusterScatter } from "./cluster-scatter";
import { ClusterSelectionPane } from "./cluster-selection-pane";
import { ClusterToolbar } from "./cluster-toolbar";
import { ColorModePicker } from "./color-mode-picker";
import { SaveSelectionDialog } from "./save-selection-dialog";
import { idsInsidePolygon } from "@/features/sar-analysis/lib/lasso-math";
import { usePickerConfig } from "@/features/sar-analysis/lib/use-picker-config";
import { useColorMode } from "@/features/sar-analysis/lib/use-color-mode";
import { useUmapCluster } from "@/features/sar-analysis/hooks/use-umap-cluster";
import type { SearchMolecule } from "@/features/research-organization/types";
import type { ProtocolOption } from "./color-mode-picker";

interface ClusterMapViewProps {
  molecules: SearchMolecule[];
  collectionId?: string;
  protocols: ProtocolOption[]; // for color-by-activity
  defaultColorProtocolId: string | null;
  onSaveCollection: (args: {
    name: string;
    projectId: string | null;
    moleculeIds: string[];
  }) => Promise<void>;
  projects: { id: string; name: string }[];
  defaultProjectId: string | null;
  sourceLabel: string; // e.g. collection name; goes into default save-as name
}

export function ClusterMapView(props: ClusterMapViewProps) {
  const { picker, n, threshold, setPicker, setN, setThreshold } = usePickerConfig();
  const defaultColor = props.defaultColorProtocolId ? "activity" : "cluster";
  const { mode, protocolId, setMode } = useColorMode({ defaultMode: defaultColor });

  const [lassoPolygon, setLassoPolygon] = useState<{ x: number; y: number }[] | null>(null);
  const [diversifyTrigger, setDiversifyTrigger] = useState(0);
  const [pendingSubset, setPendingSubset] = useState<string[] | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  const allIds = useMemo(() => props.molecules.map((m) => m.id), [props.molecules]);

  // The hook re-fires when its inputs change; we toggle moleculeIds when lasso+diversify.
  const { result, loading } = useUmapCluster({
    moleculeIds: pendingSubset ?? allIds,
    collectionId: pendingSubset ? undefined : props.collectionId,
    picker,
    n: picker === "maxmin" ? n : undefined,
    threshold: picker === "butina" ? threshold : undefined,
    enabled: props.molecules.length >= 10,
  });

  // Selected ids: lasso ∩ representatives (when both), else whichever is non-empty.
  const lassoedIds = useMemo(() => {
    if (!lassoPolygon || !result) return new Set<string>();
    return new Set(idsInsidePolygon(result.points, lassoPolygon));
  }, [lassoPolygon, result]);

  const repIds = useMemo(
    () => new Set(result?.representatives.map((r) => r.moleculeId) ?? []),
    [result],
  );

  const selectedIds = useMemo(() => {
    if (repIds.size > 0 && lassoedIds.size > 0) {
      return new Set([...repIds].filter((id) => lassoedIds.has(id)));
    }
    return repIds.size > 0 ? repIds : lassoedIds;
  }, [repIds, lassoedIds]);

  const selectedMolecules = useMemo(
    () => props.molecules.filter((m) => selectedIds.has(m.id)),
    [props.molecules, selectedIds],
  );

  const onDiversify = () => {
    setPendingSubset(lassoPolygon ? [...lassoedIds] : null);
    setDiversifyTrigger((t) => t + 1);
  };

  const defaultName = `Diversify-${selectedIds.size} from ${props.sourceLabel}`;

  return (
    <>
      <ClusterToolbar
        picker={picker}
        n={n}
        threshold={threshold}
        selectedCount={selectedIds.size}
        onPickerChange={setPicker}
        onNChange={setN}
        onThresholdChange={setThreshold}
        onDiversify={onDiversify}
        onSave={() => setPreviewOpen(true)}
        colorPicker={
          <ColorModePicker
            mode={mode}
            protocolId={protocolId}
            protocols={props.protocols}
            onChange={setMode}
          />
        }
      />

      <PanelGroup direction="horizontal" className="flex-1">
        <Panel defaultSize={70} minSize={50} maxSize={80}>
          {loading ? (
            <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
              Computing cluster map…
            </div>
          ) : result ? (
            <ClusterScatter
              points={result.points}
              clusters={result.clusters}
              representatives={result.representatives}
              colorMode={
                mode === "activity"
                  ? { mode: "activity", protocolId: protocolId ?? "" }
                  : { mode }
              }
              activityPic50={{} /* threaded from props when activityData available */}
              scaffoldByMol={{}}
              onSelected={(poly) => setLassoPolygon(poly)}
              onPointClick={(_id) => {
                /* open compound side sheet */
              }}
            />
          ) : null}
        </Panel>
        <PanelResizeHandle className="w-px bg-border hover:bg-accent" />
        <Panel defaultSize={30} minSize={20} maxSize={50}>
          <ClusterSelectionPane
            allMolecules={props.molecules}
            selectedIds={selectedIds}
          />
        </Panel>
      </PanelGroup>

      <SaveSelectionDialog
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
        onSave={async ({ name, projectId, moleculeIds }) => {
          await props.onSaveCollection({ name, projectId, moleculeIds });
          setPreviewOpen(false);
        }}
        selectedMolecules={selectedMolecules}
        defaultName={defaultName}
        projects={props.projects}
        defaultProjectId={props.defaultProjectId}
      />
    </>
  );
}
```

- [ ] **Step 2: Integration test** — abbreviated; mount the view with a stubbed `useUmapCluster` returning a fixed `UmapResult`, verify:
  - Lasso polygon callback filters the right pane.
  - Clicking `Save selection` opens the dialog with the right default name.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/sar-analysis/components/cluster-map-view.tsx \
        frontend/src/features/sar-analysis/components/cluster-map-view.test.tsx
git commit -m "feat(sar): ClusterMapView — split-pane composition + selection state"
```

---

## Task 27: View-mode toggle + `ResultsSurface` wiring

**Files:**
- Modify: `frontend/src/features/research-organization/lib/use-view-mode.ts`
- Modify: `frontend/src/features/research-organization/components/results/view-mode-toggle.tsx`
- Modify: `frontend/src/features/research-organization/components/results/results-surface.tsx`
- Modify: `frontend/src/features/research-organization/hooks/use-collection-search.ts` (so `protocols` + `defaultProtocolId` flow through to ClusterMapView)
- Test: extend `results-surface.test.tsx` to cover the new view branch.

- [ ] **Step 1: Extend `useViewMode`**

```ts
// use-view-mode.ts
export type ViewMode = "cards" | "table" | "tree" | "clusters";
// Existing default = "cards"
// URL value "clusters" round-trips to ?view=clusters
```

- [ ] **Step 2: Extend `<ViewModeToggle />` with a `Cluster` segment** (Lucide icon `ScatterChart`, label "Cluster", `value="clusters"`). Disable when `disabled` prop is true (e.g. < 10 mols).

- [ ] **Step 3: Extend `<ResultsSurface />`**

Add a branch in the existing dispatcher:

```tsx
{view === "clusters" && (
  <ClusterMapView
    molecules={molecules}
    collectionId={collectionId}
    protocols={protocols}
    defaultColorProtocolId={defaultColorProtocolId}
    onSaveCollection={onSaveCollection}
    projects={projects}
    defaultProjectId={defaultProjectId}
    sourceLabel={sourceLabel}
  />
)}
```

Pass `collectionId` from the caller (`CollectionDetail`) and the search-page wiring. `sourceLabel` = collection name on `/collections/{id}`, or "Search results" on `/search`.

- [ ] **Step 4: Wire `onSaveCollection`**

The save callback posts to `POST /api/v1/collections` (already shipped). Redirect to `/collections/{new-id}?view=clusters` on success. Use the existing `useCreateCollection` orval hook + Sonner toast for the create-success pattern.

- [ ] **Step 5: Run all FE tests + tsc**

```bash
cd /Users/sidx/workspace/chem-vault2/frontend
pnpm vitest run
pnpm exec tsc --noEmit
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/research-organization/lib/use-view-mode.ts \
        frontend/src/features/research-organization/components/results/view-mode-toggle.tsx \
        frontend/src/features/research-organization/components/results/results-surface.tsx \
        frontend/src/features/research-organization/hooks/use-collection-search.ts \
        frontend/src/features/research-organization/components/results/results-surface.test.tsx
git commit -m "feat(sar): wire ?view=clusters into ResultsSurface + view-mode toggle"
```

---

## Manual smoke checklist (after Task 27)

Run on the dev stack: `docker compose up -d && cd frontend && pnpm dev`. Confirm Temporal worker is up.

| # | Scenario | Expected |
|---|---|---|
| 1 | `uv run alembic upgrade head` | Migration 039 applies. `\d umap_jobs` shows the table + partial index. |
| 2 | Open `Lead Series A - Quinazolines` (50 mols) → switch to `Cluster` segment | Scatter renders in <3s; tooltip shows ID + name on hover. |
| 3 | Click `Diversify` (N=10) | 10 stars appear; right pane filters to 10 compounds. |
| 4 | Click `Save selection (10)` | Modal opens with 10 cards + default name + project picker pre-filled. |
| 5 | Click `Save & open` | New collection created; redirect to `/collections/{new-id}?view=clusters` showing the 10 in cluster view. |
| 6 | Open the 900-mol `large` collection in `Cluster` view | "Computing cluster map…" caption ~10–30s on first load; second load <500ms (cache hit). |
| 7 | Lasso a region of ~50 points → counter shows "(50)" | Right pane filters to those 50. |
| 8 | With lasso active, edit N to 5 + click `Diversify` | 5 stars appear within the polygon only; right pane shows the 5. |
| 9 | `select status, picker, ids_hash, completed_at from umap_jobs order by requested_at desc limit 5;` | Recent jobs show `ready`; `result_json` populated. |
| 10 | Switch color-by from `Cluster` to `Activity (Mtb_WCA)` | Points recolor with 4-bin pIC50 palette; star overlay persists. |
| 11 | Switch color to `Scaffold` | Points recolor to scaffold-tree's palette. |
| 12 | Deep-link `?view=clusters&picker=butina&t=0.3&color=scaffold` | Loads in that state on first paint. |
| 13 | Open a 5-mol collection | `Cluster` segment is disabled with tooltip "Need ≥ 10 compounds for a meaningful map." |
| 14 | Cancel a long-running async job (Network tab → POST cancel) | Job marks `cancelled`; FE loading state resolves. |

---

## Acceptance criteria (mirrored from spec §9)

- All 14 smoke-checklist items pass.
- New BE unit + integration + API tests green; no regression in the existing 2611+ test suite.
- New FE tests green; `pnpm exec tsc --noEmit` clean.
- Cluster view-mode disabled for collections with < 10 compounds.
- Cold-cache compute time for a 5K-compound collection: < 30s end-to-end.
- Warm-cache response: < 500ms.
- URL state round-trips cleanly.
