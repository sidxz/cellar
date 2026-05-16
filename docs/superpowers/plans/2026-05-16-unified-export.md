# Unified Export — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a shared, always-async export pipeline (CSV / SDF / XLSX / PDF) that exports the *full* search result set, wired into `/search` as the first consumer, ready for runs / batches / activity to plug in next.

**Architecture:** New `domain/export/` (ExportJob aggregate) + `application/export/` (use cases, row_streams, format renderers, orchestrator protocol) + Temporal workflow that streams batches via the same `ExecuteSearch` use case + fsspec-stored files + REST endpoints + new shared FE `ExportToolbar` / `useExport` hook / Sonner progress toast.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy 2.0 async / Pydantic v2 / Temporal / fsspec / openpyxl (write-only) / RDKit (SDWriter) / WeasyPrint + Jinja2 / matplotlib (SVG + PNG) · Next.js 16 / React 19 / TS 5.7 / TanStack Query v5 / shadcn/ui (Sonner toast) / vitest

**Spec:** `docs/superpowers/specs/2026-05-16-unified-export-design.md`

---

## Decisions inherited from spec

| # | Decision |
|---|---|
| D1 | Always-async via Temporal — every export. No sync route. |
| D2 | WeasyPrint + Jinja for PDF (no headless Chrome). |
| D3 | XLSX embeds PNG sparklines up to 5,000 rows; numeric-only beyond, with a `Notes` sheet line. PDF refuses >5,000 rows. |
| D4 | Initial scope = `/search` only. |
| D5 | `ExportJob` aggregate persisted with status/query_snapshot/file_key. |
| D6 | fsspec storage at `exports/{workspace_id}/{job_id}.{ext}`. |
| D7 | 7-day TTL; nightly purge. |
| D8 | Workflow re-runs the query (not snapshot rows). |
| D9 | Renderer writes batch-by-batch to a tempfile, then fsspec upload. |
| D10 | One Sonner toast UX; no inline blocking dialog. |

---

## File map (locks in decomposition)

### Backend — new files

| Path | Responsibility |
|---|---|
| `backend/src/cellar/domain/export/__init__.py` | (empty) |
| `backend/src/cellar/domain/export/enums.py` | `ExportFormat`, `ExportStatus`, `ExportSource` |
| `backend/src/cellar/domain/export/export_job.py` | `ExportJob` aggregate + state machine |
| `backend/src/cellar/domain/export/repository.py` | `ExportJobRepository` Protocol |
| `backend/tests/unit/domain/export/test_export_job.py` | State-machine tests |
| `backend/src/cellar/application/export/__init__.py` | (empty) |
| `backend/src/cellar/application/export/row_streams/__init__.py` | (empty) |
| `backend/src/cellar/application/export/row_streams/base.py` | `RowStream` Protocol + `ColumnSpec` + `ExportRow` |
| `backend/src/cellar/application/export/row_streams/search_results.py` | `SearchResultsRowStream` |
| `backend/src/cellar/application/export/renderers/__init__.py` | (empty) |
| `backend/src/cellar/application/export/renderers/base.py` | `ExportRenderer` Protocol + `RenderOptions` |
| `backend/src/cellar/application/export/renderers/csv_renderer.py` | CSV writer (streaming) |
| `backend/src/cellar/application/export/renderers/sdf_renderer.py` | RDKit SDWriter wrapper |
| `backend/src/cellar/application/export/renderers/excel_renderer.py` | openpyxl write-only + sparkline PNGs |
| `backend/src/cellar/application/export/renderers/pdf_renderer.py` | WeasyPrint + Jinja |
| `backend/src/cellar/application/export/renderers/pdf_template/search_report.html.j2` | PDF template |
| `backend/src/cellar/application/export/renderers/pdf_template/search_report.css` | print CSS |
| `backend/src/cellar/application/export/renderers/sparkline.py` | Shared matplotlib renderer (PNG + SVG) |
| `backend/src/cellar/application/export/orchestration.py` | `ExportOrchestrator` Protocol + DTOs + `WorkflowOrchestratorUnavailable` re-export |
| `backend/src/cellar/application/export/start_export.py` | `StartExport` use case |
| `backend/src/cellar/application/export/get_export_status.py` | `GetExportStatus` |
| `backend/src/cellar/application/export/cancel_export.py` | `CancelExport` |
| `backend/src/cellar/application/export/list_exports.py` | `ListExports` |
| `backend/src/cellar/application/export/purge_expired_exports.py` | `PurgeExpiredExports` |
| `backend/src/cellar/application/export/render_export.py` | `RenderExport` — the in-process runner the workflow / null-orchestrator both call |
| `backend/tests/unit/application/export/test_render_export.py` | End-to-end CSV/SDF/XLSX/PDF via in-memory job |
| `backend/tests/unit/application/export/renderers/test_csv_renderer.py` | |
| `backend/tests/unit/application/export/renderers/test_sdf_renderer.py` | |
| `backend/tests/unit/application/export/renderers/test_excel_renderer.py` | |
| `backend/tests/unit/application/export/renderers/test_pdf_renderer.py` | |
| `backend/tests/unit/application/export/row_streams/test_search_results.py` | |
| `backend/tests/unit/application/export/test_start_export.py` | |
| `backend/tests/unit/application/export/test_get_export_status.py` | |
| `backend/tests/unit/application/export/test_cancel_export.py` | |
| `backend/tests/unit/application/export/test_list_exports.py` | |
| `backend/tests/unit/application/export/test_purge_expired_exports.py` | |
| `backend/src/cellar/infrastructure/persistence/sqlalchemy/export/__init__.py` | (empty) |
| `backend/src/cellar/infrastructure/persistence/sqlalchemy/export/export_job_model.py` | SQLAlchemy model |
| `backend/src/cellar/infrastructure/persistence/sqlalchemy/export/export_job_repository.py` | Repo impl |
| `backend/tests/integration/persistence/test_export_job_repository.py` | Integration tests |
| `backend/src/cellar/infrastructure/temporal/workflows/export.py` | `ExportWorkflow` + progress dataclass |
| `backend/src/cellar/infrastructure/temporal/activities/export.py` | render activities |
| `backend/src/cellar/infrastructure/temporal/orchestrators/export.py` | `TemporalExportOrchestrator` + `NullExportOrchestrator` |
| `backend/src/cellar/infrastructure/di/_export.py` | Lagom container wiring |
| `backend/src/cellar/interface/dependencies/_export.py` | FastAPI deps |
| `backend/alembic/versions/036_export_jobs.py` | Migration |
| `backend/tests/api/test_export_routes.py` | Route tests |

### Backend — modified files

| Path | Change |
|---|---|
| `backend/src/cellar/interface/routes/export.py` | Add `/api/v1/exports*` routes; mark old `/api/v1/molecules/export/sdf` as deprecated (keep responding for 1 release) |
| `backend/src/cellar/interface/dependencies/__init__.py` | Export new deps |
| `backend/src/cellar/infrastructure/di/container.py` | Wire `_export.py` |
| `backend/src/cellar/infrastructure/temporal/worker.py` | Register ExportWorkflow + activities |
| `backend/src/cellar/infrastructure/temporal/task_queues.py` | (no-op if MAIN_TASK_QUEUE already exists; reuse) |
| `backend/pyproject.toml` | Add `weasyprint`, `matplotlib` deps |

### Frontend — new files

| Path | Responsibility |
|---|---|
| `frontend/src/shared/components/export/types.ts` | `ExportFormat`, `ExportRequest`, `ExportJob`, `ExportSource` |
| `frontend/src/shared/components/export/use-export.ts` | TanStack Query mutation + polling hook |
| `frontend/src/shared/components/export/export-toolbar.tsx` | Replacement dropdown — emits ExportRequest |
| `frontend/src/shared/components/export/export-job-toast.tsx` | Sonner-driven progress toast + re-download |
| `frontend/src/shared/components/export/use-export.test.ts` | hook tests |
| `frontend/src/shared/components/export/export-toolbar.test.tsx` | component tests |

### Frontend — modified files

| Path | Change |
|---|---|
| `frontend/src/shared/components/data-grid/data-grid.tsx` | Replace `exportFilename` + `excelEnhancer` + `extraExportItems` props with a single optional `exportRequest?: () => ExportRequest \| null`. Render the new shared toolbar when set. |
| `frontend/src/shared/components/data-grid/export-toolbar.tsx` | **Delete** (old FE-only impl). One commit removes both the file and the old props from data-grid. |
| `frontend/src/features/research-organization/components/search-page.tsx` | Drop `handleExportSdf`, `useSdfExport`; pass a `buildExportRequest(format)` to `<ResultsGrid>` |
| `frontend/src/features/research-organization/components/search/results-grid.tsx` | Drop `onExportSdf`, `extraExportItems`; pass `exportRequest` straight through to `<DataGrid>` |

---

## Implementation order (waves)

**Wave 1 — BE foundation (T1–T4):** domain aggregate, migration, persistence, DI hooks
**Wave 2 — BE renderers + row stream (T5–T10):** CSV → SDF → XLSX → PDF, with `RenderExport` runner that ties them together
**Wave 3 — BE app services (T11–T14):** use cases + orchestrator protocol + Temporal workflow
**Wave 4 — BE routes + observability (T15–T16):** REST endpoints + purge
**Wave 5 — FE shared (T17–T19):** types + hook + toolbar + toast
**Wave 6 — FE search wiring + cleanup (T20–T21):** wire `/search`, delete old code

After each task: tests pass, commit. After each wave: dev-stack smoke.

---

# Wave 1 — Backend foundation

## Task 1: Export domain — `ExportJob` aggregate

**Files:**
- Create: `backend/src/cellar/domain/export/__init__.py`
- Create: `backend/src/cellar/domain/export/enums.py`
- Create: `backend/src/cellar/domain/export/export_job.py`
- Create: `backend/src/cellar/domain/export/repository.py`
- Create: `backend/tests/unit/domain/export/__init__.py`
- Create: `backend/tests/unit/domain/export/test_export_job.py`

- [ ] **Step 1: Write enums**

```python
# backend/src/cellar/domain/export/enums.py
from __future__ import annotations
from enum import StrEnum


class ExportFormat(StrEnum):
    CSV = "csv"
    SDF = "sdf"
    XLSX = "xlsx"
    PDF = "pdf"

    @property
    def extension(self) -> str:
        return f".{self.value}"

    @property
    def media_type(self) -> str:
        return {
            ExportFormat.CSV: "text/csv",
            ExportFormat.SDF: "chemical/x-sdf",
            ExportFormat.XLSX: (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            ExportFormat.PDF: "application/pdf",
        }[self]


class ExportStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ExportSource(StrEnum):
    SEARCH = "search"
    # Future: RUNS, BATCHES, ACTIVITY, COLLECTION, ELN
```

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/unit/domain/export/test_export_job.py
from __future__ import annotations
import uuid
from datetime import datetime, timedelta, UTC

import pytest

from cellar.domain.export.enums import ExportFormat, ExportSource, ExportStatus
from cellar.domain.export.export_job import ExportJob
from cellar.domain.shared.errors import ConflictError


def _make(**overrides) -> ExportJob:
    base = dict(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        requested_by=uuid.uuid4(),
        source=ExportSource.SEARCH,
        format=ExportFormat.CSV,
        query_snapshot={"query": {}, "protocol_columns": []},
        filename="cellar-search.csv",
    )
    base.update(overrides)
    return ExportJob.create(**base)


def test_create_starts_pending():
    job = _make()
    assert job.status == ExportStatus.PENDING
    assert job.progress is None
    assert job.row_count is None
    assert job.requested_at is not None
    assert job.expires_at is None


def test_mark_running_from_pending():
    job = _make()
    job.mark_running()
    assert job.status == ExportStatus.RUNNING
    assert job.started_at is not None


def test_mark_running_from_other_raises():
    job = _make()
    job.mark_running()
    with pytest.raises(ConflictError):
        job.mark_running()


def test_set_row_count():
    job = _make()
    job.mark_running()
    job.set_row_count(1234)
    assert job.row_count == 1234


def test_report_progress_clamped():
    job = _make()
    job.mark_running()
    job.set_row_count(100)
    job.report_progress(0.5)
    assert job.progress == 0.5
    job.report_progress(1.5)  # clamp
    assert job.progress == 1.0
    job.report_progress(-0.1)
    assert job.progress == 0.0


def test_mark_ready_sets_download_metadata():
    job = _make()
    job.mark_running()
    expires = datetime.now(UTC) + timedelta(days=7)
    job.mark_ready(
        file_key="exports/ws/x.csv",
        byte_size=1024,
        content_type="text/csv",
        expires_at=expires,
    )
    assert job.status == ExportStatus.READY
    assert job.file_key == "exports/ws/x.csv"
    assert job.byte_size == 1024
    assert job.expires_at == expires
    assert job.completed_at is not None
    assert job.progress == 1.0


def test_mark_failed_records_error():
    job = _make()
    job.mark_running()
    job.mark_failed("disk full")
    assert job.status == ExportStatus.FAILED
    assert job.error_message == "disk full"
    assert job.completed_at is not None


def test_cancel_flow():
    job = _make()
    job.mark_running()
    job.request_cancel()
    assert job.status == ExportStatus.CANCEL_REQUESTED
    job.mark_cancelled()
    assert job.status == ExportStatus.CANCELLED


def test_cannot_cancel_terminal_job():
    job = _make()
    job.mark_running()
    job.mark_failed("x")
    with pytest.raises(ConflictError):
        job.request_cancel()


def test_mark_expired_requires_ready():
    job = _make()
    job.mark_running()
    with pytest.raises(ConflictError):
        job.mark_expired()
    job.mark_ready("k", 1, "text/csv", datetime.now(UTC))
    job.mark_expired()
    assert job.status == ExportStatus.EXPIRED
    assert job.file_key is None  # storage swept
```

- [ ] **Step 3: Run tests — confirm fail**

Run: `uv run pytest backend/tests/unit/domain/export/test_export_job.py -x`
Expected: ModuleNotFoundError for `cellar.domain.export.export_job`.

- [ ] **Step 4: Implement `ExportJob`**

```python
# backend/src/cellar/domain/export/export_job.py
from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime, UTC

from cellar.domain.export.enums import ExportFormat, ExportSource, ExportStatus
from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.shared.errors import ConflictError

_TERMINAL = {ExportStatus.READY, ExportStatus.FAILED, ExportStatus.CANCELLED, ExportStatus.EXPIRED}


@dataclass
class ExportJob(AggregateRoot):
    workspace_id: uuid.UUID
    requested_by: uuid.UUID
    source: ExportSource
    format: ExportFormat
    query_snapshot: dict
    filename: str
    status: ExportStatus = ExportStatus.PENDING
    row_count: int | None = None
    progress: float | None = None
    file_key: str | None = None
    byte_size: int | None = None
    content_type: str | None = None
    error_message: str | None = None
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        id: uuid.UUID,
        workspace_id: uuid.UUID,
        requested_by: uuid.UUID,
        source: ExportSource,
        format: ExportFormat,
        query_snapshot: dict,
        filename: str,
    ) -> "ExportJob":
        return cls(
            id=id,
            workspace_id=workspace_id,
            requested_by=requested_by,
            source=source,
            format=format,
            query_snapshot=query_snapshot,
            filename=filename,
        )

    def mark_running(self) -> None:
        if self.status != ExportStatus.PENDING:
            raise ConflictError(f"Cannot start job in status {self.status}")
        self.status = ExportStatus.RUNNING
        self.started_at = datetime.now(UTC)
        self.version += 1

    def set_row_count(self, n: int) -> None:
        self.row_count = max(int(n), 0)
        self.version += 1

    def report_progress(self, p: float) -> None:
        self.progress = max(0.0, min(1.0, float(p)))
        self.version += 1

    def mark_ready(
        self,
        file_key: str,
        byte_size: int,
        content_type: str,
        expires_at: datetime,
    ) -> None:
        self.status = ExportStatus.READY
        self.file_key = file_key
        self.byte_size = byte_size
        self.content_type = content_type
        self.expires_at = expires_at
        self.completed_at = datetime.now(UTC)
        self.progress = 1.0
        self.version += 1

    def mark_failed(self, error: str) -> None:
        self.status = ExportStatus.FAILED
        self.error_message = error
        self.completed_at = datetime.now(UTC)
        self.version += 1

    def request_cancel(self) -> None:
        if self.status in _TERMINAL:
            raise ConflictError(f"Cannot cancel job in status {self.status}")
        self.status = ExportStatus.CANCEL_REQUESTED
        self.version += 1

    def mark_cancelled(self) -> None:
        self.status = ExportStatus.CANCELLED
        self.completed_at = datetime.now(UTC)
        self.version += 1

    def mark_expired(self) -> None:
        if self.status != ExportStatus.READY:
            raise ConflictError(f"Cannot expire job in status {self.status}")
        self.status = ExportStatus.EXPIRED
        self.file_key = None
        self.version += 1
```

- [ ] **Step 5: Implement repository Protocol**

```python
# backend/src/cellar/domain/export/repository.py
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Protocol

from cellar.domain.export.export_job import ExportJob


class ExportJobRepository(Protocol):
    async def save(self, job: ExportJob) -> None: ...
    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, job_id: uuid.UUID
    ) -> ExportJob | None: ...
    async def list_in_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int = 50,
        cursor_requested_at: datetime | None = None,
    ) -> list[ExportJob]: ...
    async def find_expired_ready(self, before: datetime, *, limit: int = 100) -> list[ExportJob]: ...
```

- [ ] **Step 6: Run tests — confirm pass**

Run: `uv run pytest backend/tests/unit/domain/export/ -x`
Expected: 10 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/src/cellar/domain/export/ backend/tests/unit/domain/export/
git commit -m "feat(domain): ExportJob aggregate + repository protocol"
```

---

## Task 2: Migration 036 — `export_jobs` table

**Files:**
- Create: `backend/alembic/versions/036_export_jobs.py`

- [ ] **Step 1: Write the migration**

```python
"""036 — export_jobs table.

Persisted ExportJob aggregate. Status / progress columns are mutated by
the worker; query_snapshot is the audit-trail evidence of what was asked.
The (status, expires_at) index supports the nightly purge sweep.

Revision ID: 036_export_jobs
Revises: 035_cc_intercept_key
Create Date: 2026-05-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "036_export_jobs"
down_revision: str | None = "035_cc_intercept_key"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "export_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("query_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("progress", sa.Float(), nullable=True),
        sa.Column("file_key", sa.String(1024), nullable=True),
        sa.Column("byte_size", sa.BigInteger(), nullable=True),
        sa.Column("content_type", sa.String(255), nullable=True),
        sa.Column("filename", sa.String(512), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_export_jobs_workspace_requested_at",
        "export_jobs",
        ["workspace_id", sa.text("requested_at DESC")],
    )
    op.create_index(
        "ix_export_jobs_status_expires_at",
        "export_jobs",
        ["status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_export_jobs_status_expires_at", table_name="export_jobs")
    op.drop_index("ix_export_jobs_workspace_requested_at", table_name="export_jobs")
    op.drop_table("export_jobs")
```

- [ ] **Step 2: Run the migration locally**

Run: `cd backend && uv run alembic upgrade head`
Expected: `Running upgrade 035_cc_intercept_key -> 036_export_jobs`.

Verify: `uv run alembic current` shows `036_export_jobs (head)`.

- [ ] **Step 3: Test downgrade**

Run: `uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: clean round-trip.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/036_export_jobs.py
git commit -m "feat(persistence): migration 036 — export_jobs table"
```

---

## Task 3: SQLAlchemy model + repository implementation

**Files:**
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/export/__init__.py`
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/export/export_job_model.py`
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/export/export_job_repository.py`
- Create: `backend/tests/integration/persistence/test_export_job_repository.py`

- [ ] **Step 1: Write the model**

```python
# backend/src/cellar/infrastructure/persistence/sqlalchemy/export/export_job_model.py
from __future__ import annotations
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Index, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cellar.infrastructure.persistence.sqlalchemy.base import Base, VersionMixin


class ExportJobModel(Base, VersionMixin):
    __tablename__ = "export_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    query_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    progress: Mapped[float | None] = mapped_column(Float, nullable=True)
    file_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    byte_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_export_jobs_workspace_requested_at", "workspace_id", "requested_at"),
        Index("ix_export_jobs_status_expires_at", "status", "expires_at"),
    )
```

> If `VersionMixin` doesn't already exist with a `version` column, check `cellar/infrastructure/persistence/sqlalchemy/base.py` — `WorkspaceIdMixin` is referenced from attachments, so VersionMixin almost certainly exists. If not, declare `version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)` inline.

- [ ] **Step 2: Write the failing repository test (integration)**

```python
# backend/tests/integration/persistence/test_export_job_repository.py
from __future__ import annotations
import uuid
from datetime import datetime, timedelta, UTC

import pytest

from cellar.domain.export.enums import ExportFormat, ExportSource, ExportStatus
from cellar.domain.export.export_job import ExportJob
from cellar.infrastructure.persistence.sqlalchemy.export.export_job_repository import (
    SqlAlchemyExportJobRepository,
)


def _make_job(**over) -> ExportJob:
    base = dict(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        requested_by=uuid.uuid4(),
        source=ExportSource.SEARCH,
        format=ExportFormat.CSV,
        query_snapshot={"q": "x"},
        filename="x.csv",
    )
    base.update(over)
    return ExportJob.create(**base)


@pytest.mark.asyncio
async def test_save_and_load(uow):
    repo = SqlAlchemyExportJobRepository(uow)
    job = _make_job()
    async with uow:
        await repo.save(job)
    async with uow:
        loaded = await repo.find_by_id_in_workspace(job.workspace_id, job.id)
    assert loaded is not None
    assert loaded.status == ExportStatus.PENDING


@pytest.mark.asyncio
async def test_save_round_trip_after_status_changes(uow):
    repo = SqlAlchemyExportJobRepository(uow)
    job = _make_job()
    job.mark_running()
    job.set_row_count(42)
    async with uow:
        await repo.save(job)
    async with uow:
        loaded = await repo.find_by_id_in_workspace(job.workspace_id, job.id)
    assert loaded.status == ExportStatus.RUNNING
    assert loaded.row_count == 42


@pytest.mark.asyncio
async def test_list_in_workspace_filters_and_sorts(uow):
    repo = SqlAlchemyExportJobRepository(uow)
    ws = uuid.uuid4()
    other_ws = uuid.uuid4()
    j1 = _make_job(workspace_id=ws)
    j2 = _make_job(workspace_id=ws)
    j3 = _make_job(workspace_id=other_ws)
    async with uow:
        await repo.save(j1)
        await repo.save(j2)
        await repo.save(j3)
    async with uow:
        result = await repo.list_in_workspace(ws)
    assert {j.id for j in result} == {j1.id, j2.id}


@pytest.mark.asyncio
async def test_find_expired_ready(uow):
    repo = SqlAlchemyExportJobRepository(uow)
    now = datetime.now(UTC)
    j = _make_job()
    j.mark_running()
    j.mark_ready("k", 1, "text/csv", expires_at=now - timedelta(hours=1))
    async with uow:
        await repo.save(j)
    async with uow:
        result = await repo.find_expired_ready(now)
    assert any(x.id == j.id for x in result)
```

> The `uow` fixture is the project's standard async UoW for integration tests. Follow `backend/tests/integration/persistence/test_attachment_repository.py` for the fixture wiring.

- [ ] **Step 3: Implement repo**

```python
# backend/src/cellar/infrastructure/persistence/sqlalchemy/export/export_job_repository.py
from __future__ import annotations
import uuid
from datetime import datetime

from sqlalchemy import desc, select

from cellar.domain.export.enums import ExportFormat, ExportSource, ExportStatus
from cellar.domain.export.export_job import ExportJob
from cellar.infrastructure.persistence.sqlalchemy.export.export_job_model import ExportJobModel
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SqlAlchemyExportJobRepository:
    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def save(self, job: ExportJob) -> None:
        session = self._uow.session
        existing = await session.get(ExportJobModel, job.id)
        if existing is None:
            session.add(_to_model(job))
        else:
            _apply_to_model(existing, job)

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, job_id: uuid.UUID
    ) -> ExportJob | None:
        session = self._uow.session
        stmt = select(ExportJobModel).where(
            ExportJobModel.id == job_id,
            ExportJobModel.workspace_id == workspace_id,
        )
        model = (await session.execute(stmt)).scalar_one_or_none()
        return _to_domain(model) if model else None

    async def list_in_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int = 50,
        cursor_requested_at: datetime | None = None,
    ) -> list[ExportJob]:
        session = self._uow.session
        stmt = (
            select(ExportJobModel)
            .where(ExportJobModel.workspace_id == workspace_id)
            .order_by(desc(ExportJobModel.requested_at))
            .limit(limit)
        )
        if cursor_requested_at is not None:
            stmt = stmt.where(ExportJobModel.requested_at < cursor_requested_at)
        return [_to_domain(m) for m in (await session.execute(stmt)).scalars().all()]

    async def find_expired_ready(self, before: datetime, *, limit: int = 100) -> list[ExportJob]:
        session = self._uow.session
        stmt = (
            select(ExportJobModel)
            .where(
                ExportJobModel.status == ExportStatus.READY.value,
                ExportJobModel.expires_at.isnot(None),
                ExportJobModel.expires_at < before,
            )
            .limit(limit)
        )
        return [_to_domain(m) for m in (await session.execute(stmt)).scalars().all()]


def _to_model(job: ExportJob) -> ExportJobModel:
    return ExportJobModel(
        id=job.id,
        workspace_id=job.workspace_id,
        requested_by=job.requested_by,
        source=job.source.value,
        format=job.format.value,
        query_snapshot=job.query_snapshot,
        status=job.status.value,
        row_count=job.row_count,
        progress=job.progress,
        file_key=job.file_key,
        byte_size=job.byte_size,
        content_type=job.content_type,
        filename=job.filename,
        error_message=job.error_message,
        requested_at=job.requested_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        expires_at=job.expires_at,
        version=job.version,
    )


def _apply_to_model(model: ExportJobModel, job: ExportJob) -> None:
    model.status = job.status.value
    model.row_count = job.row_count
    model.progress = job.progress
    model.file_key = job.file_key
    model.byte_size = job.byte_size
    model.content_type = job.content_type
    model.filename = job.filename
    model.error_message = job.error_message
    model.started_at = job.started_at
    model.completed_at = job.completed_at
    model.expires_at = job.expires_at
    model.version = job.version


def _to_domain(model: ExportJobModel) -> ExportJob:
    return ExportJob(
        id=model.id,
        workspace_id=model.workspace_id,
        requested_by=model.requested_by,
        source=ExportSource(model.source),
        format=ExportFormat(model.format),
        query_snapshot=model.query_snapshot,
        filename=model.filename or "",
        status=ExportStatus(model.status),
        row_count=model.row_count,
        progress=model.progress,
        file_key=model.file_key,
        byte_size=model.byte_size,
        content_type=model.content_type,
        error_message=model.error_message,
        requested_at=model.requested_at,
        started_at=model.started_at,
        completed_at=model.completed_at,
        expires_at=model.expires_at,
        version=model.version,
    )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest backend/tests/integration/persistence/test_export_job_repository.py -x`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/persistence/sqlalchemy/export/ backend/tests/integration/persistence/test_export_job_repository.py
git commit -m "feat(persistence): ExportJob SQLAlchemy model + repo impl"
```

---

## Task 4: DI wiring (Lagom container)

**Files:**
- Create: `backend/src/cellar/infrastructure/di/_export.py`
- Modify: `backend/src/cellar/infrastructure/di/container.py`

- [ ] **Step 1: Wire repo + (placeholder) use cases**

```python
# backend/src/cellar/infrastructure/di/_export.py
from __future__ import annotations

from lagom import Container

from cellar.domain.export.repository import ExportJobRepository
from cellar.infrastructure.persistence.sqlalchemy.export.export_job_repository import (
    SqlAlchemyExportJobRepository,
)


def register_export(container: Container) -> None:
    container[ExportJobRepository] = lambda c: SqlAlchemyExportJobRepository(c[AsyncUnitOfWork])
```

> Match the import + binding style of `_research_organization.py`. If `AsyncUnitOfWork` is the wrong DI key, mirror what `_research_organization.py` does.

- [ ] **Step 2: Wire from container**

In `container.py`, alongside existing `register_*` calls:

```python
from cellar.infrastructure.di._export import register_export
…
register_export(container)
```

- [ ] **Step 3: Smoke test that the binding resolves**

Run: `uv run python -c "from cellar.infrastructure.di.container import container; from cellar.domain.export.repository import ExportJobRepository; print(type(container[ExportJobRepository]).__name__)"`
Expected: `SqlAlchemyExportJobRepository`.

- [ ] **Step 4: Commit**

```bash
git add backend/src/cellar/infrastructure/di/_export.py backend/src/cellar/infrastructure/di/container.py
git commit -m "feat(di): wire export domain repository"
```

---

# Wave 2 — Renderers + row stream

## Task 5: `RowStream` + `ColumnSpec` + `ExportRow`

**Files:**
- Create: `backend/src/cellar/application/export/__init__.py`
- Create: `backend/src/cellar/application/export/row_streams/__init__.py`
- Create: `backend/src/cellar/application/export/row_streams/base.py`

- [ ] **Step 1: Write the protocol + dataclasses**

```python
# backend/src/cellar/application/export/row_streams/base.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal, Protocol


ColumnKind = Literal["text", "number", "smiles", "image_curve", "qualifier", "structure"]


@dataclass(frozen=True)
class ColumnSpec:
    key: str               # stable identifier
    header: str            # human-readable
    kind: ColumnKind
    unit: str | None = None
    group: str | None = None  # logical column-group (e.g. protocol name)


@dataclass
class ExportRow:
    cells: dict[str, Any]
    raw: dict[str, Any] = field(default_factory=dict)


class RowStream(Protocol):
    """Source of export rows + column metadata.

    Implementations must yield rows in deterministic order and expose a
    total_count that the workflow uses to compute progress.
    """

    columns: list[ColumnSpec]

    async def total_count(self) -> int: ...
    async def iter_batches(self, batch_size: int) -> AsyncIterator[list[ExportRow]]: ...
```

- [ ] **Step 2: Commit (no tests — protocol-only file)**

```bash
git add backend/src/cellar/application/export/row_streams/
git commit -m "feat(export): RowStream protocol + ColumnSpec + ExportRow"
```

---

## Task 6: `SearchResultsRowStream`

**Files:**
- Create: `backend/src/cellar/application/export/row_streams/search_results.py`
- Create: `backend/tests/unit/application/export/__init__.py`
- Create: `backend/tests/unit/application/export/row_streams/__init__.py`
- Create: `backend/tests/unit/application/export/row_streams/test_search_results.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/application/export/row_streams/test_search_results.py
from __future__ import annotations
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from cellar.application.export.row_streams.search_results import SearchResultsRowStream


@pytest.mark.asyncio
async def test_iter_batches_walks_cursor():
    workspace = uuid.uuid4()
    page1 = MagicMock(items=[_mol("CV-1"), _mol("CV-2")], next_cursor="cur1", total_count=4)
    page2 = MagicMock(items=[_mol("CV-3"), _mol("CV-4")], next_cursor=None, total_count=4)
    execute = AsyncMock()
    execute.side_effect = [_success(page1), _success(page2)]

    protocols_reader = AsyncMock(return_value=[])
    stream = SearchResultsRowStream(
        workspace_id=workspace,
        payload={"query": {"criteria": []}, "protocol_columns": []},
        execute_search=execute,
        protocols_reader=protocols_reader,
        requested_by=uuid.uuid4(),
    )
    total = await stream.total_count()
    assert total == 4

    batches = []
    async for b in stream.iter_batches(batch_size=2):
        batches.append([r.raw["registration_number"] for r in b])
    assert batches == [["CV-1", "CV-2"], ["CV-3", "CV-4"]]


def _mol(reg: str):
    m = MagicMock()
    m.id = uuid.uuid4()
    m.registration_number.value = reg
    m.name = f"Mol {reg}"
    m.structure.smiles = "CCO"
    m.structure.inchi_key = "X"
    m.descriptors.molecular_weight = 46.0
    m.descriptors.logp = -0.3
    m.descriptors.hbd = 1
    m.descriptors.hba = 1
    m.descriptors.tpsa = 20.2
    m.descriptors.molecular_formula = "C2H6O"
    return m


def _success(page):
    from returns.result import Success
    from cellar.application.shared.pagination import EnrichedPageResult
    return Success(EnrichedPageResult(
        items=page.items,
        next_cursor=page.next_cursor,
        total_count=page.total_count,
        activity_data=None,
        similarity_scores=None,
    ))
```

- [ ] **Step 2: Implement**

```python
# backend/src/cellar/application/export/row_streams/search_results.py
from __future__ import annotations
import uuid
from dataclasses import asdict, dataclass
from typing import Any, AsyncIterator, Awaitable, Callable

from returns.result import Success

from cellar.application.export.row_streams.base import ColumnSpec, ExportRow, RowStream
from cellar.application.research_organization.execute_search import (
    ExecuteSearch,
    ExecuteSearchQuery,
)
from cellar.domain.shared.aggregation_types import SelectionRule


@dataclass
class SearchResultsRowStream(RowStream):
    workspace_id: uuid.UUID
    payload: dict[str, Any]
    execute_search: ExecuteSearch
    protocols_reader: Any                  # ProtocolReader — used to build column headers
    requested_by: uuid.UUID

    def __post_init__(self) -> None:
        self._cached_total: int | None = None
        self._protocols_cache: list | None = None
        self.columns = []  # populated lazily by _ensure_columns

    async def total_count(self) -> int:
        if self._cached_total is None:
            page = await self._fetch_page(cursor=None, limit=1)
            self._cached_total = page.total_count or 0
        return self._cached_total

    async def iter_batches(self, batch_size: int) -> AsyncIterator[list[ExportRow]]:
        await self._ensure_columns()
        cursor: str | None = None
        while True:
            page = await self._fetch_page(cursor=cursor, limit=batch_size)
            if not page.items:
                break
            yield [self._row_for(mol, page.activity_data) for mol in page.items]
            if not page.next_cursor:
                break
            cursor = page.next_cursor

    async def _fetch_page(self, *, cursor: str | None, limit: int):
        cmd = ExecuteSearchQuery(
            workspace_id=self.workspace_id,
            query=self.payload.get("query"),
            saved_search_id=_parse_uuid(self.payload.get("saved_search_id")),
            protocol_columns=self.payload.get("protocol_columns"),
            aggregation=SelectionRule(self.payload.get("aggregation", SelectionRule.LATEST_APPROVED_RUN.value)),
            cursor_id=_parse_uuid(cursor) if cursor else None,
            limit=limit,
            project_ids=[_parse_uuid(p) for p in (self.payload.get("project_ids") or [])],
            sort_by=self.payload.get("sort_by"),
            sort_dir=self.payload.get("sort_dir"),
        )
        result = await self.execute_search(cmd, auth=_AuthShim(self.workspace_id, self.requested_by))
        if not isinstance(result, Success):
            raise RuntimeError(f"search execution failed: {result.failure()}")
        return result.unwrap()

    async def _ensure_columns(self) -> None:
        if self.columns:
            return
        # Protocol metadata for header names
        protocol_cols = self.payload.get("protocol_columns") or []
        self._protocols_cache = await self.protocols_reader(self.workspace_id)
        self.columns = _build_columns(protocol_cols, self._protocols_cache)

    def _row_for(self, mol, activity_data: dict | None) -> ExportRow:
        # raw is the molecule's full serialized payload (used by renderers
        # that need to reach into structure, descriptors, etc.).
        raw = {
            "id": str(mol.id),
            "registration_number": mol.registration_number.value if mol.registration_number else "",
            "name": mol.name,
            "smiles": getattr(mol.structure, "smiles", None) if mol.structure else None,
            "inchi_key": getattr(mol.structure, "inchi_key", None) if mol.structure else None,
            "molecular_formula": getattr(mol.descriptors, "molecular_formula", None) if mol.descriptors else None,
            "molecular_weight": getattr(mol.descriptors, "molecular_weight", None) if mol.descriptors else None,
            "logp": getattr(mol.descriptors, "logp", None) if mol.descriptors else None,
            "hbd": getattr(mol.descriptors, "hbd", None) if mol.descriptors else None,
            "hba": getattr(mol.descriptors, "hba", None) if mol.descriptors else None,
            "tpsa": getattr(mol.descriptors, "tpsa", None) if mol.descriptors else None,
            "activity": (activity_data or {}).get(str(mol.id)) or {},
        }
        cells: dict[str, Any] = {}
        for spec in self.columns:
            cells[spec.key] = _cell_value(spec, raw)
        return ExportRow(cells=cells, raw=raw)


def _build_columns(protocol_cols: list[str], protocols: list) -> list[ColumnSpec]:
    base: list[ColumnSpec] = [
        ColumnSpec(key="registration_number", header="Reg #", kind="text"),
        ColumnSpec(key="name", header="Name", kind="text"),
        ColumnSpec(key="smiles", header="SMILES", kind="smiles"),
        ColumnSpec(key="inchi_key", header="InChIKey", kind="text"),
        ColumnSpec(key="molecular_formula", header="Formula", kind="text"),
        ColumnSpec(key="molecular_weight", header="MW", kind="number"),
        ColumnSpec(key="logp", header="LogP", kind="number"),
        ColumnSpec(key="hbd", header="HBD", kind="number"),
        ColumnSpec(key="hba", header="HBA", kind="number"),
        ColumnSpec(key="tpsa", header="TPSA", kind="number"),
    ]
    # Activity columns — one per protocol_column token; DR tokens expand to
    # one value/qualifier/unit/curve_class tuple per intercept; non-DR
    # tokens emit one value column.
    by_id = {str(p.id): p for p in protocols}
    for col_token in protocol_cols:
        base.extend(_expand_protocol_column(col_token, by_id))
    return base


def _expand_protocol_column(token: str, by_id: dict) -> list[ColumnSpec]:
    # See `frontend/src/features/research-organization/lib/protocol-column-id.ts`
    # for the token grammar:
    #   drc:<rd_id>                          → all intercepts of a DR readout
    #   drc:<rd_id>:<kind>:<level>           → one specific intercept
    #   rd:<proto_id>:<rd_id>:<normalization>→ a scalar readout
    parts = token.split(":")
    if parts[0] == "rd":
        proto_id, rd_id, normalization = parts[1], parts[2], parts[3] if len(parts) > 3 else None
        proto = by_id.get(proto_id)
        rd = next((r for r in (proto.readout_definitions if proto else []) if str(r.id) == rd_id), None)
        rd_name = rd.name if rd else "Readout"
        proto_name = proto.name if proto else "Protocol"
        return [ColumnSpec(
            key=f"{token}::value",
            header=f"{proto_name}::{rd_name}",
            kind="number",
            unit=getattr(rd, "unit", None),
            group=proto_name,
        )]
    if parts[0] == "drc":
        rd_id = parts[1]
        proto = next((p for p in by_id.values()
                      for r in (p.readout_definitions or []) if str(r.id) == rd_id), None)
        rd = next((r for r in (proto.readout_definitions or []) if str(r.id) == rd_id), None) if proto else None
        rd_name = rd.name if rd else "Readout"
        proto_name = proto.name if proto else "Protocol"
        intercepts = (getattr(rd, "dose_response_config", None).intercepts
                      if rd and getattr(rd, "dose_response_config", None) else []) or []
        cols: list[ColumnSpec] = []
        for spec in intercepts:
            label = spec.label or f"{spec.kind.value.upper()}{int(spec.level)}"
            base_key = f"drc:{rd_id}:{spec.kind.value}:{spec.level}"
            cols.extend([
                ColumnSpec(key=f"{base_key}::value", header=f"{proto_name}::{rd_name}::{label}",
                           kind="number", unit=getattr(rd, "unit", None), group=proto_name),
                ColumnSpec(key=f"{base_key}::qualifier", header=f"{proto_name}::{rd_name}::{label}::qualifier",
                           kind="qualifier", group=proto_name),
                ColumnSpec(key=f"{base_key}::unit", header=f"{proto_name}::{rd_name}::{label}::unit",
                           kind="text", group=proto_name),
                ColumnSpec(key=f"{base_key}::run_count", header=f"{proto_name}::{rd_name}::{label}::n",
                           kind="number", group=proto_name),
                ColumnSpec(key=f"{base_key}::curve_class", header=f"{proto_name}::{rd_name}::{label}::class",
                           kind="text", group=proto_name),
            ])
        # One Plot column per readout-def (NOT per intercept) — matches the
        # frontend grid. ExcelRenderer + PdfRenderer look for this column
        # kind to embed sparkline PNG/SVG; CSV + SDF skip it.
        if intercepts:
            cols.append(ColumnSpec(
                key=f"drc:{rd_id}::plot",
                header=f"{proto_name}::{rd_name}::Plot",
                kind="image_curve",
                group=proto_name,
            ))
        return cols
    return []


def _cell_value(spec: ColumnSpec, raw: dict) -> Any:
    if spec.key in raw:
        return raw[spec.key]
    if "::" not in spec.key:
        return None
    col_token, suffix = spec.key.rsplit("::", 1)
    av = (raw.get("activity") or {}).get(col_token)
    if not av:
        return None
    iv = _intercept_for(av, col_token) if col_token.startswith("drc:") else None
    if suffix == "value":
        if iv:
            return None if iv.get("value") is None else iv["value"]
        return av.get("value")
    if suffix == "qualifier":
        return _qualifier_of(av, iv)
    if suffix == "unit":
        return av.get("unit")
    if suffix == "run_count":
        return av.get("run_count") or 1
    if suffix == "curve_class":
        return ((av.get("curve_params") or {}).get("curve_class"))
    return None


def _intercept_for(av: dict, col_token: str) -> dict | None:
    parts = col_token.split(":")
    if len(parts) < 4:
        return None
    target = (parts[2], float(parts[3]))
    for iv in av.get("intercept_values") or []:
        spec = iv.get("spec") or {}
        if (spec.get("kind"), spec.get("level")) == target:
            return iv
    return None


def _qualifier_of(av: dict, iv: dict | None) -> str:
    if iv is not None:
        if iv.get("at_bound"):
            return ">"
        if iv.get("value") is None:
            return "ND"
        return "="
    cc = (av.get("curve_params") or {}).get("curve_class")
    if cc == "inactive":
        return "ND"
    return av.get("qualifier") or "="


def _parse_uuid(value):
    return uuid.UUID(str(value)) if value else None


class _AuthShim:
    """Minimal AuthContext stand-in carrying just workspace + user.

    The export workflow re-runs `ExecuteSearch` with the workspace + user
    from the persisted job. `require_same_workspace` only reads `.workspace_id`.
    """
    def __init__(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> None:
        self.workspace_id = workspace_id
        self.user_id = user_id
        self.workspace_role = "viewer"
```

> The `_AuthShim` is a deliberate inset: re-running ExecuteSearch in a worker context needs *some* AuthContext. The actual `AuthContext` shape is defined in `application/auth.py` — match its public attributes if more are needed.

- [ ] **Step 3: Run tests**

Run: `uv run pytest backend/tests/unit/application/export/row_streams/ -x`
Expected: 1 passed.

- [ ] **Step 4: Commit**

```bash
git add backend/src/cellar/application/export/row_streams/search_results.py backend/tests/unit/application/export/
git commit -m "feat(export): SearchResultsRowStream — cursored re-runs of ExecuteSearch"
```

---

## Task 7: CSV renderer

**Files:**
- Create: `backend/src/cellar/application/export/renderers/__init__.py`
- Create: `backend/src/cellar/application/export/renderers/base.py`
- Create: `backend/src/cellar/application/export/renderers/csv_renderer.py`
- Create: `backend/tests/unit/application/export/renderers/__init__.py`
- Create: `backend/tests/unit/application/export/renderers/test_csv_renderer.py`

- [ ] **Step 1: Write base protocol**

```python
# backend/src/cellar/application/export/renderers/base.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, AsyncIterator

from cellar.application.export.row_streams.base import ColumnSpec, ExportRow


@dataclass(frozen=True)
class RenderOptions:
    include_sparklines: bool = True
    image_size: str = "small"   # "small" | "medium" | "large"
    page_size: str = "A4"
    page_orientation: str = "landscape"
    title: str = "Cellar Export"
    extras: dict = field(default_factory=dict)  # source-specific (e.g. query summary string)


class ExportRenderer(Protocol):
    async def render(
        self,
        *,
        columns: list[ColumnSpec],
        batches: AsyncIterator[list[ExportRow]],
        out_path: Path,
        options: RenderOptions,
        row_count_hint: int,
    ) -> None: ...
```

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/unit/application/export/renderers/test_csv_renderer.py
from __future__ import annotations
from pathlib import Path
from typing import AsyncIterator

import pytest

from cellar.application.export.renderers.base import RenderOptions
from cellar.application.export.renderers.csv_renderer import CsvRenderer
from cellar.application.export.row_streams.base import ColumnSpec, ExportRow


async def _batches(rows: list[list[ExportRow]]) -> AsyncIterator[list[ExportRow]]:
    for b in rows:
        yield b


@pytest.mark.asyncio
async def test_csv_writes_headers_and_rows(tmp_path: Path):
    cols = [
        ColumnSpec(key="reg", header="Reg #", kind="text"),
        ColumnSpec(key="mw", header="MW", kind="number"),
        ColumnSpec(key="drc:rd1:ec:50.0::value", header="Mtb::EC50", kind="number", unit="µM"),
        ColumnSpec(key="drc:rd1:ec:50.0::qualifier", header="Mtb::EC50::q", kind="qualifier"),
    ]
    out = tmp_path / "out.csv"
    renderer = CsvRenderer()
    rows = [[
        ExportRow(cells={"reg": "CV-1", "mw": 421.5, "drc:rd1:ec:50.0::value": 1.23,
                         "drc:rd1:ec:50.0::qualifier": "="}),
        ExportRow(cells={"reg": "CV-2", "mw": 380.1, "drc:rd1:ec:50.0::value": None,
                         "drc:rd1:ec:50.0::qualifier": "ND"}),
    ]]
    await renderer.render(
        columns=cols,
        batches=_batches(rows),
        out_path=out,
        options=RenderOptions(),
        row_count_hint=2,
    )
    text = out.read_text(encoding="utf-8-sig")
    assert text.startswith("Reg #,MW,Mtb::EC50,Mtb::EC50::q\r\n")
    assert "CV-1,421.5,1.23,=\r\n" in text
    assert "CV-2,380.1,,ND\r\n" in text
```

- [ ] **Step 3: Implement**

```python
# backend/src/cellar/application/export/renderers/csv_renderer.py
from __future__ import annotations
import csv
from pathlib import Path
from typing import AsyncIterator

from cellar.application.export.renderers.base import RenderOptions
from cellar.application.export.row_streams.base import ColumnSpec, ExportRow


class CsvRenderer:
    async def render(
        self,
        *,
        columns: list[ColumnSpec],
        batches: AsyncIterator[list[ExportRow]],
        out_path: Path,
        options: RenderOptions,
        row_count_hint: int,
    ) -> None:
        # Image columns (sparklines) aren't meaningful in CSV — drop them
        # before writing so chemists don't see an empty "Plot" column.
        out_cols = [c for c in columns if c.kind != "image_curve"]
        with out_path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow([c.header for c in out_cols])
            async for batch in batches:
                for row in batch:
                    writer.writerow([_serialize(row.cells.get(c.key)) for c in out_cols])


def _serialize(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        # Preserve full precision but strip trailing zeros.
        s = f"{value!r}"
        return s
    return str(value)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest backend/tests/unit/application/export/renderers/test_csv_renderer.py -x`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/application/export/renderers/base.py backend/src/cellar/application/export/renderers/csv_renderer.py backend/src/cellar/application/export/renderers/__init__.py backend/tests/unit/application/export/renderers/
git commit -m "feat(export): CSV renderer + ExportRenderer protocol"
```

---

## Task 8: SDF renderer

**Files:**
- Create: `backend/src/cellar/application/export/renderers/sdf_renderer.py`
- Create: `backend/tests/unit/application/export/renderers/test_sdf_renderer.py`

- [ ] **Step 1: Test**

```python
# backend/tests/unit/application/export/renderers/test_sdf_renderer.py
from __future__ import annotations
from pathlib import Path
from typing import AsyncIterator

import pytest

from cellar.application.export.renderers.base import RenderOptions
from cellar.application.export.renderers.sdf_renderer import SdfRenderer
from cellar.application.export.row_streams.base import ColumnSpec, ExportRow


async def _batches(rows: list[list[ExportRow]]) -> AsyncIterator[list[ExportRow]]:
    for b in rows:
        yield b


@pytest.mark.asyncio
async def test_sdf_writes_mol_blocks_and_data_tags(tmp_path: Path):
    cols = [
        ColumnSpec(key="registration_number", header="Reg #", kind="text"),
        ColumnSpec(key="name", header="Name", kind="text"),
        ColumnSpec(key="smiles", header="SMILES", kind="smiles"),
        ColumnSpec(key="molecular_weight", header="MW", kind="number"),
        ColumnSpec(key="drc:rd1:ec:50.0::value", header="Mtb::EC50", kind="number", unit="µM"),
        ColumnSpec(key="drc:rd1:ec:50.0::qualifier", header="Mtb::EC50::q", kind="qualifier"),
    ]
    rows = [[
        ExportRow(cells={
            "registration_number": "CV-1", "name": "ethanol", "smiles": "CCO",
            "molecular_weight": 46.07,
            "drc:rd1:ec:50.0::value": 1.23, "drc:rd1:ec:50.0::qualifier": "=",
        }, raw={"smiles": "CCO"}),
        ExportRow(cells={
            "registration_number": "CV-2", "name": "no_struct", "smiles": None,
            "molecular_weight": 380.1,
            "drc:rd1:ec:50.0::value": None, "drc:rd1:ec:50.0::qualifier": "ND",
        }, raw={"smiles": None}),
    ]]
    out = tmp_path / "out.sdf"
    await SdfRenderer().render(
        columns=cols,
        batches=_batches(rows),
        out_path=out,
        options=RenderOptions(),
        row_count_hint=2,
    )
    text = out.read_text()
    assert "> <Reg #>" in text
    assert "CV-1" in text
    assert "> <Mtb::EC50>" in text
    assert "1.23" in text
    assert text.count("$$$$") == 1   # 2nd row has no SMILES → skipped
```

- [ ] **Step 2: Implement**

```python
# backend/src/cellar/application/export/renderers/sdf_renderer.py
from __future__ import annotations
from pathlib import Path
from typing import AsyncIterator

from rdkit import Chem
from rdkit.Chem import AllChem

from cellar.application.export.renderers.base import RenderOptions
from cellar.application.export.row_streams.base import ColumnSpec, ExportRow


class SdfRenderer:
    async def render(
        self,
        *,
        columns: list[ColumnSpec],
        batches: AsyncIterator[list[ExportRow]],
        out_path: Path,
        options: RenderOptions,
        row_count_hint: int,
    ) -> None:
        writer = Chem.SDWriter(str(out_path))
        try:
            async for batch in batches:
                for row in batch:
                    smiles = row.cells.get("smiles") or row.raw.get("smiles")
                    if not smiles:
                        continue
                    mol = Chem.MolFromSmiles(smiles)
                    if mol is None:
                        continue
                    AllChem.Compute2DCoords(mol)
                    for col in columns:
                        if col.key == "smiles" or col.kind == "image_curve":
                            continue
                        v = row.cells.get(col.key)
                        if v is None or v == "":
                            continue
                        mol.SetProp(col.header, _serialize(v))
                    writer.write(mol)
        finally:
            writer.close()


def _serialize(value) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest backend/tests/unit/application/export/renderers/test_sdf_renderer.py -x`
Expected: 1 passed.

- [ ] **Step 4: Commit**

```bash
git add backend/src/cellar/application/export/renderers/sdf_renderer.py backend/tests/unit/application/export/renderers/test_sdf_renderer.py
git commit -m "feat(export): SDF renderer (RDKit SDWriter + per-activity data tags)"
```

---

## Task 9: XLSX renderer + sparkline helper

**Files:**
- Create: `backend/src/cellar/application/export/renderers/sparkline.py`
- Create: `backend/src/cellar/application/export/renderers/excel_renderer.py`
- Create: `backend/tests/unit/application/export/renderers/test_excel_renderer.py`
- Modify: `backend/pyproject.toml` (add `matplotlib>=3.9`)

- [ ] **Step 1: Add matplotlib dep**

Edit `backend/pyproject.toml`'s `[project] dependencies` list:

```toml
    "matplotlib>=3.9",
```

Then `cd backend && uv sync`.

- [ ] **Step 2: Sparkline helper**

```python
# backend/src/cellar/application/export/renderers/sparkline.py
from __future__ import annotations
import io
import math


def render_sparkline_png(curve_snapshot: dict | None, *, width: int = 240, height: int = 120) -> bytes | None:
    """Render a small sigmoid + data-point sparkline as PNG bytes.

    Returns None if the snapshot has no usable fit / points (e.g. inactive
    curve in points-only mode — the renderer falls back to no image).

    Reuses the same convention as the FE `DoseResponseFigure`:
      - log10(dose) on the x-axis
      - response on the y-axis
      - 4PL fit traced only when curve_class != "inactive"
      - intercept dashed line at the snapshot's primary intercept
    """
    if not curve_snapshot:
        return None
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    points = curve_snapshot.get("data_points") or []
    fit = curve_snapshot.get("fit") or {}
    inactive = curve_snapshot.get("curve_class") == "inactive"

    if not points and not fit:
        return None

    fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    xs = [math.log10(p["dose"]) for p in points if p.get("dose", 0) > 0]
    ys = [p["response"] for p in points if p.get("dose", 0) > 0]
    if xs:
        ax.scatter(xs, ys, s=8, color="#1f77b4")

    if not inactive and fit:
        bottom = fit.get("bottom", 0)
        top = fit.get("top", 100)
        ec50 = fit.get("ec50", 1.0)
        hill = fit.get("hill_slope", 1.0)
        if ec50 > 0:
            xs_fit = [math.log10(ec50) + i * 0.1 for i in range(-30, 31)]
            ys_fit = [bottom + (top - bottom) / (1 + 10 ** ((math.log10(ec50) - x) * hill)) for x in xs_fit]
            ax.plot(xs_fit, ys_fit, color="#1f77b4", linewidth=1.0)
            ax.axvline(math.log10(ec50), color="#888", linestyle="--", linewidth=0.6)

    ax.set_xticks([])
    ax.set_yticks([])
    buf = io.BytesIO()
    fig.tight_layout(pad=0)
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    return buf.getvalue()
```

- [ ] **Step 3: Excel renderer test**

```python
# backend/tests/unit/application/export/renderers/test_excel_renderer.py
from __future__ import annotations
from pathlib import Path
from typing import AsyncIterator

import pytest
from openpyxl import load_workbook

from cellar.application.export.renderers.base import RenderOptions
from cellar.application.export.renderers.excel_renderer import (
    ExcelRenderer,
    SPARKLINE_ROW_CAP,
)
from cellar.application.export.row_streams.base import ColumnSpec, ExportRow


async def _batches(rows):
    for b in rows:
        yield b


@pytest.mark.asyncio
async def test_excel_writes_data_sheet_with_numeric_cells(tmp_path: Path):
    cols = [
        ColumnSpec(key="reg", header="Reg #", kind="text"),
        ColumnSpec(key="mw", header="MW", kind="number"),
        ColumnSpec(key="drc:rd1:ec:50.0::value", header="Mtb::EC50", kind="number", unit="µM"),
    ]
    rows = [[ExportRow(cells={"reg": "CV-1", "mw": 421.5, "drc:rd1:ec:50.0::value": 1.23})]]
    out = tmp_path / "out.xlsx"
    await ExcelRenderer().render(
        columns=cols, batches=_batches(rows), out_path=out,
        options=RenderOptions(), row_count_hint=1,
    )
    wb = load_workbook(out)
    ws = wb["Data"]
    assert ws["A1"].value == "Reg #"
    assert ws["B2"].value == 421.5
    assert isinstance(ws["B2"].value, float)
    assert ws["C2"].value == 1.23


@pytest.mark.asyncio
async def test_excel_notes_sheet_when_sparkline_cap_tripped(tmp_path: Path):
    cols = [ColumnSpec(key="reg", header="Reg #", kind="text")]
    big_rows = [[ExportRow(cells={"reg": f"CV-{i}"}) for i in range(SPARKLINE_ROW_CAP + 10)]]
    out = tmp_path / "out.xlsx"
    await ExcelRenderer().render(
        columns=cols, batches=_batches(big_rows), out_path=out,
        options=RenderOptions(), row_count_hint=SPARKLINE_ROW_CAP + 10,
    )
    wb = load_workbook(out)
    assert "Notes" in wb.sheetnames
    notes_text = "\n".join(str(c.value or "") for c in wb["Notes"]["A"])
    assert "Sparklines omitted" in notes_text
```

- [ ] **Step 4: Implement**

```python
# backend/src/cellar/application/export/renderers/excel_renderer.py
from __future__ import annotations
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import AsyncIterator

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from cellar.application.export.renderers.base import RenderOptions
from cellar.application.export.renderers.sparkline import render_sparkline_png
from cellar.application.export.row_streams.base import ColumnSpec, ExportRow

SPARKLINE_ROW_CAP = 5000


class ExcelRenderer:
    async def render(
        self,
        *,
        columns: list[ColumnSpec],
        batches: AsyncIterator[list[ExportRow]],
        out_path: Path,
        options: RenderOptions,
        row_count_hint: int,
    ) -> None:
        wb = Workbook(write_only=True)
        ws = wb.create_sheet("Data")
        headers = [c.header for c in columns]
        ws.append(headers)

        embed_sparklines = (
            options.include_sparklines
            and row_count_hint <= SPARKLINE_ROW_CAP
        )
        sparkline_col_indices = [
            i for i, c in enumerate(columns) if c.kind == "image_curve"
        ]

        tempfiles: list = []  # keep open until write
        rows_written = 0
        try:
            async for batch in batches:
                for row in batch:
                    out_row = []
                    for c in columns:
                        v = row.cells.get(c.key)
                        if c.kind == "number" and v is not None:
                            try:
                                v = float(v)
                            except (TypeError, ValueError):
                                pass
                        out_row.append(v if c.kind != "image_curve" else "")
                    ws.append(out_row)
                    rows_written += 1
                    if embed_sparklines and sparkline_col_indices:
                        snapshot = ((row.raw.get("activity") or {})
                                    .get("curve_snapshot") if row.raw else None)
                        png = render_sparkline_png(snapshot) if snapshot else None
                        if png:
                            tf = NamedTemporaryFile(suffix=".png", delete=False)
                            tf.write(png); tf.close()
                            tempfiles.append(tf.name)
                            for ci in sparkline_col_indices:
                                img = XLImage(tf.name)
                                cell_ref = f"{get_column_letter(ci+1)}{rows_written+1}"
                                ws.add_image(img, cell_ref)

            notes = wb.create_sheet("Notes")
            notes.append([options.title])
            notes.append([f"Rows: {rows_written}"])
            if not embed_sparklines and row_count_hint > SPARKLINE_ROW_CAP:
                notes.append([f"Sparklines omitted: row count {row_count_hint} exceeds {SPARKLINE_ROW_CAP} cap."])

            wb.save(out_path)
        finally:
            import os
            for p in tempfiles:
                try:
                    os.unlink(p)
                except OSError:
                    pass
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest backend/tests/unit/application/export/renderers/test_excel_renderer.py -x`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/application/export/renderers/{excel_renderer,sparkline}.py backend/tests/unit/application/export/renderers/test_excel_renderer.py backend/pyproject.toml backend/uv.lock
git commit -m "feat(export): XLSX renderer — numeric cells + embedded sparklines ≤5K rows"
```

---

## Task 10: PDF renderer + Jinja template

**Files:**
- Create: `backend/src/cellar/application/export/renderers/pdf_renderer.py`
- Create: `backend/src/cellar/application/export/renderers/pdf_template/search_report.html.j2`
- Create: `backend/src/cellar/application/export/renderers/pdf_template/search_report.css`
- Create: `backend/src/cellar/application/export/renderers/pdf_template/__init__.py`
- Create: `backend/tests/unit/application/export/renderers/test_pdf_renderer.py`
- Modify: `backend/pyproject.toml` (add `weasyprint>=62`, `Jinja2>=3.1`)

- [ ] **Step 1: Add deps + sync**

Edit `backend/pyproject.toml`:
```toml
    "weasyprint>=62",
    "Jinja2>=3.1",
```
Run: `cd backend && uv sync`.

- [ ] **Step 2: Test**

```python
# backend/tests/unit/application/export/renderers/test_pdf_renderer.py
from __future__ import annotations
from pathlib import Path
from typing import AsyncIterator

import pytest

from cellar.application.export.renderers.base import RenderOptions
from cellar.application.export.renderers.pdf_renderer import PDF_ROW_CAP, PdfRenderer
from cellar.application.export.row_streams.base import ColumnSpec, ExportRow


async def _batches(rows):
    for b in rows:
        yield b


@pytest.mark.asyncio
async def test_pdf_renders_a_small_report(tmp_path: Path):
    cols = [
        ColumnSpec(key="reg", header="Reg #", kind="text"),
        ColumnSpec(key="mw", header="MW", kind="number"),
    ]
    rows = [[ExportRow(cells={"reg": "CV-1", "mw": 421.5})]]
    out = tmp_path / "out.pdf"
    await PdfRenderer().render(
        columns=cols, batches=_batches(rows), out_path=out,
        options=RenderOptions(title="Test export"),
        row_count_hint=1,
    )
    data = out.read_bytes()
    assert data.startswith(b"%PDF")  # valid PDF header


@pytest.mark.asyncio
async def test_pdf_refuses_above_row_cap(tmp_path: Path):
    cols = [ColumnSpec(key="reg", header="Reg #", kind="text")]
    rows = [[ExportRow(cells={"reg": f"CV-{i}"}) for i in range(PDF_ROW_CAP + 1)]]
    out = tmp_path / "out.pdf"
    with pytest.raises(ValueError, match="exceeds"):
        await PdfRenderer().render(
            columns=cols, batches=_batches(rows), out_path=out,
            options=RenderOptions(), row_count_hint=PDF_ROW_CAP + 1,
        )
```

- [ ] **Step 3: Implement renderer**

```python
# backend/src/cellar/application/export/renderers/pdf_renderer.py
from __future__ import annotations
from pathlib import Path
from typing import AsyncIterator

from jinja2 import Environment, FileSystemLoader, select_autoescape

from cellar.application.export.renderers.base import RenderOptions
from cellar.application.export.row_streams.base import ColumnSpec, ExportRow

PDF_ROW_CAP = 5000
PDF_TEMPLATE_DIR = Path(__file__).parent / "pdf_template"


class PdfRenderer:
    def __init__(self) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(PDF_TEMPLATE_DIR)),
            autoescape=select_autoescape(["html", "j2"]),
        )

    async def render(
        self,
        *,
        columns: list[ColumnSpec],
        batches: AsyncIterator[list[ExportRow]],
        out_path: Path,
        options: RenderOptions,
        row_count_hint: int,
    ) -> None:
        if row_count_hint > PDF_ROW_CAP:
            raise ValueError(
                f"PDF row count {row_count_hint} exceeds {PDF_ROW_CAP} cap — use XLSX for larger exports."
            )

        # Materialize batches once — WeasyPrint needs the full body.
        all_rows: list[ExportRow] = []
        async for batch in batches:
            all_rows.extend(batch)

        tmpl = self._env.get_template("search_report.html.j2")
        html = tmpl.render(
            title=options.title,
            columns=columns,
            rows=all_rows,
            options=options,
        )

        from weasyprint import CSS, HTML
        HTML(string=html, base_url=str(PDF_TEMPLATE_DIR)).write_pdf(
            target=str(out_path),
            stylesheets=[CSS(filename=str(PDF_TEMPLATE_DIR / "search_report.css"))],
        )
```

- [ ] **Step 4: Template**

```html+jinja
{# backend/src/cellar/application/export/renderers/pdf_template/search_report.html.j2 #}
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{{ title }}</title>
  <link rel="stylesheet" href="search_report.css">
</head>
<body>
  <div class="page-header">
    <h1>{{ title }}</h1>
    <p class="meta">{{ rows | length }} rows</p>
  </div>
  <table>
    <thead>
      <tr>{% for c in columns %}<th>{{ c.header }}</th>{% endfor %}</tr>
    </thead>
    <tbody>
      {% for row in rows %}
        <tr>
          {% for c in columns %}
            <td class="cell-{{ c.kind }}">
              {%- set v = row.cells.get(c.key) -%}
              {%- if v is none -%}—{%- else -%}{{ v }}{%- endif -%}
            </td>
          {% endfor %}
        </tr>
      {% endfor %}
    </tbody>
  </table>
</body>
</html>
```

```css
/* backend/src/cellar/application/export/renderers/pdf_template/search_report.css */
@page {
  size: A4 landscape;
  margin: 1cm;
  @bottom-right { content: "Page " counter(page) " of " counter(pages); font-size: 9px; color: #666; }
}
body { font-family: -apple-system, "Helvetica Neue", Arial, sans-serif; font-size: 9px; color: #222; }
.page-header { margin-bottom: 0.5em; }
.page-header h1 { font-size: 13px; margin: 0 0 0.2em 0; }
.page-header .meta { color: #777; margin: 0; font-size: 9px; }
table { width: 100%; border-collapse: collapse; }
thead { display: table-header-group; }
th, td { border-bottom: 1px solid #e2e2e2; padding: 4px 6px; text-align: left; vertical-align: top; }
th { background: #f6f6f6; font-weight: 600; }
tr { page-break-inside: avoid; }
.cell-number { text-align: right; font-variant-numeric: tabular-nums; }
.cell-qualifier { color: #777; font-style: italic; }
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest backend/tests/unit/application/export/renderers/test_pdf_renderer.py -x`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/application/export/renderers/pdf_renderer.py backend/src/cellar/application/export/renderers/pdf_template/ backend/tests/unit/application/export/renderers/test_pdf_renderer.py backend/pyproject.toml backend/uv.lock
git commit -m "feat(export): PDF renderer (WeasyPrint + Jinja template)"
```

---

# Wave 3 — Use cases + orchestration

## Task 11: `ExportOrchestrator` Protocol + `RenderExport` runner

**Files:**
- Create: `backend/src/cellar/application/export/orchestration.py`
- Create: `backend/src/cellar/application/export/render_export.py`
- Create: `backend/tests/unit/application/export/test_render_export.py`

- [ ] **Step 1: Protocol**

```python
# backend/src/cellar/application/export/orchestration.py
from __future__ import annotations
import uuid
from dataclasses import dataclass
from typing import Protocol

from cellar.application.orchestration.workflow_status import WorkflowOrchestratorUnavailable  # re-export

__all__ = ["ExportOrchestrator", "StartExportWorkflowRequest", "WorkflowOrchestratorUnavailable"]


@dataclass(frozen=True, kw_only=True)
class StartExportWorkflowRequest:
    job_id: uuid.UUID
    workspace_id: uuid.UUID


class ExportOrchestrator(Protocol):
    async def start(self, request: StartExportWorkflowRequest) -> str: ...
    async def request_cancel(self, workflow_id: str) -> None: ...
```

- [ ] **Step 2: Runner (the in-process renderer used by both null orchestrator + Temporal activity)**

```python
# backend/src/cellar/application/export/render_export.py
from __future__ import annotations
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, UTC
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Callable

import structlog

from cellar.application.export.renderers.base import ExportRenderer, RenderOptions
from cellar.application.export.renderers.csv_renderer import CsvRenderer
from cellar.application.export.renderers.excel_renderer import ExcelRenderer
from cellar.application.export.renderers.pdf_renderer import PdfRenderer
from cellar.application.export.renderers.sdf_renderer import SdfRenderer
from cellar.application.export.row_streams.base import RowStream
from cellar.application.export.row_streams.search_results import SearchResultsRowStream
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.export.enums import ExportFormat, ExportSource, ExportStatus
from cellar.domain.export.export_job import ExportJob
from cellar.domain.export.repository import ExportJobRepository
from cellar.infrastructure.storage.fsspec_client import FsspecStorageClient

logger = structlog.get_logger(__name__)

_TTL_DAYS = 7
_BATCH_SIZE = 500


@dataclass
class RenderExport:
    uow: UnitOfWork
    repo: ExportJobRepository
    storage: FsspecStorageClient
    build_search_stream: Callable[[ExportJob], SearchResultsRowStream]
    progress_step: int = 500

    async def __call__(self, job_id: uuid.UUID, workspace_id: uuid.UUID) -> None:
        async with self.uow:
            job = await self.repo.find_by_id_in_workspace(workspace_id, job_id)
            if job is None:
                raise RuntimeError(f"ExportJob {job_id} not found")
            if job.status not in (ExportStatus.PENDING, ExportStatus.RUNNING):
                logger.info("export.skip_non_runnable", job_id=str(job_id), status=job.status)
                return
            if job.status == ExportStatus.PENDING:
                job.mark_running()
                await self.repo.save(job)

        try:
            stream = self._build_stream(job)
            renderer = _renderer_for(job.format)
            total = await stream.total_count()

            async with self.uow:
                job = await self.repo.find_by_id_in_workspace(workspace_id, job_id)
                job.set_row_count(total)
                await self.repo.save(job)

            ext = job.format.extension
            with NamedTemporaryFile(suffix=ext, delete=False) as tf:
                tmp_path = Path(tf.name)

            options = RenderOptions(title=f"Cellar Export — {job.format.value.upper()}")
            await renderer.render(
                columns=stream.columns,
                batches=_progressing(stream.iter_batches(_BATCH_SIZE),
                                     repo=self.repo, uow=self.uow,
                                     workspace_id=workspace_id, job_id=job_id, total=total),
                out_path=tmp_path,
                options=options,
                row_count_hint=total,
            )

            key = f"exports/{job.workspace_id}/{job.id}{ext}"
            await self.storage.upload(key, tmp_path.read_bytes())
            byte_size = tmp_path.stat().st_size
            tmp_path.unlink(missing_ok=True)

            async with self.uow:
                job = await self.repo.find_by_id_in_workspace(workspace_id, job_id)
                job.mark_ready(
                    file_key=key,
                    byte_size=byte_size,
                    content_type=job.format.media_type,
                    expires_at=datetime.now(UTC) + timedelta(days=_TTL_DAYS),
                )
                await self.repo.save(job)
        except Exception as exc:  # noqa: BLE001 — surface every error to the job record
            logger.exception("export.failed", job_id=str(job_id))
            async with self.uow:
                job = await self.repo.find_by_id_in_workspace(workspace_id, job_id)
                if job is not None:
                    job.mark_failed(str(exc))
                    await self.repo.save(job)
            raise

    def _build_stream(self, job: ExportJob) -> RowStream:
        if job.source == ExportSource.SEARCH:
            return self.build_search_stream(job)
        raise ValueError(f"Unsupported export source: {job.source}")


def _renderer_for(fmt: ExportFormat) -> ExportRenderer:
    return {
        ExportFormat.CSV: CsvRenderer(),
        ExportFormat.SDF: SdfRenderer(),
        ExportFormat.XLSX: ExcelRenderer(),
        ExportFormat.PDF: PdfRenderer(),
    }[fmt]


async def _progressing(source, *, repo, uow, workspace_id, job_id, total):
    rows_done = 0
    async for batch in source:
        rows_done += len(batch)
        yield batch
        if total > 0:
            async with uow:
                job = await repo.find_by_id_in_workspace(workspace_id, job_id)
                if job is None:
                    continue
                job.report_progress(rows_done / total)
                await repo.save(job)
```

- [ ] **Step 3: Test (uses CSV path through fakes)**

```python
# backend/tests/unit/application/export/test_render_export.py
from __future__ import annotations
import uuid
from pathlib import Path
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from cellar.application.export.render_export import RenderExport
from cellar.application.export.row_streams.base import ColumnSpec, ExportRow, RowStream
from cellar.domain.export.enums import ExportFormat, ExportSource, ExportStatus
from cellar.domain.export.export_job import ExportJob


class _FakeStream(RowStream):
    columns = [ColumnSpec(key="reg", header="Reg #", kind="text")]
    async def total_count(self) -> int:
        return 2
    async def iter_batches(self, batch_size: int) -> AsyncIterator[list[ExportRow]]:
        yield [ExportRow(cells={"reg": "CV-1"}), ExportRow(cells={"reg": "CV-2"})]


@pytest.mark.asyncio
async def test_render_export_csv_marks_ready(tmp_path):
    workspace_id = uuid.uuid4()
    job = ExportJob.create(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        requested_by=uuid.uuid4(),
        source=ExportSource.SEARCH,
        format=ExportFormat.CSV,
        query_snapshot={},
        filename="x.csv",
    )

    repo = MagicMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=job)
    repo.save = AsyncMock()
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = False
    storage = MagicMock()
    storage.upload = AsyncMock()

    runner = RenderExport(
        uow=uow,
        repo=repo,
        storage=storage,
        build_search_stream=lambda j: _FakeStream(),
    )
    await runner(job_id=job.id, workspace_id=workspace_id)
    assert job.status == ExportStatus.READY
    assert job.byte_size > 0
    assert storage.upload.await_count == 1
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest backend/tests/unit/application/export/test_render_export.py -x`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/application/export/{orchestration.py,render_export.py} backend/tests/unit/application/export/test_render_export.py
git commit -m "feat(export): RenderExport runner — streams batches, writes via fsspec, marks job ready"
```

---

## Task 12: `start_export`, `get_export_status`, `cancel_export`, `list_exports`, `purge_expired_exports`

**Files:**
- Create: `backend/src/cellar/application/export/start_export.py`
- Create: `backend/src/cellar/application/export/get_export_status.py`
- Create: `backend/src/cellar/application/export/cancel_export.py`
- Create: `backend/src/cellar/application/export/list_exports.py`
- Create: `backend/src/cellar/application/export/purge_expired_exports.py`
- Create: `backend/tests/unit/application/export/test_{start,get_status,cancel,list,purge}.py`

- [ ] **Step 1: `start_export.py`**

```python
# backend/src/cellar/application/export/start_export.py
from __future__ import annotations
import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.export.orchestration import (
    ExportOrchestrator,
    StartExportWorkflowRequest,
    WorkflowOrchestratorUnavailable,
)
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.export.enums import ExportFormat, ExportSource
from cellar.domain.export.export_job import ExportJob
from cellar.domain.export.repository import ExportJobRepository
from cellar.domain.shared.errors import DomainError, ValidationError


@dataclass(frozen=True, kw_only=True)
class StartExportCommand:
    workspace_id: uuid.UUID
    requested_by: uuid.UUID
    source: ExportSource
    format: ExportFormat
    payload: dict[str, Any]
    filename_hint: str | None = None


@dataclass(frozen=True)
class StartExportResult:
    job_id: uuid.UUID


class StartExport:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ExportJobRepository,
        orchestrator: ExportOrchestrator,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._orchestrator = orchestrator

    async def __call__(
        self, cmd: StartExportCommand, *, auth: AuthContext
    ) -> Result[StartExportResult, DomainError]:
        require_workspace_role(auth, "viewer")
        if cmd.source != ExportSource.SEARCH:
            return Failure(ValidationError(f"Unsupported export source: {cmd.source}"))

        job = ExportJob.create(
            id=uuid.uuid4(),
            workspace_id=cmd.workspace_id,
            requested_by=cmd.requested_by,
            source=cmd.source,
            format=cmd.format,
            query_snapshot=cmd.payload,
            filename=(cmd.filename_hint or "cellar-export") + cmd.format.extension,
        )
        async with self._uow:
            await self._repo.save(job)

        try:
            await self._orchestrator.start(StartExportWorkflowRequest(
                job_id=job.id, workspace_id=job.workspace_id,
            ))
        except WorkflowOrchestratorUnavailable as exc:
            return Failure(ValidationError(f"Export workflow unavailable: {exc}"))

        return Success(StartExportResult(job_id=job.id))
```

- [ ] **Step 2: `get_export_status.py`**

```python
# backend/src/cellar/application/export/get_export_status.py
from __future__ import annotations
import uuid
from dataclasses import dataclass
from datetime import datetime

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.export.enums import ExportFormat, ExportStatus
from cellar.domain.export.repository import ExportJobRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetExportStatusQuery:
    workspace_id: uuid.UUID
    job_id: uuid.UUID


@dataclass(frozen=True)
class ExportStatusView:
    id: uuid.UUID
    status: ExportStatus
    format: ExportFormat
    row_count: int | None
    progress: float | None
    error_message: str | None
    download_url: str | None
    byte_size: int | None
    filename: str | None
    requested_at: datetime
    completed_at: datetime | None
    expires_at: datetime | None


class GetExportStatus:
    def __init__(self, uow: UnitOfWork, repo: ExportJobRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, q: GetExportStatusQuery, *, auth: AuthContext
    ) -> Result[ExportStatusView, DomainError]:
        require_same_workspace(auth, q.workspace_id)
        async with self._uow:
            job = await self._repo.find_by_id_in_workspace(q.workspace_id, q.job_id)
        if job is None:
            return Failure(NotFoundError("ExportJob", str(q.job_id)))

        download_url = None
        if job.status == ExportStatus.READY:
            download_url = f"/api/v1/exports/{job.id}/download"

        return Success(ExportStatusView(
            id=job.id,
            status=job.status,
            format=job.format,
            row_count=job.row_count,
            progress=job.progress,
            error_message=job.error_message,
            download_url=download_url,
            byte_size=job.byte_size,
            filename=job.filename,
            requested_at=job.requested_at,
            completed_at=job.completed_at,
            expires_at=job.expires_at,
        ))
```

- [ ] **Step 3: `cancel_export.py`**

```python
# backend/src/cellar/application/export/cancel_export.py
from __future__ import annotations
import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace
from cellar.application.export.orchestration import ExportOrchestrator
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.export.repository import ExportJobRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class CancelExportCommand:
    workspace_id: uuid.UUID
    job_id: uuid.UUID


class CancelExport:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ExportJobRepository,
        orchestrator: ExportOrchestrator,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._orchestrator = orchestrator

    async def __call__(
        self, cmd: CancelExportCommand, *, auth: AuthContext
    ) -> Result[None, DomainError]:
        require_same_workspace(auth, cmd.workspace_id)
        async with self._uow:
            job = await self._repo.find_by_id_in_workspace(cmd.workspace_id, cmd.job_id)
            if job is None:
                return Failure(NotFoundError("ExportJob", str(cmd.job_id)))
            job.request_cancel()
            await self._repo.save(job)
        try:
            await self._orchestrator.request_cancel(f"export-{job.id}")
        except Exception:
            pass  # best-effort
        return Success(None)
```

- [ ] **Step 4: `list_exports.py`** + `purge_expired_exports.py`

```python
# backend/src/cellar/application/export/list_exports.py
from __future__ import annotations
import uuid
from dataclasses import dataclass
from datetime import datetime

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.export.repository import ExportJobRepository
from cellar.domain.shared.errors import DomainError

from cellar.application.export.get_export_status import ExportStatusView


@dataclass(frozen=True, kw_only=True)
class ListExportsQuery:
    workspace_id: uuid.UUID
    limit: int = 50
    cursor_requested_at: datetime | None = None


class ListExports:
    def __init__(self, uow: UnitOfWork, repo: ExportJobRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, q: ListExportsQuery, *, auth: AuthContext
    ) -> Result[list[ExportStatusView], DomainError]:
        require_same_workspace(auth, q.workspace_id)
        async with self._uow:
            jobs = await self._repo.list_in_workspace(
                q.workspace_id,
                limit=q.limit,
                cursor_requested_at=q.cursor_requested_at,
            )
        return Success([_view(j) for j in jobs])


def _view(job) -> ExportStatusView:
    from cellar.domain.export.enums import ExportStatus
    return ExportStatusView(
        id=job.id, status=job.status, format=job.format,
        row_count=job.row_count, progress=job.progress,
        error_message=job.error_message,
        download_url=f"/api/v1/exports/{job.id}/download" if job.status == ExportStatus.READY else None,
        byte_size=job.byte_size, filename=job.filename,
        requested_at=job.requested_at, completed_at=job.completed_at,
        expires_at=job.expires_at,
    )
```

```python
# backend/src/cellar/application/export/purge_expired_exports.py
from __future__ import annotations
from datetime import datetime, UTC

from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.export.repository import ExportJobRepository
from cellar.infrastructure.storage.fsspec_client import FsspecStorageClient


class PurgeExpiredExports:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ExportJobRepository,
        storage: FsspecStorageClient,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._storage = storage

    async def __call__(self) -> int:
        now = datetime.now(UTC)
        async with self._uow:
            jobs = await self._repo.find_expired_ready(now)
        purged = 0
        for job in jobs:
            if job.file_key:
                try:
                    await self._storage.delete(job.file_key)
                except FileNotFoundError:
                    pass
            async with self._uow:
                fresh = await self._repo.find_by_id_in_workspace(job.workspace_id, job.id)
                if fresh is None:
                    continue
                fresh.mark_expired()
                await self._repo.save(fresh)
            purged += 1
        return purged
```

- [ ] **Step 5: Tests (one file per use case, brief asserts)**

For brevity each test follows this skeleton — write `test_start.py`, `test_get_status.py`, `test_cancel.py`, `test_list.py`, `test_purge.py`:

```python
# backend/tests/unit/application/export/test_start_export.py
import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest
from returns.result import Success

from cellar.application.auth import AuthContext
from cellar.application.export.start_export import (
    StartExport, StartExportCommand,
)
from cellar.domain.export.enums import ExportFormat, ExportSource


@pytest.mark.asyncio
async def test_start_persists_job_and_starts_workflow():
    workspace = uuid.uuid4()
    user = uuid.uuid4()
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = False
    repo = MagicMock(); repo.save = AsyncMock()
    orch = MagicMock(); orch.start = AsyncMock(return_value="wf-1")
    auth = AuthContext(workspace_id=workspace, user_id=user, workspace_role="viewer")

    uc = StartExport(uow, repo, orch)
    result = await uc(StartExportCommand(
        workspace_id=workspace, requested_by=user,
        source=ExportSource.SEARCH, format=ExportFormat.CSV,
        payload={"query": {}},
    ), auth=auth)

    assert isinstance(result, Success)
    repo.save.assert_awaited_once()
    orch.start.assert_awaited_once()
```

Write similar focused tests for the other 4 use cases.

- [ ] **Step 6: Run all tests**

Run: `uv run pytest backend/tests/unit/application/export/ -x`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/src/cellar/application/export/*.py backend/tests/unit/application/export/test_{start,get_status,cancel,list,purge}*.py
git commit -m "feat(export): start/get/cancel/list/purge use cases"
```

---

## Task 13: Temporal workflow + orchestrators (null + temporal)

**Files:**
- Create: `backend/src/cellar/infrastructure/temporal/workflows/export.py`
- Create: `backend/src/cellar/infrastructure/temporal/activities/export.py`
- Create: `backend/src/cellar/infrastructure/temporal/orchestrators/export.py`
- Modify: `backend/src/cellar/infrastructure/temporal/worker.py`

- [ ] **Step 1: Workflow**

```python
# backend/src/cellar/infrastructure/temporal/workflows/export.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from cellar.infrastructure.temporal.activities.export import (
        ExportActivities,
        RunExportInput,
    )


@dataclass
class ExportWorkflowInput:
    job_id: str
    workspace_id: str


@workflow.defn
class ExportWorkflow:
    @workflow.run
    async def run(self, input: ExportWorkflowInput) -> None:
        await workflow.execute_activity(
            ExportActivities.run_export,
            RunExportInput(job_id=input.job_id, workspace_id=input.workspace_id),
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
```

- [ ] **Step 2: Activity**

```python
# backend/src/cellar/infrastructure/temporal/activities/export.py
from __future__ import annotations
import uuid
from dataclasses import dataclass

from temporalio import activity

from cellar.application.export.render_export import RenderExport


@dataclass
class RunExportInput:
    job_id: str
    workspace_id: str


class ExportActivities:
    def __init__(self, render_export: RenderExport) -> None:
        self._run = render_export

    @activity.defn
    async def run_export(self, input: RunExportInput) -> None:
        await self._run(uuid.UUID(input.job_id), uuid.UUID(input.workspace_id))
```

- [ ] **Step 3: Orchestrators**

```python
# backend/src/cellar/infrastructure/temporal/orchestrators/export.py
from __future__ import annotations
import asyncio
import uuid

from temporalio.client import Client

from cellar.application.export.orchestration import (
    ExportOrchestrator,
    StartExportWorkflowRequest,
    WorkflowOrchestratorUnavailable,
)
from cellar.application.export.render_export import RenderExport
from cellar.infrastructure.temporal.task_queues import MAIN_TASK_QUEUE
from cellar.infrastructure.temporal.workflows.export import (
    ExportWorkflow,
    ExportWorkflowInput,
)


class TemporalExportOrchestrator:
    def __init__(self, client: Client) -> None:
        self._client = client

    async def start(self, request: StartExportWorkflowRequest) -> str:
        wf_id = f"export-{request.job_id}"
        await self._client.start_workflow(
            ExportWorkflow.run,
            ExportWorkflowInput(
                job_id=str(request.job_id),
                workspace_id=str(request.workspace_id),
            ),
            id=wf_id,
            task_queue=MAIN_TASK_QUEUE,
        )
        return wf_id

    async def request_cancel(self, workflow_id: str) -> None:
        handle = self._client.get_workflow_handle(workflow_id)
        await handle.cancel()


class NullExportOrchestrator:
    """In-process fallback when Temporal is unavailable.

    Runs the RenderExport runner synchronously in the request thread.
    Suitable for dev / tests where the worker isn't up.
    """
    def __init__(self, render_export: RenderExport) -> None:
        self._run = render_export

    async def start(self, request: StartExportWorkflowRequest) -> str:
        # Fire-and-forget; the request returns the job_id immediately and
        # the FE polls. Errors surface on the job record.
        asyncio.create_task(self._run(request.job_id, request.workspace_id))
        return f"inline-{request.job_id}"

    async def request_cancel(self, workflow_id: str) -> None:
        # No-op for the inline path.
        return None
```

- [ ] **Step 4: Worker registration**

In `backend/src/cellar/infrastructure/temporal/worker.py`, add `ExportWorkflow` to the workflows list and `ExportActivities` to activities list following the existing `BulkRegistrationWorkflow` pattern. Resolve `RenderExport` from the DI container at worker start.

- [ ] **Step 5: Smoke run**

Run: `uv run pytest backend/tests/unit/application/export/ -x` (no new tests here — the workflow/activity is a thin adapter).
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/infrastructure/temporal/{workflows,activities,orchestrators}/export.py backend/src/cellar/infrastructure/temporal/worker.py
git commit -m "feat(temporal): ExportWorkflow + activity + orchestrator (Temporal + Null)"
```

---

# Wave 4 — Routes + DI

## Task 14: DI wiring (use cases, orchestrator, render runner, build_search_stream)

**Files:**
- Modify: `backend/src/cellar/infrastructure/di/_export.py`

- [ ] **Step 1: Extend the DI module**

```python
# backend/src/cellar/infrastructure/di/_export.py
from __future__ import annotations
import os

from lagom import Container

from cellar.application.export.cancel_export import CancelExport
from cellar.application.export.get_export_status import GetExportStatus
from cellar.application.export.list_exports import ListExports
from cellar.application.export.orchestration import ExportOrchestrator
from cellar.application.export.purge_expired_exports import PurgeExpiredExports
from cellar.application.export.render_export import RenderExport
from cellar.application.export.row_streams.search_results import SearchResultsRowStream
from cellar.application.export.start_export import StartExport
from cellar.application.research_organization.execute_search import ExecuteSearch
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.export.repository import ExportJobRepository
from cellar.infrastructure.persistence.sqlalchemy.export.export_job_repository import (
    SqlAlchemyExportJobRepository,
)
from cellar.infrastructure.storage.fsspec_client import FsspecStorageClient
from cellar.infrastructure.temporal.orchestrators.export import (
    NullExportOrchestrator,
    TemporalExportOrchestrator,
)


def register_export(container: Container) -> None:
    container[ExportJobRepository] = lambda c: SqlAlchemyExportJobRepository(c[UnitOfWork])
    container[FsspecStorageClient] = lambda c: FsspecStorageClient()

    def _build_search_stream(c: Container):
        from cellar.application.chemical_registration.protocols import ProtocolsReader
        return lambda job: SearchResultsRowStream(
            workspace_id=job.workspace_id,
            payload=job.query_snapshot,
            execute_search=c[ExecuteSearch],
            protocols_reader=c.resolve(ProtocolsReader) if ProtocolsReader in c else _no_protocols,
            requested_by=job.requested_by,
        )
    async def _no_protocols(_ws):
        return []
    container[RenderExport] = lambda c: RenderExport(
        uow=c[UnitOfWork],
        repo=c[ExportJobRepository],
        storage=c[FsspecStorageClient],
        build_search_stream=_build_search_stream(c),
    )

    if os.environ.get("TEMPORAL_DISABLED") == "1":
        container[ExportOrchestrator] = lambda c: NullExportOrchestrator(c[RenderExport])
    else:
        from cellar.infrastructure.temporal.client import get_temporal_client
        container[ExportOrchestrator] = lambda c: TemporalExportOrchestrator(get_temporal_client())

    container[StartExport] = lambda c: StartExport(c[UnitOfWork], c[ExportJobRepository], c[ExportOrchestrator])
    container[GetExportStatus] = lambda c: GetExportStatus(c[UnitOfWork], c[ExportJobRepository])
    container[CancelExport] = lambda c: CancelExport(c[UnitOfWork], c[ExportJobRepository], c[ExportOrchestrator])
    container[ListExports] = lambda c: ListExports(c[UnitOfWork], c[ExportJobRepository])
    container[PurgeExpiredExports] = lambda c: PurgeExpiredExports(c[UnitOfWork], c[ExportJobRepository], c[FsspecStorageClient])
```

> Match the resolve-style of `_research_organization.py` if Lagom's syntax differs. The `_no_protocols` shim is in case the project's `ProtocolsReader` Protocol lives elsewhere — replace with the right reader binding once verified.

- [ ] **Step 2: Commit**

```bash
git add backend/src/cellar/infrastructure/di/_export.py
git commit -m "feat(di): wire export use cases + orchestrator + render runner"
```

---

## Task 15: REST routes + FastAPI deps

**Files:**
- Modify: `backend/src/cellar/interface/routes/export.py` (extend existing file)
- Create: `backend/src/cellar/interface/dependencies/_export.py`
- Modify: `backend/src/cellar/interface/dependencies/__init__.py`
- Create: `backend/tests/api/test_export_routes.py`

- [ ] **Step 1: Deps**

```python
# backend/src/cellar/interface/dependencies/_export.py
from __future__ import annotations
from typing import Annotated

from fastapi import Depends

from cellar.application.export.cancel_export import CancelExport
from cellar.application.export.get_export_status import GetExportStatus
from cellar.application.export.list_exports import ListExports
from cellar.application.export.start_export import StartExport
from cellar.infrastructure.di.container import container
from cellar.infrastructure.storage.fsspec_client import FsspecStorageClient

StartExportDep = Annotated[StartExport, Depends(lambda: container[StartExport])]
GetExportStatusDep = Annotated[GetExportStatus, Depends(lambda: container[GetExportStatus])]
CancelExportDep = Annotated[CancelExport, Depends(lambda: container[CancelExport])]
ListExportsDep = Annotated[ListExports, Depends(lambda: container[ListExports])]
StorageDep = Annotated[FsspecStorageClient, Depends(lambda: container[FsspecStorageClient])]
```

Export from `dependencies/__init__.py`.

- [ ] **Step 2: Routes**

Replace `backend/src/cellar/interface/routes/export.py` body with:

```python
"""Unified export endpoints (CSV / SDF / XLSX / PDF) — and the legacy
/molecules/export/sdf shim that now points at the unified pipeline."""

from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from cellar.application.export.cancel_export import CancelExportCommand
from cellar.application.export.get_export_status import GetExportStatusQuery
from cellar.application.export.list_exports import ListExportsQuery
from cellar.application.export.start_export import StartExportCommand
from cellar.domain.export.enums import ExportFormat, ExportSource, ExportStatus
from cellar.interface.dependencies import AuthDep
from cellar.interface.dependencies._export import (
    CancelExportDep, GetExportStatusDep, ListExportsDep, StartExportDep, StorageDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/exports", tags=["export"])


class StartExportBody(BaseModel):
    source: ExportSource = Field(default=ExportSource.SEARCH)
    format: ExportFormat
    filename_hint: str | None = None
    payload: dict[str, Any]


class StartExportResponse(BaseModel):
    job_id: uuid.UUID


class ExportStatusResponse(BaseModel):
    id: uuid.UUID
    status: ExportStatus
    format: ExportFormat
    row_count: int | None
    progress: float | None
    error_message: str | None
    download_url: str | None
    byte_size: int | None
    filename: str | None
    requested_at: datetime
    completed_at: datetime | None
    expires_at: datetime | None


@router.post("", response_model=StartExportResponse, status_code=202)
async def start_export(body: StartExportBody, auth: AuthDep, uc: StartExportDep) -> StartExportResponse:
    res = await uc(StartExportCommand(
        workspace_id=auth.workspace_id,
        requested_by=auth.user_id,
        source=body.source,
        format=body.format,
        payload=body.payload,
        filename_hint=body.filename_hint,
    ), auth=auth)
    out = result_to_response(res)
    return StartExportResponse(job_id=out.job_id)


@router.get("/{job_id}", response_model=ExportStatusResponse)
async def get_export(job_id: uuid.UUID, auth: AuthDep, uc: GetExportStatusDep) -> ExportStatusResponse:
    res = await uc(GetExportStatusQuery(workspace_id=auth.workspace_id, job_id=job_id), auth=auth)
    view = result_to_response(res)
    return ExportStatusResponse(**view.__dict__)


@router.post("/{job_id}/cancel", status_code=204)
async def cancel_export(job_id: uuid.UUID, auth: AuthDep, uc: CancelExportDep) -> Response:
    res = await uc(CancelExportCommand(workspace_id=auth.workspace_id, job_id=job_id), auth=auth)
    result_to_response(res)
    return Response(status_code=204)


@router.get("", response_model=list[ExportStatusResponse])
async def list_exports(
    auth: AuthDep,
    uc: ListExportsDep,
    limit: int = Query(50, ge=1, le=200),
) -> list[ExportStatusResponse]:
    res = await uc(ListExportsQuery(workspace_id=auth.workspace_id, limit=limit), auth=auth)
    views = result_to_response(res)
    return [ExportStatusResponse(**v.__dict__) for v in views]


@router.get("/{job_id}/download")
async def download_export(
    job_id: uuid.UUID,
    auth: AuthDep,
    status_uc: GetExportStatusDep,
    storage: StorageDep,
) -> Response:
    res = await status_uc(GetExportStatusQuery(workspace_id=auth.workspace_id, job_id=job_id), auth=auth)
    view = result_to_response(res)
    if view.status == ExportStatus.EXPIRED:
        raise HTTPException(410, "Export expired — re-export the same query.")
    if view.status != ExportStatus.READY:
        raise HTTPException(409, f"Export not ready (status={view.status}).")

    # Re-read job for the file_key (status view doesn't carry it for security).
    from cellar.infrastructure.di.container import container
    from cellar.domain.export.repository import ExportJobRepository
    repo = container[ExportJobRepository]
    job = await repo.find_by_id_in_workspace(auth.workspace_id, job_id)
    if not job or not job.file_key:
        raise HTTPException(404, "Export file missing.")

    data = await storage.download(job.file_key)
    return Response(
        content=data,
        media_type=job.content_type or view.format.media_type,
        headers={"Content-Disposition": f'attachment; filename="{job.filename}"'},
    )


# Legacy shim — kept for one release so existing FE callers don't 404.
legacy_router = APIRouter(prefix="/api/v1/molecules/export", tags=["export-legacy"])


@legacy_router.post("/sdf", status_code=410)
async def legacy_sdf_export() -> Response:
    return Response(
        status_code=410,
        content=b'{"detail":"Use POST /api/v1/exports with format=sdf, source=search."}',
        media_type="application/json",
    )
```

> Wire `legacy_router` in the FastAPI app's router list alongside the existing routers. The 410 returns force the FE to migrate.

- [ ] **Step 3: API test**

```python
# backend/tests/api/test_export_routes.py
import pytest


@pytest.mark.asyncio
async def test_start_export_returns_job_id(api_client, auth_headers):
    res = await api_client.post(
        "/api/v1/exports",
        json={"format": "csv", "payload": {"query": {"criteria": []}, "protocol_columns": []}},
        headers=auth_headers,
    )
    assert res.status_code == 202
    body = res.json()
    assert "job_id" in body


@pytest.mark.asyncio
async def test_get_export_404_on_unknown_id(api_client, auth_headers):
    res = await api_client.get(
        "/api/v1/exports/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_legacy_sdf_returns_410(api_client, auth_headers):
    res = await api_client.post(
        "/api/v1/molecules/export/sdf",
        json={"molecule_ids": []},
        headers=auth_headers,
    )
    assert res.status_code == 410
```

> The `api_client` + `auth_headers` fixtures are conventional in this repo — check `backend/tests/api/conftest.py`.

- [ ] **Step 4: Run all backend tests**

Run: `cd backend && uv run pytest tests/unit/ tests/integration/ tests/api/test_export_routes.py -x`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/interface/routes/export.py backend/src/cellar/interface/dependencies/_export.py backend/src/cellar/interface/dependencies/__init__.py backend/tests/api/test_export_routes.py
git commit -m "feat(api): /api/v1/exports endpoints + legacy SDF 410 shim"
```

---

## Task 16: Regenerate orval client

**Files:**
- Modify: generated `frontend/src/shared/lib/api/generated/*` (orval output)

- [ ] **Step 1: Regenerate orval**

Run: `cd frontend && pnpm orval`
Expected: new `useStartExport`, `useGetExport`, `useListExports`, `useCancelExport` hooks (or the underlying axios functions if hooks aren't requested in `orval.config.ts`).

- [ ] **Step 2: Commit**

```bash
git add frontend/src/shared/lib/api/generated/
git commit -m "chore(api): regenerate orval client for /api/v1/exports"
```

---

# Wave 5 — Frontend shared

## Task 17: Types + `useExport` hook

**Files:**
- Create: `frontend/src/shared/components/export/types.ts`
- Create: `frontend/src/shared/components/export/use-export.ts`
- Create: `frontend/src/shared/components/export/use-export.test.ts`

- [ ] **Step 1: Types**

```ts
// frontend/src/shared/components/export/types.ts
export type ExportFormat = "csv" | "sdf" | "xlsx" | "pdf";
export type ExportSource = "search";
export type ExportStatus =
  | "pending" | "running" | "ready" | "failed"
  | "cancel_requested" | "cancelled" | "expired";

export interface ExportRequest {
  source: ExportSource;
  format: ExportFormat;
  filename_hint?: string;
  payload: Record<string, unknown>;
}

export interface ExportJob {
  id: string;
  status: ExportStatus;
  format: ExportFormat;
  row_count: number | null;
  progress: number | null;
  error_message: string | null;
  download_url: string | null;
  byte_size: number | null;
  filename: string | null;
  requested_at: string;
  completed_at: string | null;
  expires_at: string | null;
}
```

- [ ] **Step 2: Hook test**

```ts
// frontend/src/shared/components/export/use-export.test.ts
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactNode } from "react";

import { useExport } from "./use-export";

const wrapper = ({ children }: { children: ReactNode }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
};

beforeEach(() => {
  vi.useFakeTimers();
  global.fetch = vi.fn();
});
afterEach(() => vi.useRealTimers());

describe("useExport", () => {
  it("starts then polls until ready", async () => {
    (global.fetch as any)
      .mockResolvedValueOnce({ ok: true, status: 202, json: async () => ({ job_id: "j1" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({
        id: "j1", status: "running", progress: 0.3, format: "csv",
        row_count: 100, error_message: null, download_url: null,
        byte_size: null, filename: "x.csv", requested_at: "", completed_at: null, expires_at: null,
      })})
      .mockResolvedValueOnce({ ok: true, json: async () => ({
        id: "j1", status: "ready", progress: 1.0, format: "csv",
        row_count: 100, error_message: null, download_url: "/api/v1/exports/j1/download",
        byte_size: 1234, filename: "x.csv", requested_at: "", completed_at: "", expires_at: "",
      })});

    const { result } = renderHook(() => useExport(), { wrapper });
    act(() => { result.current.start({ source: "search", format: "csv", payload: {} }); });
    await vi.advanceTimersByTimeAsync(2000);
    await waitFor(() => expect(result.current.job?.status).toBe("ready"));
  });
});
```

- [ ] **Step 3: Hook impl**

```ts
// frontend/src/shared/components/export/use-export.ts
"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { ExportRequest, ExportJob } from "./types";

interface UseExportReturn {
  start: (req: ExportRequest) => Promise<string>;
  cancel: () => Promise<void>;
  reset: () => void;
  job: ExportJob | null;
  isPending: boolean;
  error: string | null;
}

export function useExport(): UseExportReturn {
  const [job, setJob] = useState<ExportJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancelled = useRef(false);

  const stop = useCallback(() => {
    if (pollTimer.current) {
      clearTimeout(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  const poll = useCallback(async (jobId: string, attempt = 0) => {
    if (cancelled.current) return;
    try {
      const next = await customInstance<ExportJob>({
        url: `/api/v1/exports/${jobId}`,
        method: "GET",
      });
      setJob(next);
      if (next.status === "ready") {
        triggerDownload(next);
        return;
      }
      if (["failed", "cancelled", "expired"].includes(next.status)) {
        setError(next.error_message ?? next.status);
        return;
      }
      const delay = attempt < 6 ? 500 : 2000;
      pollTimer.current = setTimeout(() => void poll(jobId, attempt + 1), delay);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  const start = useCallback(async (req: ExportRequest) => {
    setError(null);
    setJob(null);
    cancelled.current = false;
    const resp = await customInstance<{ job_id: string }>({
      url: "/api/v1/exports",
      method: "POST",
      data: req,
    });
    void poll(resp.job_id);
    return resp.job_id;
  }, [poll]);

  const cancel = useCallback(async () => {
    if (!job?.id) return;
    cancelled.current = true;
    stop();
    await customInstance<void>({
      url: `/api/v1/exports/${job.id}/cancel`,
      method: "POST",
    });
  }, [job, stop]);

  const reset = useCallback(() => {
    cancelled.current = true;
    stop();
    setJob(null);
    setError(null);
  }, [stop]);

  useEffect(() => () => stop(), [stop]);

  return {
    start, cancel, reset, job,
    isPending: !!job && !["ready", "failed", "cancelled", "expired"].includes(job.status),
    error,
  };
}

function triggerDownload(job: ExportJob) {
  if (!job.download_url || !job.filename) return;
  const a = document.createElement("a");
  a.href = job.download_url;
  a.download = job.filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}
```

- [ ] **Step 4: Run tests**

Run: `cd frontend && pnpm test src/shared/components/export/use-export.test.ts`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/shared/components/export/{types.ts,use-export.ts,use-export.test.ts}
git commit -m "feat(export): useExport hook + types (poll → trigger download)"
```

---

## Task 18: `ExportToolbar` (shared) + `ExportJobToast`

**Files:**
- Create: `frontend/src/shared/components/export/export-toolbar.tsx`
- Create: `frontend/src/shared/components/export/export-job-toast.tsx`
- Create: `frontend/src/shared/components/export/export-toolbar.test.tsx`

- [ ] **Step 1: Toolbar**

```tsx
// frontend/src/shared/components/export/export-toolbar.tsx
"use client";
import { ChevronDown, Download, Loader2 } from "lucide-react";

import { Button } from "@/shared/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";
import { useExport } from "./use-export";
import { ExportJobToast } from "./export-job-toast";
import type { ExportFormat, ExportRequest } from "./types";

const ITEMS: { format: ExportFormat; label: string; extension: string }[] = [
  { format: "xlsx", label: "Excel", extension: ".xlsx" },
  { format: "csv", label: "CSV", extension: ".csv" },
  { format: "sdf", label: "SDF", extension: ".sdf" },
  { format: "pdf", label: "PDF", extension: ".pdf" },
];

interface Props {
  buildRequest: (format: ExportFormat) => ExportRequest | null;
}

export function ExportToolbar({ buildRequest }: Props) {
  const exp = useExport();

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm" disabled={exp.isPending}>
            {exp.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            Export
            <ChevronDown className="ml-1 size-3 opacity-60" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-[10rem]">
          {ITEMS.map((it) => (
            <DropdownMenuItem
              key={it.format}
              onSelect={() => {
                const req = buildRequest(it.format);
                if (req) void exp.start(req);
              }}
            >
              <span>{it.label}</span>
              <span className="ml-auto text-[11px] tracking-wide text-muted-foreground">{it.extension}</span>
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      <ExportJobToast job={exp.job} error={exp.error} onCancel={exp.cancel} onDismiss={exp.reset} />
    </>
  );
}
```

- [ ] **Step 2: Toast**

```tsx
// frontend/src/shared/components/export/export-job-toast.tsx
"use client";
import { useEffect } from "react";
import { toast } from "sonner";
import type { ExportJob } from "./types";

interface Props {
  job: ExportJob | null;
  error: string | null;
  onCancel: () => void;
  onDismiss: () => void;
}

export function ExportJobToast({ job, error, onCancel, onDismiss }: Props) {
  useEffect(() => {
    if (!job && !error) return;
    if (error) {
      toast.error(`Export failed: ${error}`, { id: "export-job", onDismiss });
      return;
    }
    if (!job) return;
    const pct = job.progress != null ? Math.round(job.progress * 100) : null;
    const label = pct != null ? ` (${pct}%)` : "";
    if (job.status === "ready") {
      toast.success(`Exported ${formatBytes(job.byte_size)} — ${job.filename}`, {
        id: "export-job", duration: 30_000, onDismiss,
      });
    } else if (["pending", "running"].includes(job.status)) {
      toast.loading(`Exporting${label}…`, {
        id: "export-job", duration: Infinity,
        action: { label: "Cancel", onClick: onCancel },
      });
    } else if (job.status === "cancelled") {
      toast(`Export cancelled`, { id: "export-job", onDismiss });
    }
  }, [job, error, onCancel, onDismiss]);
  return null;
}

function formatBytes(n: number | null): string {
  if (!n) return "—";
  const u = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(1)} ${u[i]}`;
}
```

- [ ] **Step 3: Component test**

```tsx
// frontend/src/shared/components/export/export-toolbar.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ExportToolbar } from "./export-toolbar";

vi.mock("./use-export", () => ({
  useExport: () => ({
    start: vi.fn(),
    cancel: vi.fn(),
    reset: vi.fn(),
    job: null,
    isPending: false,
    error: null,
  }),
}));

const wrapper = ({ children }: any) => (
  <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
);

describe("ExportToolbar", () => {
  it("renders four format options", () => {
    render(<ExportToolbar buildRequest={() => null} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Export/i }));
    expect(screen.getByText("Excel")).toBeInTheDocument();
    expect(screen.getByText("CSV")).toBeInTheDocument();
    expect(screen.getByText("SDF")).toBeInTheDocument();
    expect(screen.getByText("PDF")).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: Run tests**

Run: `cd frontend && pnpm test src/shared/components/export/`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/shared/components/export/{export-toolbar.tsx,export-job-toast.tsx,export-toolbar.test.tsx}
git commit -m "feat(export): shared ExportToolbar + Sonner progress toast"
```

---

# Wave 6 — Search wiring + cleanup

## Task 19: Wire `/search` to the new toolbar; remove old SDF wiring

**Files:**
- Modify: `frontend/src/features/research-organization/components/search-page.tsx`
- Modify: `frontend/src/features/research-organization/components/search/results-grid.tsx`

- [ ] **Step 1: Edit search-page.tsx**

Remove the `useSdfExport` import + `handleExportSdf` callback. Add a `buildExportRequest`:

```ts
import { ExportToolbar } from "@/shared/components/export/export-toolbar";
import type { ExportRequest, ExportFormat } from "@/shared/components/export/types";

// inside SearchPageInner, after `currentQuery` is in scope:
const buildExportRequest = useCallback(
  (format: ExportFormat): ExportRequest | null => {
    if (!currentQuery) return null;
    const backendCols = toBackendProtocolColumns(protocolColumns);
    return {
      source: "search",
      format,
      filename_hint: `cellar-search-${new Date().toISOString().slice(0, 10)}`,
      payload: {
        query: currentQuery,
        ...(backendCols.length ? { protocol_columns: backendCols } : {}),
        aggregation: aggregationModeToWire(aggregationMode),
        ...(projectIds.length ? { project_ids: projectIds } : {}),
        sort_by: sortBy,
        sort_dir: sortDir,
      },
    };
  },
  [currentQuery, protocolColumns, aggregationMode, projectIds, sortBy, sortDir],
);
```

Drop `onExportSdf={handleExportSdf}` from the `<ResultsGrid>` props; pass `buildExportRequest` through to the grid via a new prop.

- [ ] **Step 2: Edit results-grid.tsx**

Replace the `onExportSdf?` prop with `buildExportRequest?: (format: ExportFormat) => ExportRequest | null`. Pass it to `<DataGrid>` as `exportRequest={buildExportRequest}` (see Task 20 for the DataGrid prop change).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/research-organization/components/search-page.tsx frontend/src/features/research-organization/components/search/results-grid.tsx
git commit -m "feat(search): wire new ExportToolbar — exports run server-side over full result set"
```

---

## Task 20: Replace DataGrid's old export plumbing with `exportRequest`

**Files:**
- Modify: `frontend/src/shared/components/data-grid/data-grid.tsx`
- Delete: `frontend/src/shared/components/data-grid/export-toolbar.tsx`

- [ ] **Step 1: Replace props**

In `data-grid.tsx`, drop `exportFilename`, `excelEnhancer`, `extraExportItems` from the interface and the toolbar JSX. Add:

```ts
import { ExportToolbar } from "@/shared/components/export/export-toolbar";
import type { ExportRequest, ExportFormat } from "@/shared/components/export/types";
...
exportRequest?: (format: ExportFormat) => ExportRequest | null;
```

Replace the toolbar block:
```tsx
{exportRequest ? <ExportToolbar buildRequest={exportRequest} /> : null}
```

Remove the `ExcelEnhancer` re-export.

- [ ] **Step 2: Delete the old toolbar file**

```bash
rm frontend/src/shared/components/data-grid/export-toolbar.tsx
```

- [ ] **Step 3: TypeScript + tests pass**

Run: `cd frontend && pnpm exec tsc --noEmit && pnpm test`
Expected: clean (any other grid still calling the old props will surface here — port each to the new prop or pass nothing).

- [ ] **Step 4: Commit**

```bash
git add -A frontend/src/shared/components/data-grid/
git commit -m "refactor(data-grid): drop FE-only export toolbar in favor of shared BE-driven one"
```

---

## Task 21: Browser smoke + push

- [ ] **Step 1: Dev stack up**

```bash
docker compose up -d
cd frontend && pnpm dev
```

- [ ] **Step 2: Smoke checklist**

| Scenario | Expected |
|---|---|
| Search returns 50 mols → Export → CSV | Toast spins ~1 s; .csv downloads; opens cleanly; numbers are numbers; ND for inactive intercepts. |
| Same search → Export → SDF | .sdf opens in any chemistry viewer; each entry has `> <Mtb_WCA::EC50>` tags. |
| Same search → Export → Excel | .xlsx opens in Excel; numeric cells are right-aligned; sparkline images appear in the Plot column (≤5K rows). |
| Same search → Export → PDF | .pdf opens; landscape; query summary + footer page numbers visible. |
| Search returns 2,500 mols → Excel | Progress toast climbs to 100%; file ~10–25 MB; opens. |
| Search returns 10,000 mols → PDF | Job marks `failed` with `"exceeds 5000 cap"` toast. |
| Click Cancel mid-export | Toast switches to "cancelled". |
| Close browser tab mid-export, re-open, re-poll via dev tools | Job still completes server-side. |

- [ ] **Step 3: Push**

```bash
git push origin prot-2
```

- [ ] **Step 4: Update CLAUDE.md handoff section**

Add a `### 2026-05-16 — Unified export shipped on prot-2` block summarizing the commits + smoke results.

- [ ] **Step 5: Commit handoff**

```bash
git add CLAUDE.md
git commit -m "docs: handoff — unified export shipped on prot-2"
git push
```

---

## Out-of-scope (post-merge follow-ups)

- Port runs grid / batches grid / activity / collection grids to the new toolbar (each its own PR).
- "Recent exports" tray UI consuming `GET /api/v1/exports`.
- S3 / MinIO swap of fsspec.
- Per-format permission gates in workspace config.
- Scheduled purge — wire `PurgeExpiredExports` into a Temporal scheduled workflow (today's plan ships the use case; the schedule wires later).
