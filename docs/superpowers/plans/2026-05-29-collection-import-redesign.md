# Collection Import Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace today's rudimentary `identifier,type` CSV with a 4-step wizard (Upload → Mapping → Preview → Confirm) that has synonym-based header auto-detection, saved mapping templates, per-row outcome classification, and a clean handoff to the existing bulk-register wizard for unregistered molecules.

**Architecture:** Backend `BulkAddToCollection` use case wraps the existing `MoleculeResolver` (find-only, no registration). Workspace-scoped `CollectionImportTemplate` aggregate mirrors `RunImportTemplate` 1:1. Preview returns per-row outcomes with status enum + counts + a short-lived `preview_id` stash of unmatched rows. Register-wizard handoff via query params: bulk-register page reads the stash, chemist fills org/scientist/source on the existing screens, success step routes back to the collection with a one-click "add these newly-registered molecules" CTA.

**Tech Stack:** Python 3.13 + FastAPI + SQLAlchemy 2.0 async + Pydantic v2 + dry-python/returns; Next.js 16 + React Hook Form + Zod + papaparse + TanStack Query.

**Branch:** continue on `prot-2`. Rides on top of all the un-pushed work from May.

**Spec:** `docs/superpowers/specs/2026-05-29-collection-import-redesign.md`

---

## File Structure

**New backend files:**

| Path | Responsibility |
|---|---|
| `backend/src/cellar/domain/research_organization/collection_import_template.py` | `CollectionImportTemplate` aggregate |
| `backend/src/cellar/domain/research_organization/bulk_add_types.py` | `BulkAddRow`, `RowStatus`, `RowOutcome`, `BulkAddResult` |
| `backend/src/cellar/application/research_organization/bulk_add_to_collection.py` | Use case + Command + preview-id stash |
| `backend/src/cellar/application/research_organization/collection_import_mapping.py` | Synonym-based header detection |
| `backend/src/cellar/application/research_organization/collection_import_templates.py` | Template CRUD use cases + scoring helper |
| `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/collection_import_template_repository.py` | SQLAlchemy repo |
| `backend/alembic/versions/045_collection_import_templates.py` | Migration |
| `backend/src/cellar/interface/routes/collection_import_templates.py` | Template CRUD endpoints |

**Modified backend files:**

| Path | What changes |
|---|---|
| `backend/src/cellar/domain/research_organization/repository.py` | Add `CollectionImportTemplateRepository` protocol |
| `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/models.py` | Add `CollectionImportTemplateModel` |
| `backend/src/cellar/infrastructure/di/_research_organization.py` | Wire new use cases + repo + stash |
| `backend/src/cellar/interface/dependencies/_research_organization.py` | Add deps for new use cases |
| `backend/src/cellar/interface/routes/collections.py` | Add `preview-bulk`, `bulk`, and `unregistered-rows/{preview_id}` endpoints |

**New frontend files:**

| Path | Responsibility |
|---|---|
| `frontend/src/app/(dashboard)/collections/[id]/import/page.tsx` | Wizard page route |
| `frontend/src/features/research-organization/components/collection-import-wizard/index.tsx` | 4-step wizard composer |
| `frontend/src/features/research-organization/components/collection-import-wizard/upload-step.tsx` | Step 1 |
| `frontend/src/features/research-organization/components/collection-import-wizard/mapping-step.tsx` | Step 2 |
| `frontend/src/features/research-organization/components/collection-import-wizard/preview-step.tsx` | Step 3 |
| `frontend/src/features/research-organization/components/collection-import-wizard/confirm-step.tsx` | Step 4 |
| `frontend/src/features/research-organization/lib/parse-collection-import-csv.ts` | CSV parsing + template generator |
| `frontend/src/features/research-organization/hooks/use-collection-import-wizard.ts` | Wizard state machine |
| `frontend/src/features/research-organization/hooks/use-preview-collection-import.ts` | TanStack mutation |
| `frontend/src/features/research-organization/hooks/use-commit-collection-import.ts` | TanStack mutation |
| `frontend/src/features/research-organization/hooks/use-collection-import-templates.ts` | Template CRUD hooks |

**Modified frontend files:**

| Path | What changes |
|---|---|
| `frontend/src/features/research-organization/components/collection-detail.tsx` | Add "Bulk import" header button → routes to `/collections/{id}/import` |
| `frontend/src/features/chemical-registration/components/registration-wizard/index.tsx` (or wherever the wizard composer lives) | Branch on `from_collection_import` URL param — pre-fill input step from stash |
| `frontend/src/features/chemical-registration/components/registration-wizard/step-summary.tsx` | Add "Add to {collection_name}" CTA when `return_to_collection` present |

---

## Conventions

- **TDD** for every backend code task. Failing test first, verify failure, implement, verify pass, commit.
- **Commit style:** `<type>(<scope>): <short imperative>`.
- **CSV template** (downloadable from the wizard's Upload step):
  ```csv
  registration_number,external_id,smiles,inchi_key,name,notes
  CC-000001,,,,,
  ,ACME-LOT-42,,,,partner sample
  ,,c1ccccc1O,,phenol,
  ```
- **Per-row outcomes** (5 statuses on `RowOutcome.status`):
  - `resolved` — molecule found in the workspace; will be added
  - `already_present` — molecule found AND already a member; no-op
  - `unregistered` — has SMILES or name/identifier but no match found; eligible for handoff
  - `ambiguous` — multiple molecules match (e.g. name "aspirin" hits 2); chemist picks
  - `error` — no usable identifier (empty row or only `notes`)
- **Preview-id stash:** in-memory dict on the use case singleton, 30-min TTL. Single-process app — DB-backed stash deferred until horizontal scaling matters.
- **Header roles** (synonym dictionary keys): `registration_number`, `external_id`, `inchi_key`, `smiles`, `name`, `notes`. All optional in the mapping — preview validates "at least one identifier column mapped" before showing outcomes.

---

# Tasks

## Task 1: Domain types for bulk-add

**Files:**
- Create: `backend/src/cellar/domain/research_organization/bulk_add_types.py`
- Create: `backend/tests/unit/domain/research_organization/test_bulk_add_types.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/domain/research_organization/test_bulk_add_types.py
import uuid

from cellar.domain.research_organization.bulk_add_types import (
    BulkAddRow,
    BulkAddResult,
    RowOutcome,
    RowStatus,
)


def test_bulk_add_row_carries_optional_identifiers():
    row = BulkAddRow(
        row_index=3,
        registration_number="CC-000001",
        smiles="c1ccccc1O",
        name="phenol",
    )
    assert row.row_index == 3
    assert row.external_id is None
    assert row.notes is None


def test_bulk_add_result_aggregates_counts_from_outcomes():
    mol_id = uuid.uuid4()
    outcomes = [
        RowOutcome(row_index=0, status=RowStatus.RESOLVED, molecule_id=mol_id),
        RowOutcome(row_index=1, status=RowStatus.ALREADY_PRESENT, molecule_id=mol_id),
        RowOutcome(row_index=2, status=RowStatus.UNREGISTERED, message="not found"),
        RowOutcome(row_index=3, status=RowStatus.AMBIGUOUS, candidates=[uuid.uuid4()]),
        RowOutcome(row_index=4, status=RowStatus.ERROR, message="no usable identifier"),
    ]
    result = BulkAddResult.from_outcomes(outcomes)
    assert result.resolved_count == 1
    assert result.already_present_count == 1
    assert result.unregistered_count == 1
    assert result.ambiguous_count == 1
    assert result.error_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/domain/research_organization/test_bulk_add_types.py -v`
Expected: ImportError for `bulk_add_types`.

- [ ] **Step 3: Write the module**

```python
# backend/src/cellar/domain/research_organization/bulk_add_types.py
"""Per-row inputs + outcomes for the BulkAddToCollection use case."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum


class RowStatus(str, Enum):
    RESOLVED = "resolved"
    ALREADY_PRESENT = "already_present"
    UNREGISTERED = "unregistered"
    AMBIGUOUS = "ambiguous"
    ERROR = "error"


@dataclass(frozen=True, kw_only=True)
class BulkAddRow:
    """One CSV row, after the FE has applied the chemist's column mapping."""

    row_index: int
    registration_number: str | None = None
    external_id: str | None = None
    inchi_key: str | None = None
    smiles: str | None = None
    name: str | None = None
    notes: str | None = None

    def has_identifier(self) -> bool:
        return any(
            (
                self.registration_number,
                self.external_id,
                self.inchi_key,
                self.smiles,
                self.name,
            )
        )


@dataclass(frozen=True, kw_only=True)
class RowOutcome:
    row_index: int
    status: RowStatus
    molecule_id: uuid.UUID | None = None
    molecule_name: str | None = None
    candidates: list[uuid.UUID] = field(default_factory=list)
    message: str | None = None


@dataclass(frozen=True, kw_only=True)
class BulkAddResult:
    outcomes: list[RowOutcome]
    resolved_count: int
    already_present_count: int
    unregistered_count: int
    ambiguous_count: int
    error_count: int
    preview_id: uuid.UUID | None = None

    @classmethod
    def from_outcomes(
        cls,
        outcomes: list[RowOutcome],
        *,
        preview_id: uuid.UUID | None = None,
    ) -> BulkAddResult:
        counts = {s: 0 for s in RowStatus}
        for o in outcomes:
            counts[o.status] += 1
        return cls(
            outcomes=outcomes,
            resolved_count=counts[RowStatus.RESOLVED],
            already_present_count=counts[RowStatus.ALREADY_PRESENT],
            unregistered_count=counts[RowStatus.UNREGISTERED],
            ambiguous_count=counts[RowStatus.AMBIGUOUS],
            error_count=counts[RowStatus.ERROR],
            preview_id=preview_id,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/domain/research_organization/test_bulk_add_types.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/domain/research_organization/bulk_add_types.py \
        backend/tests/unit/domain/research_organization/test_bulk_add_types.py
git commit -m "feat(research_org): bulk-add domain types (row + outcome + result)"
```

---

## Task 2: CollectionImportTemplate aggregate

**Files:**
- Create: `backend/src/cellar/domain/research_organization/collection_import_template.py`
- Modify: `backend/src/cellar/domain/research_organization/repository.py`
- Create: `backend/tests/unit/domain/research_organization/test_collection_import_template.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/domain/research_organization/test_collection_import_template.py
import uuid

import pytest

from cellar.domain.research_organization.collection_import_template import (
    CollectionImportTemplate,
)
from cellar.domain.shared.errors import ValidationError


def test_create_requires_name():
    with pytest.raises(ValidationError):
        CollectionImportTemplate.create(
            workspace_id=uuid.uuid4(),
            name="",
            column_mapping={"name": "Compound Name"},
            created_by=uuid.uuid4(),
        )


def test_create_requires_at_least_one_identifier_role():
    with pytest.raises(ValidationError):
        CollectionImportTemplate.create(
            workspace_id=uuid.uuid4(),
            name="Partner ACME",
            column_mapping={"notes": "Comments"},
            created_by=uuid.uuid4(),
        )


def test_update_changes_mapping_and_bumps_updated_at():
    tpl = CollectionImportTemplate.create(
        workspace_id=uuid.uuid4(),
        name="t1",
        column_mapping={"name": "Compound Name"},
        created_by=uuid.uuid4(),
    )
    original_updated = tpl.updated_at
    tpl.update(column_mapping={"name": "Compound", "smiles": "Structure"})
    assert tpl.column_mapping["smiles"] == "Structure"
    assert tpl.updated_at >= original_updated
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/domain/research_organization/test_collection_import_template.py -v`
Expected: ImportError.

- [ ] **Step 3: Write the aggregate**

```python
# backend/src/cellar/domain/research_organization/collection_import_template.py
"""CollectionImportTemplate — reusable column mapping for collection CSV imports.

Workspace-scoped. Stores which CSV header maps to which role
(registration_number / external_id / smiles / inchi_key / name / notes).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from cellar.domain.shared.entity import Entity
from cellar.domain.shared.errors import ValidationError

_UNSET: Any = object()

_IDENTIFIER_ROLES = frozenset(
    {"registration_number", "external_id", "inchi_key", "smiles", "name"}
)


class CollectionImportTemplate(Entity):
    """Saved column mapping for bulk-adding molecules to a collection."""

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        name: str,
        description: str | None = None,
        column_mapping: dict[str, str],
        created_by: uuid.UUID,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)
        self._validate_name(name)
        self._validate_mapping(column_mapping)
        self.workspace_id = workspace_id
        self.name = name.strip()
        self.description = description
        self.column_mapping = column_mapping
        self.created_by = created_by

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        name: str,
        column_mapping: dict[str, str],
        description: str | None = None,
        created_by: uuid.UUID,
    ) -> CollectionImportTemplate:
        return cls(
            workspace_id=workspace_id,
            name=name,
            description=description,
            column_mapping=column_mapping,
            created_by=created_by,
        )

    def update(
        self,
        *,
        name: str | None = None,
        description: Any = _UNSET,
        column_mapping: dict[str, str] | None = None,
    ) -> None:
        if name is not None:
            self._validate_name(name)
            self.name = name.strip()
        if description is not _UNSET:
            self.description = description
        if column_mapping is not None:
            self._validate_mapping(column_mapping)
            self.column_mapping = column_mapping
        self.updated_at = datetime.now(UTC)

    @staticmethod
    def _validate_name(name: str) -> None:
        if not name or not name.strip():
            raise ValidationError("CollectionImportTemplate name must not be empty")

    @staticmethod
    def _validate_mapping(mapping: dict[str, str]) -> None:
        if not any(role in mapping and mapping[role] for role in _IDENTIFIER_ROLES):
            raise ValidationError(
                "column_mapping must declare at least one identifier role "
                "(registration_number, external_id, inchi_key, smiles, or name)"
            )
```

- [ ] **Step 4: Add the repository protocol**

In `backend/src/cellar/domain/research_organization/repository.py`, add (find an appropriate location after existing repository protocols):

```python
from cellar.domain.research_organization.collection_import_template import (
    CollectionImportTemplate,
)


class CollectionImportTemplateRepository(Protocol):
    async def save(self, template: CollectionImportTemplate) -> None: ...

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, template_id: uuid.UUID
    ) -> CollectionImportTemplate | None: ...

    async def find_by_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[CollectionImportTemplate]: ...

    async def delete(
        self, workspace_id: uuid.UUID, template_id: uuid.UUID
    ) -> None: ...
```

(If the file uses `runtime_checkable` Protocol pattern on others, match it. Confirm `Protocol` and `uuid` are already imported; add if not.)

- [ ] **Step 5: Run tests**

Run: `cd backend && uv run pytest tests/unit/domain/research_organization/test_collection_import_template.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/domain/research_organization/collection_import_template.py \
        backend/src/cellar/domain/research_organization/repository.py \
        backend/tests/unit/domain/research_organization/test_collection_import_template.py
git commit -m "feat(research_org): CollectionImportTemplate aggregate + repo protocol"
```

---

## Task 3: Migration 045 — collection_import_templates table

**Files:**
- Create: `backend/alembic/versions/045_collection_import_templates.py`

- [ ] **Step 1: Write the migration**

```python
# backend/alembic/versions/045_collection_import_templates.py
"""045 — collection_import_templates table.

Workspace-scoped saved column mappings for the collection bulk-import
wizard. Shape mirrors run_import_templates (migration 016) but the
mapping payload's identifier roles are different.

Revision ID: 045_collection_import_templates
Revises: 044_batch_id_mirror_fk
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "045_collection_import_templates"
down_revision = "044_batch_id_mirror_fk"


def upgrade() -> None:
    op.create_table(
        "collection_import_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("column_mapping", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "name", name="uq_collection_import_template_ws_name"
        ),
    )
    op.create_index(
        "ix_collection_import_template_ws",
        "collection_import_templates",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_collection_import_template_ws",
        table_name="collection_import_templates",
    )
    op.drop_table("collection_import_templates")
```

- [ ] **Step 2: Run the migration against the dev DB**

Run: `cd backend && uv run alembic upgrade head`
Expected: log line about `045_collection_import_templates` applying cleanly.

- [ ] **Step 3: Verify the table**

Run: `cd backend && uv run python -c "from sqlalchemy import create_engine, inspect; from cellar.infrastructure.config import settings; e = create_engine(settings.database_url.replace('+asyncpg','')); print(inspect(e).has_table('collection_import_templates'))"`
Expected: `True`.

(If that one-liner doesn't fit the local config plumbing, fall back to `psql` and `\dt collection_import_templates`.)

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/045_collection_import_templates.py
git commit -m "feat(migration): 045 — collection_import_templates table"
```

---

## Task 4: SQLAlchemy model + repository

**Files:**
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/models.py`
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/collection_import_template_repository.py`
- Create: `backend/tests/integration/persistence/research_organization/test_collection_import_template_repository.py`

- [ ] **Step 1: Add the model**

Find the existing `models.py` in `infrastructure/persistence/sqlalchemy/research_organization/`. Append a model whose shape mirrors `RunImportTemplateModel` (see `infrastructure/persistence/sqlalchemy/screening_assay/models.py` for the exact pattern — JSONB column, `Mapped[]` typing):

```python
class CollectionImportTemplateModel(Base):
    __tablename__ = "collection_import_templates"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False, index=True)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    column_mapping: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "workspace_id", "name", name="uq_collection_import_template_ws_name"
        ),
    )
```

(Match `JSONB`, `Base`, `Mapped`, `mapped_column`, `datetime`, `uuid` import paths to what other models in this file use.)

- [ ] **Step 2: Write the failing repo integration test**

```python
# backend/tests/integration/persistence/research_organization/test_collection_import_template_repository.py
import uuid

import pytest

from cellar.domain.research_organization.collection_import_template import (
    CollectionImportTemplate,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.collection_import_template_repository import (
    SQLAlchemyCollectionImportTemplateRepository,
)


@pytest.mark.asyncio
async def test_save_and_find_by_workspace(db_session):
    repo = SQLAlchemyCollectionImportTemplateRepository(db_session)
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()
    tpl = CollectionImportTemplate.create(
        workspace_id=ws_id,
        name="Partner ACME",
        column_mapping={"registration_number": "Reg No.", "name": "Compound"},
        created_by=user_id,
    )
    await repo.save(tpl)
    await db_session.commit()

    found = await repo.find_by_workspace(ws_id)
    assert len(found) == 1
    assert found[0].name == "Partner ACME"


@pytest.mark.asyncio
async def test_update_persists_new_mapping(db_session):
    repo = SQLAlchemyCollectionImportTemplateRepository(db_session)
    ws_id = uuid.uuid4()
    tpl = CollectionImportTemplate.create(
        workspace_id=ws_id,
        name="t1",
        column_mapping={"name": "X"},
        created_by=uuid.uuid4(),
    )
    await repo.save(tpl)
    await db_session.commit()

    tpl.update(column_mapping={"name": "X", "smiles": "Structure"})
    await repo.save(tpl)
    await db_session.commit()

    reloaded = await repo.find_by_id_in_workspace(ws_id, tpl.id)
    assert reloaded is not None
    assert reloaded.column_mapping["smiles"] == "Structure"
```

(Match the `db_session` fixture name used by other integration tests in the same directory — see `tests/integration/persistence/` for the conftest convention.)

- [ ] **Step 3: Write the repository**

```python
# backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/collection_import_template_repository.py
"""SQLAlchemy repository for CollectionImportTemplate."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from cellar.domain.research_organization.collection_import_template import (
    CollectionImportTemplate,
)
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    EntityRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CollectionImportTemplateModel,
)


class SQLAlchemyCollectionImportTemplateRepository(
    EntityRepository[CollectionImportTemplate, CollectionImportTemplateModel]
):
    model_class = CollectionImportTemplateModel

    async def find_by_workspace(  # type: ignore[override]
        self, workspace_id: uuid.UUID
    ) -> list[CollectionImportTemplate]:
        stmt = (
            select(CollectionImportTemplateModel)
            .where(CollectionImportTemplateModel.workspace_id == workspace_id)
            .order_by(CollectionImportTemplateModel.name)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    def _to_domain(self, model: CollectionImportTemplateModel) -> CollectionImportTemplate:
        return CollectionImportTemplate(
            id=model.id,
            workspace_id=model.workspace_id,
            name=model.name,
            description=model.description,
            column_mapping=model.column_mapping,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: CollectionImportTemplate) -> CollectionImportTemplateModel:
        return CollectionImportTemplateModel(
            id=entity.id,
            workspace_id=entity.workspace_id,
            name=entity.name,
            description=entity.description,
            column_mapping=entity.column_mapping,
            created_by=entity.created_by,
        )

    def _update_model(
        self, model: CollectionImportTemplateModel, entity: CollectionImportTemplate
    ) -> None:
        model.name = entity.name
        model.description = entity.description
        model.column_mapping = entity.column_mapping
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && uv run pytest tests/integration/persistence/research_organization/test_collection_import_template_repository.py -v`
Expected: 2 passed (testcontainer Postgres).

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/ \
        backend/tests/integration/persistence/research_organization/test_collection_import_template_repository.py
git commit -m "feat(research_org): SQLAlchemy model + repo for CollectionImportTemplate"
```

---

## Task 5: Synonym-based header detection

**Files:**
- Create: `backend/src/cellar/application/research_organization/collection_import_mapping.py`
- Create: `backend/tests/unit/application/research_organization/test_collection_import_mapping.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/application/research_organization/test_collection_import_mapping.py
from cellar.application.research_organization.collection_import_mapping import (
    HeaderSuggestion,
    suggest_column_mapping,
)


def test_suggests_registration_number_for_canonical_synonyms():
    suggestions = suggest_column_mapping(
        ["Reg No.", "Compound Name", "Structure"]
    )
    by_header = {s.header: s for s in suggestions}
    assert by_header["Reg No."].role == "registration_number"
    assert by_header["Compound Name"].role == "name"
    assert by_header["Structure"].role == "smiles"


def test_unknown_header_yields_no_suggestion():
    suggestions = suggest_column_mapping(["Foo Bar Quux"])
    assert suggestions[0].role is None


def test_normalization_is_case_and_punctuation_insensitive():
    s = suggest_column_mapping(["INCHI_KEY"])[0]
    assert s.role == "inchi_key"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/application/research_organization/test_collection_import_mapping.py -v`
Expected: ImportError.

- [ ] **Step 3: Write the module**

```python
# backend/src/cellar/application/research_organization/collection_import_mapping.py
"""Synonym-based header → role suggestion for the collection-import wizard.

Mirrors the shape of `application/screening/long_format_normalizer.py`'s
synonym dictionary but covers the collection roles (no plate / well /
concentration / readout).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class HeaderSuggestion:
    header: str
    role: str | None
    reason: str


# role → list of normalized synonyms
_SYNONYMS: dict[str, list[str]] = {
    "registration_number": [
        "regno", "reg", "regnumber", "registrationnumber", "registration",
        "compoundid", "cellarid", "ccnumber", "ccno", "compoundnumber",
    ],
    "external_id": [
        "externalid", "vendorid", "vendorlot", "cas", "casnumber",
        "chemblid", "pubchemid", "suppliercode", "catalogno", "sku",
        "lotid", "lotnumber",
    ],
    "inchi_key": ["inchikey", "inchi"],
    "smiles": ["smiles", "canonicalsmiles", "structure", "molsmiles"],
    "name": [
        "name", "compoundname", "moleculename", "commonname", "title",
        "label", "compound",
    ],
    "notes": ["notes", "note", "comment", "comments", "description", "remark"],
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def suggest_column_mapping(headers: list[str]) -> list[HeaderSuggestion]:
    """Return one HeaderSuggestion per CSV header, in input order.

    `role` is None when no synonym matches; the FE renders these with an
    empty select that the chemist can set manually.
    """
    suggestions: list[HeaderSuggestion] = []
    for header in headers:
        normalized = _norm(header)
        matched_role: str | None = None
        for role, syns in _SYNONYMS.items():
            if normalized in syns:
                matched_role = role
                break
        suggestions.append(
            HeaderSuggestion(
                header=header,
                role=matched_role,
                reason="synonym match" if matched_role else "no match",
            )
        )
    return suggestions
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/application/research_organization/test_collection_import_mapping.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/application/research_organization/collection_import_mapping.py \
        backend/tests/unit/application/research_organization/test_collection_import_mapping.py
git commit -m "feat(research_org): synonym-based header detection for collection imports"
```

---

## Task 6: BulkAddToCollection use case + preview-id stash

**Files:**
- Create: `backend/src/cellar/application/research_organization/bulk_add_to_collection.py`
- Create: `backend/tests/unit/application/research_organization/test_bulk_add_to_collection.py`

- [ ] **Step 1: Read the existing seams**

Skim before writing:
- `backend/src/cellar/application/shared/molecule_resolver.py` — `MoleculeResolver.resolve(workspace_id, refs)` returns `(resolved: list[ResolvedMolecule], unresolved: list[UnresolvedMolecule])`. `MoleculeReference(value, ref_type=RefType)`. `RefType.SMILES` runs structure_processor → InChIKey lookup. Unresolved reason codes include `"not_found"`, `"ambiguous"`, `"invalid"`.
- `backend/src/cellar/application/research_organization/collection_membership.py` — for the pattern of "fetch collection → call `collection_repo.add_molecules(workspace_id, collection_id, ids)` → already-present count is `len(ids) - added`".

The new use case differs in three ways:
1. Builds refs per-row from the explicit field shape (BulkAddRow), not a flat list.
2. Classifies each row into one of 5 RowStatus values for richer reporting.
3. On dry_run with any UNREGISTERED rows, stashes the unmatched rows under a `preview_id` keyed in an in-memory dict on the use-case instance, 30-min TTL.

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/unit/application/research_organization/test_bulk_add_to_collection.py
import uuid
from dataclasses import dataclass

import pytest

from cellar.application.research_organization.bulk_add_to_collection import (
    BulkAddToCollection,
    BulkAddToCollectionCommand,
    StashedUnregisteredRows,
)
from cellar.application.shared.molecule_resolver import (
    MoleculeReference,
    ResolvedMolecule,
    UnresolvedMolecule,
)
from cellar.domain.research_organization.bulk_add_types import (
    BulkAddRow,
    RowStatus,
)
from cellar.domain.research_organization.enums import RefType
from cellar.domain.shared.errors import NotFoundError


@dataclass
class FakeResolver:
    """Stub: returns canned (resolved, unresolved) by reference value."""

    resolved_map: dict[str, uuid.UUID]
    ambiguous_values: set[str]

    async def resolve(self, workspace_id, refs):
        resolved, unresolved = [], []
        for r in refs:
            if r.value in self.resolved_map:
                resolved.append(
                    ResolvedMolecule(
                        ref=r,
                        molecule_id=self.resolved_map[r.value],
                        name=f"M-{r.value}",
                    )
                )
            elif r.value in self.ambiguous_values:
                unresolved.append(UnresolvedMolecule(ref=r, reason="ambiguous"))
            else:
                unresolved.append(UnresolvedMolecule(ref=r, reason="not_found"))
        return resolved, unresolved


@dataclass
class FakeCollectionRepo:
    members: set[uuid.UUID]
    collection_exists: bool = True

    async def find_by_id_in_workspace(self, ws, cid):
        return object() if self.collection_exists else None

    async def add_molecules(self, ws, cid, ids):
        new = [i for i in ids if i not in self.members]
        self.members.update(new)
        return len(new)

    async def list_member_ids(self, ws, cid):
        return list(self.members)


@dataclass
class FakeUoW:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return None
    async def commit(self): return []


@pytest.mark.asyncio
async def test_dry_run_classifies_all_five_statuses():
    existing = uuid.uuid4()
    already = uuid.uuid4()
    ambiguous_mol = uuid.uuid4()
    resolver = FakeResolver(
        resolved_map={"CC-000001": existing, "CC-000002": already},
        ambiguous_values={"aspirin"},
    )
    repo = FakeCollectionRepo(members={already})
    use_case = BulkAddToCollection(uow=FakeUoW(), resolver=resolver, repo=repo)

    rows = [
        BulkAddRow(row_index=0, registration_number="CC-000001"),   # resolved
        BulkAddRow(row_index=1, registration_number="CC-000002"),   # already_present
        BulkAddRow(row_index=2, smiles="c1ccccc1O"),                # unregistered
        BulkAddRow(row_index=3, name="aspirin"),                     # ambiguous
        BulkAddRow(row_index=4, notes="just a note"),                # error
    ]
    cmd = BulkAddToCollectionCommand(
        workspace_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        rows=rows,
        dry_run=True,
    )
    result = (await use_case(cmd)).unwrap()
    statuses = {o.row_index: o.status for o in result.outcomes}
    assert statuses == {
        0: RowStatus.RESOLVED,
        1: RowStatus.ALREADY_PRESENT,
        2: RowStatus.UNREGISTERED,
        3: RowStatus.AMBIGUOUS,
        4: RowStatus.ERROR,
    }
    assert result.preview_id is not None  # because 1 unregistered row


@pytest.mark.asyncio
async def test_commit_adds_only_resolved_rows():
    resolver = FakeResolver(
        resolved_map={"CC-1": uuid.uuid4(), "CC-2": uuid.uuid4()},
        ambiguous_values=set(),
    )
    repo = FakeCollectionRepo(members=set())
    use_case = BulkAddToCollection(uow=FakeUoW(), resolver=resolver, repo=repo)

    cmd = BulkAddToCollectionCommand(
        workspace_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        rows=[
            BulkAddRow(row_index=0, registration_number="CC-1"),
            BulkAddRow(row_index=1, registration_number="CC-2"),
            BulkAddRow(row_index=2, smiles="c1ccccc1O"),  # unregistered → skipped
        ],
        dry_run=False,
    )
    result = (await use_case(cmd)).unwrap()
    assert result.resolved_count == 2
    assert result.unregistered_count == 1
    assert len(repo.members) == 2  # only the 2 resolved rows landed


@pytest.mark.asyncio
async def test_stash_persists_unregistered_rows_for_handoff():
    resolver = FakeResolver(resolved_map={}, ambiguous_values=set())
    repo = FakeCollectionRepo(members=set())
    use_case = BulkAddToCollection(uow=FakeUoW(), resolver=resolver, repo=repo)
    cmd = BulkAddToCollectionCommand(
        workspace_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        rows=[BulkAddRow(row_index=0, smiles="c1ccccc1O", name="phenol")],
        dry_run=True,
    )
    result = (await use_case(cmd)).unwrap()
    stashed = use_case.fetch_stash(result.preview_id)
    assert isinstance(stashed, StashedUnregisteredRows)
    assert stashed.rows[0].smiles == "c1ccccc1O"
    assert stashed.rows[0].name == "phenol"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/application/research_organization/test_bulk_add_to_collection.py -v`
Expected: ImportError.

- [ ] **Step 4: Write the use case**

```python
# backend/src/cellar/application/research_organization/bulk_add_to_collection.py
"""BulkAddToCollection — preview + commit a CSV upload of molecule references.

Pure find-and-add: never registers. Stashes unmatched rows under a
preview_id (in-memory, 30-min TTL) so the FE can hand them off to the
bulk-register wizard.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_editor,
    require_same_workspace,
)
from cellar.application.shared.command import Command
from cellar.application.shared.molecule_resolver import (
    MoleculeReference,
    MoleculeResolverProtocol,
)
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.bulk_add_types import (
    BulkAddResult,
    BulkAddRow,
    RowOutcome,
    RowStatus,
)
from cellar.domain.research_organization.enums import RefType
from cellar.domain.research_organization.repository import CollectionRepository
from cellar.domain.shared.errors import DomainError, NotFoundError

_STASH_TTL_SECONDS = 1800


@dataclass(frozen=True, kw_only=True)
class BulkAddToCollectionCommand(Command):
    workspace_id: uuid.UUID
    collection_id: uuid.UUID
    rows: list[BulkAddRow]
    dry_run: bool


@dataclass(frozen=True, kw_only=True)
class StashedUnregisteredRows:
    workspace_id: uuid.UUID
    collection_id: uuid.UUID
    rows: list[BulkAddRow]
    expires_at: float  # unix epoch seconds


class BulkAddToCollection:
    """Resolve each row, classify, optionally commit resolved rows."""

    def __init__(
        self,
        uow: UnitOfWork,
        resolver: MoleculeResolverProtocol,
        repo: CollectionRepository,
    ) -> None:
        self._uow = uow
        self._resolver = resolver
        self._repo = repo
        self._stash: dict[uuid.UUID, StashedUnregisteredRows] = {}

    async def __call__(
        self,
        input: BulkAddToCollectionCommand,
        auth: AuthContext | None = None,
    ) -> Result[BulkAddResult, DomainError]:
        try:
            require_editor(auth)
            require_same_workspace(auth, input.workspace_id)
        except DomainError as exc:
            return Failure(exc)

        async with self._uow:
            collection = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.collection_id
            )
            if collection is None:
                return Failure(NotFoundError("Collection", str(input.collection_id)))

            member_ids = set(
                await self._repo.list_member_ids(
                    input.workspace_id, input.collection_id
                )
            )

            # Build (row → list of MoleculeReference); skip rows with no identifier.
            row_refs: list[tuple[BulkAddRow, list[MoleculeReference]]] = []
            outcomes: list[RowOutcome] = []
            for row in input.rows:
                refs = _row_to_refs(row)
                if not refs:
                    outcomes.append(
                        RowOutcome(
                            row_index=row.row_index,
                            status=RowStatus.ERROR,
                            message="no usable identifier",
                        )
                    )
                    continue
                row_refs.append((row, refs))

            # Resolve all refs at once for efficiency.
            flat_refs = [r for _, rs in row_refs for r in rs]
            resolved_list, unresolved_list = await self._resolver.resolve(
                input.workspace_id, flat_refs
            )
            resolved_by_value = {(r.ref.value, r.ref.ref_type): r for r in resolved_list}
            unresolved_by_value = {
                (u.ref.value, u.ref.ref_type): u for u in unresolved_list
            }

            for row, refs in row_refs:
                first = refs[0]
                key = (first.value, first.ref_type)
                if key in resolved_by_value:
                    rmol = resolved_by_value[key]
                    if rmol.molecule_id in member_ids:
                        outcomes.append(
                            RowOutcome(
                                row_index=row.row_index,
                                status=RowStatus.ALREADY_PRESENT,
                                molecule_id=rmol.molecule_id,
                                molecule_name=rmol.name,
                            )
                        )
                    else:
                        outcomes.append(
                            RowOutcome(
                                row_index=row.row_index,
                                status=RowStatus.RESOLVED,
                                molecule_id=rmol.molecule_id,
                                molecule_name=rmol.name,
                            )
                        )
                else:
                    u = unresolved_by_value.get(key)
                    reason = u.reason if u else "not_found"
                    if reason == "ambiguous":
                        outcomes.append(
                            RowOutcome(
                                row_index=row.row_index,
                                status=RowStatus.AMBIGUOUS,
                                message=reason,
                            )
                        )
                    else:
                        outcomes.append(
                            RowOutcome(
                                row_index=row.row_index,
                                status=RowStatus.UNREGISTERED,
                                message=reason,
                            )
                        )

            # Commit path: add resolved rows.
            if not input.dry_run:
                resolved_ids = [
                    o.molecule_id
                    for o in outcomes
                    if o.status == RowStatus.RESOLVED and o.molecule_id is not None
                ]
                if resolved_ids:
                    await self._repo.add_molecules(
                        input.workspace_id, input.collection_id, resolved_ids
                    )
                await self._uow.commit()

            # Stash unregistered rows for handoff.
            preview_id: uuid.UUID | None = None
            unregistered_rows = [
                row
                for row, _ in row_refs
                if any(
                    o.row_index == row.row_index
                    and o.status == RowStatus.UNREGISTERED
                    for o in outcomes
                )
            ]
            if unregistered_rows:
                preview_id = uuid.uuid4()
                self._stash[preview_id] = StashedUnregisteredRows(
                    workspace_id=input.workspace_id,
                    collection_id=input.collection_id,
                    rows=unregistered_rows,
                    expires_at=time.time() + _STASH_TTL_SECONDS,
                )
                self._gc_stash()

            return Success(
                BulkAddResult.from_outcomes(outcomes, preview_id=preview_id)
            )

    def fetch_stash(
        self, preview_id: uuid.UUID | None
    ) -> StashedUnregisteredRows | None:
        if preview_id is None:
            return None
        self._gc_stash()
        return self._stash.get(preview_id)

    def _gc_stash(self) -> None:
        now = time.time()
        expired = [pid for pid, s in self._stash.items() if s.expires_at < now]
        for pid in expired:
            del self._stash[pid]


def _row_to_refs(row: BulkAddRow) -> list[MoleculeReference]:
    refs: list[MoleculeReference] = []
    if row.registration_number:
        refs.append(
            MoleculeReference(
                value=row.registration_number, ref_type=RefType.REGISTRATION_NUMBER
            )
        )
    elif row.inchi_key:
        refs.append(MoleculeReference(value=row.inchi_key, ref_type=RefType.INCHI_KEY))
    elif row.smiles:
        refs.append(MoleculeReference(value=row.smiles, ref_type=RefType.SMILES))
    elif row.external_id:
        refs.append(
            MoleculeReference(value=row.external_id, ref_type=RefType.EXTERNAL_ID)
        )
    elif row.name:
        refs.append(MoleculeReference(value=row.name, ref_type=RefType.NAME))
    return refs
```

(Note: if `MoleculeResolverProtocol`, `RefType` enum values, or `CollectionRepository.list_member_ids` are spelled differently in the codebase, adjust. Search for the actual names — the imports above are based on the explored layout but may need minor renaming.)

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/application/research_organization/test_bulk_add_to_collection.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/application/research_organization/bulk_add_to_collection.py \
        backend/tests/unit/application/research_organization/test_bulk_add_to_collection.py
git commit -m "feat(research_org): BulkAddToCollection use case + preview-id stash"
```

---

## Task 7: Template CRUD use cases

**Files:**
- Create: `backend/src/cellar/application/research_organization/collection_import_templates.py`
- Create: `backend/tests/unit/application/research_organization/test_collection_import_templates.py`

This task copies the shape of `application/screening/run_import_templates.py` (4 use cases + scoring helper) verbatim, swapping `RunImportTemplate` → `CollectionImportTemplate` and dropping the well-required check.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/application/research_organization/test_collection_import_templates.py
import uuid
from dataclasses import dataclass

import pytest

from cellar.application.research_organization.collection_import_templates import (
    CreateCollectionImportTemplate,
    CreateCollectionImportTemplateCommand,
    DeleteCollectionImportTemplate,
    DeleteCollectionImportTemplateCommand,
    ListCollectionImportTemplates,
    ListCollectionImportTemplatesQuery,
    UpdateCollectionImportTemplate,
    UpdateCollectionImportTemplateCommand,
    score_template_against_headers,
)
from cellar.domain.research_organization.collection_import_template import (
    CollectionImportTemplate,
)


@dataclass
class FakeRepo:
    items: dict[tuple, CollectionImportTemplate]

    async def save(self, t):
        self.items[(t.workspace_id, t.id)] = t

    async def find_by_id_in_workspace(self, ws, tid):
        return self.items.get((ws, tid))

    async def find_by_workspace(self, ws):
        return [t for (w, _), t in self.items.items() if w == ws]

    async def delete(self, ws, tid):
        self.items.pop((ws, tid), None)


@dataclass
class FakeUoW:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return None
    async def commit(self): return []


@dataclass
class FakeDispatcher:
    async def dispatch_all(self, events): pass


@pytest.mark.asyncio
async def test_create_persists_a_template():
    repo = FakeRepo(items={})
    uc = CreateCollectionImportTemplate(FakeUoW(), repo, FakeDispatcher())
    ws = uuid.uuid4()
    result = await uc(
        CreateCollectionImportTemplateCommand(
            workspace_id=ws,
            name="ACME Q3",
            column_mapping={"registration_number": "Reg No."},
            created_by=uuid.uuid4(),
        )
    )
    tpl = result.unwrap()
    assert tpl.name == "ACME Q3"
    assert len(await repo.find_by_workspace(ws)) == 1


def test_scoring_overlap_threshold():
    tpl = CollectionImportTemplate.create(
        workspace_id=uuid.uuid4(),
        name="t",
        column_mapping={"registration_number": "Reg No.", "name": "Compound"},
        created_by=uuid.uuid4(),
    )
    # full match
    assert score_template_against_headers(tpl, ["Reg No.", "Compound"]) == 1.0
    # half match
    assert score_template_against_headers(tpl, ["Reg No.", "Foo"]) == 0.5
    # no match
    assert score_template_against_headers(tpl, ["X", "Y"]) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/application/research_organization/test_collection_import_templates.py -v`
Expected: ImportError.

- [ ] **Step 3: Write the module**

Copy the structure of `application/screening/run_import_templates.py`:
- 4 command/query dataclasses
- 4 use cases (Create / Update / Delete / List), each takes `UoW + repo + dispatcher` and implements `__call__(input, auth)`
- Auth gates: `require_editor` for write ops, `require_same_workspace` for all
- `score_template_against_headers(tpl, headers)` and `_collect_template_refs(mapping)` helpers — same shape as the run-import version but iterates only over string values (no `readout_headers` list special case)

```python
# backend/src/cellar/application/research_organization/collection_import_templates.py
"""CollectionImportTemplate use cases — CRUD + header-match scoring."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_editor,
    require_same_workspace,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.collection_import_template import (
    CollectionImportTemplate,
)
from cellar.domain.research_organization.repository import (
    CollectionImportTemplateRepository,
)
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class CreateCollectionImportTemplateCommand(Command):
    workspace_id: uuid.UUID
    name: str
    column_mapping: dict[str, str]
    description: str | None = None
    created_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class UpdateCollectionImportTemplateCommand(Command):
    workspace_id: uuid.UUID
    template_id: uuid.UUID
    name: str | None = None
    description: str | None = None
    column_mapping: dict[str, str] | None = None


@dataclass(frozen=True, kw_only=True)
class DeleteCollectionImportTemplateCommand(Command):
    workspace_id: uuid.UUID
    template_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ListCollectionImportTemplatesQuery(Query):
    workspace_id: uuid.UUID


class CreateCollectionImportTemplate:
    def __init__(self, uow, repo, dispatcher):
        self._uow, self._repo, self._dispatcher = uow, repo, dispatcher

    async def __call__(self, input, auth=None):
        try:
            require_editor(auth)
            require_same_workspace(auth, input.workspace_id)
        except DomainError as exc:
            return Failure(exc)
        async with self._uow:
            tpl = CollectionImportTemplate.create(
                workspace_id=input.workspace_id,
                name=input.name,
                column_mapping=input.column_mapping,
                description=input.description,
                created_by=input.created_by,
            )
            await self._repo.save(tpl)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(tpl)


class UpdateCollectionImportTemplate:
    def __init__(self, uow, repo, dispatcher):
        self._uow, self._repo, self._dispatcher = uow, repo, dispatcher

    async def __call__(self, input, auth=None):
        try:
            require_editor(auth)
            require_same_workspace(auth, input.workspace_id)
        except DomainError as exc:
            return Failure(exc)
        async with self._uow:
            tpl = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.template_id
            )
            if tpl is None:
                return Failure(
                    NotFoundError("CollectionImportTemplate", str(input.template_id))
                )
            tpl.update(
                name=input.name,
                description=input.description,
                column_mapping=input.column_mapping,
            )
            await self._repo.save(tpl)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(tpl)


class DeleteCollectionImportTemplate:
    def __init__(self, uow, repo, dispatcher):
        self._uow, self._repo, self._dispatcher = uow, repo, dispatcher

    async def __call__(self, input, auth=None):
        try:
            require_editor(auth)
            require_same_workspace(auth, input.workspace_id)
        except DomainError as exc:
            return Failure(exc)
        async with self._uow:
            tpl = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.template_id
            )
            if tpl is None:
                return Failure(
                    NotFoundError("CollectionImportTemplate", str(input.template_id))
                )
            await self._repo.delete(input.workspace_id, input.template_id)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(None)


class ListCollectionImportTemplates:
    def __init__(self, uow, repo):
        self._uow, self._repo = uow, repo

    async def __call__(self, input, auth=None):
        try:
            require_same_workspace(auth, input.workspace_id)
        except DomainError as exc:
            return Failure(exc)
        async with self._uow:
            return Success(await self._repo.find_by_workspace(input.workspace_id))


# Scoring (for auto-pick on wizard load) ---------------------------------------

def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def score_template_against_headers(
    template: CollectionImportTemplate, headers: list[str]
) -> float:
    norm_headers = {_norm(h) for h in headers}
    refs = [v for v in template.column_mapping.values() if v]
    if not refs:
        return 0.0
    matched = sum(1 for r in refs if _norm(r) in norm_headers)
    return matched / len(refs)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/application/research_organization/test_collection_import_templates.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/application/research_organization/collection_import_templates.py \
        backend/tests/unit/application/research_organization/test_collection_import_templates.py
git commit -m "feat(research_org): collection-import template CRUD use cases + scoring"
```

---

## Task 8: DI wiring + dependencies

**Files:**
- Modify: `backend/src/cellar/infrastructure/di/_research_organization.py`
- Modify: `backend/src/cellar/interface/dependencies/_research_organization.py`

- [ ] **Step 1: Bind repository + use cases in the DI container**

In `infrastructure/di/_research_organization.py`, add bindings following the patterns already there. The exact incantation will mirror how `CollectionRepository` and `AddMoleculesToCollection` are bound (lookup that area first). Conceptually:

```python
from cellar.application.research_organization.bulk_add_to_collection import (
    BulkAddToCollection,
)
from cellar.application.research_organization.collection_import_templates import (
    CreateCollectionImportTemplate,
    DeleteCollectionImportTemplate,
    ListCollectionImportTemplates,
    UpdateCollectionImportTemplate,
)
from cellar.domain.research_organization.repository import (
    CollectionImportTemplateRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.collection_import_template_repository import (
    SQLAlchemyCollectionImportTemplateRepository,
)

# In the bind/register block:
container[CollectionImportTemplateRepository] = (
    lambda c: SQLAlchemyCollectionImportTemplateRepository(c[Session])
)
container[BulkAddToCollection] = lambda c: BulkAddToCollection(
    uow=c[UnitOfWork],
    resolver=c[MoleculeResolver],
    repo=c[CollectionRepository],
)
# ... and 4 template CRUD use case bindings analogous to the run-import ones.
```

(Use whatever pattern is already in this file — Lagom registration, factory functions, etc. Don't change the pattern.)

**Important:** `BulkAddToCollection` must be a **singleton** binding (or otherwise process-stable) because the preview-id stash lives on the instance. Singleton scope is the default for the use cases bound today — verify by checking how `AddMoleculesToCollection` is bound and copy that scope.

- [ ] **Step 2: Add FastAPI dependencies**

In `interface/dependencies/_research_organization.py`, add typed `Annotated[Depends(...)]` deps:

```python
BulkAddToCollectionDep = Annotated[
    BulkAddToCollection, Depends(provider_for(BulkAddToCollection))
]
CreateCollectionImportTemplateDep = Annotated[
    CreateCollectionImportTemplate, Depends(provider_for(CreateCollectionImportTemplate))
]
UpdateCollectionImportTemplateDep = ...   # same shape
DeleteCollectionImportTemplateDep = ...   # same shape
ListCollectionImportTemplatesDep = ...    # same shape
```

(Match the `provider_for` / direct-Depends pattern actually used. Run `grep -n "AddMoleculesToCollectionDep" backend/src/cellar/interface/dependencies/` to find the exact pattern.)

- [ ] **Step 3: Quick smoke**

Run: `cd backend && uv run python -c "from cellar.infrastructure.di.container import build_container; c = build_container(); from cellar.application.research_organization.bulk_add_to_collection import BulkAddToCollection; print(c[BulkAddToCollection])"`
Expected: a `BulkAddToCollection` instance prints.

(If the container builder has a different name in this repo, swap.)

- [ ] **Step 4: Commit**

```bash
git add backend/src/cellar/infrastructure/di/_research_organization.py \
        backend/src/cellar/interface/dependencies/_research_organization.py
git commit -m "chore(di): wire BulkAddToCollection + CollectionImportTemplate CRUD"
```

---

## Task 9: REST endpoints — bulk preview/commit + unregistered-rows handoff

**Files:**
- Modify: `backend/src/cellar/interface/routes/collections.py`
- Create: `backend/tests/api/research_organization/test_collection_bulk_import.py`

- [ ] **Step 1: Write the failing API test**

```python
# backend/tests/api/research_organization/test_collection_bulk_import.py
import uuid

import pytest


@pytest.mark.asyncio
async def test_preview_bulk_classifies_rows(client_with_collection):
    client, collection_id, existing_mol = await client_with_collection
    body = {
        "rows": [
            {"row_index": 0, "registration_number": existing_mol["reg_number"]},
            {"row_index": 1, "smiles": "c1ccccc1O", "name": "phenol"},
            {"row_index": 2, "notes": "junk"},
        ],
    }
    response = await client.post(
        f"/api/v1/collections/{collection_id}/molecules/preview-bulk",
        json=body,
    )
    assert response.status_code == 200
    data = response.json()
    statuses = {o["row_index"]: o["status"] for o in data["outcomes"]}
    assert statuses[0] in ("resolved", "already_present")
    assert statuses[1] == "unregistered"
    assert statuses[2] == "error"
    assert data["preview_id"] is not None


@pytest.mark.asyncio
async def test_bulk_commits_resolved_only(client_with_collection):
    client, collection_id, existing_mol = await client_with_collection
    body = {
        "rows": [
            {"row_index": 0, "registration_number": existing_mol["reg_number"]},
            {"row_index": 1, "smiles": "c1ccccc1O"},
        ],
    }
    response = await client.post(
        f"/api/v1/collections/{collection_id}/molecules/bulk",
        json=body,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["resolved_count"] in (0, 1)
    assert data["unregistered_count"] == 1


@pytest.mark.asyncio
async def test_unregistered_rows_endpoint_returns_stash(client_with_collection):
    client, collection_id, _ = await client_with_collection
    preview = await client.post(
        f"/api/v1/collections/{collection_id}/molecules/preview-bulk",
        json={"rows": [{"row_index": 0, "smiles": "c1ccccc1O", "name": "phenol"}]},
    )
    pid = preview.json()["preview_id"]

    rows = await client.get(f"/api/v1/collection-import-previews/{pid}/unregistered-rows")
    assert rows.status_code == 200
    data = rows.json()
    assert len(data["rows"]) == 1
    assert data["rows"][0]["smiles"] == "c1ccccc1O"
    assert data["rows"][0]["name"] == "phenol"
    assert data["collection_id"] == str(collection_id)
```

(The `client_with_collection` fixture should mirror existing fixtures in `tests/api/research_organization/` — it returns a `(client, collection_id, existing_mol_dict)` triple. If the existing API tests use a different fixture name, adapt.)

- [ ] **Step 2: Run the failing test**

Run: `cd backend && uv run pytest tests/api/research_organization/test_collection_bulk_import.py -v`
Expected: 404s on the new endpoints.

- [ ] **Step 3: Add Pydantic request/response models in the route file**

In `backend/src/cellar/interface/routes/collections.py`, near the other request/response bodies:

```python
class BulkAddRowBody(BaseModel):
    row_index: int
    registration_number: str | None = None
    external_id: str | None = None
    inchi_key: str | None = None
    smiles: str | None = None
    name: str | None = None
    notes: str | None = None


class BulkAddRequestBody(BaseModel):
    rows: list[BulkAddRowBody]


class RowOutcomeResponse(BaseModel):
    row_index: int
    status: str
    molecule_id: uuid.UUID | None = None
    molecule_name: str | None = None
    candidates: list[uuid.UUID] = Field(default_factory=list)
    message: str | None = None


class BulkAddResponse(BaseModel):
    outcomes: list[RowOutcomeResponse]
    resolved_count: int
    already_present_count: int
    unregistered_count: int
    ambiguous_count: int
    error_count: int
    preview_id: uuid.UUID | None = None


class UnregisteredRowResponse(BaseModel):
    row_index: int
    registration_number: str | None = None
    external_id: str | None = None
    inchi_key: str | None = None
    smiles: str | None = None
    name: str | None = None
    notes: str | None = None


class UnregisteredRowsResponse(BaseModel):
    rows: list[UnregisteredRowResponse]
    collection_id: uuid.UUID
    collection_name: str | None = None
```

- [ ] **Step 4: Add the three endpoints**

```python
@router.post(
    "/{collection_id}/molecules/preview-bulk",
    response_model=BulkAddResponse,
)
async def preview_bulk_add_to_collection(
    collection_id: uuid.UUID,
    body: BulkAddRequestBody,
    auth: AuthDep,
    use_case: BulkAddToCollectionDep,
) -> BulkAddResponse:
    rows = [
        BulkAddRow(
            row_index=r.row_index,
            registration_number=r.registration_number,
            external_id=r.external_id,
            inchi_key=r.inchi_key,
            smiles=r.smiles,
            name=r.name,
            notes=r.notes,
        )
        for r in body.rows
    ]
    cmd = BulkAddToCollectionCommand(
        workspace_id=auth.workspace_id,
        collection_id=collection_id,
        rows=rows,
        dry_run=True,
    )
    result = result_to_response(await use_case(cmd, auth=auth))
    return _to_bulk_response(result)


@router.post(
    "/{collection_id}/molecules/bulk",
    response_model=BulkAddResponse,
)
async def bulk_add_to_collection(
    collection_id: uuid.UUID,
    body: BulkAddRequestBody,
    auth: AuthDep,
    use_case: BulkAddToCollectionDep,
) -> BulkAddResponse:
    rows = [
        BulkAddRow(
            row_index=r.row_index,
            registration_number=r.registration_number,
            external_id=r.external_id,
            inchi_key=r.inchi_key,
            smiles=r.smiles,
            name=r.name,
            notes=r.notes,
        )
        for r in body.rows
    ]
    cmd = BulkAddToCollectionCommand(
        workspace_id=auth.workspace_id,
        collection_id=collection_id,
        rows=rows,
        dry_run=False,
    )
    result = result_to_response(await use_case(cmd, auth=auth))
    return _to_bulk_response(result)


def _to_bulk_response(result) -> BulkAddResponse:
    return BulkAddResponse(
        outcomes=[
            RowOutcomeResponse(
                row_index=o.row_index,
                status=o.status.value,
                molecule_id=o.molecule_id,
                molecule_name=o.molecule_name,
                candidates=list(o.candidates),
                message=o.message,
            )
            for o in result.outcomes
        ],
        resolved_count=result.resolved_count,
        already_present_count=result.already_present_count,
        unregistered_count=result.unregistered_count,
        ambiguous_count=result.ambiguous_count,
        error_count=result.error_count,
        preview_id=result.preview_id,
    )
```

For the third endpoint (unregistered-rows handoff), it lives at the **top level**, not under `/collections/{id}/...`, because the preview_id is opaque and the FE has it without knowing the collection_id:

```python
# In the same file or a sibling, register under a new router at /api/v1
@router.get(
    "/collection-import-previews/{preview_id}/unregistered-rows",
    response_model=UnregisteredRowsResponse,
)
async def fetch_unregistered_rows(
    preview_id: uuid.UUID,
    auth: AuthDep,
    use_case: BulkAddToCollectionDep,
    collection_repo: CollectionRepositoryDep,
) -> UnregisteredRowsResponse:
    stashed = use_case.fetch_stash(preview_id)
    if stashed is None or stashed.workspace_id != auth.workspace_id:
        raise HTTPException(status_code=404, detail="preview not found or expired")
    collection = await collection_repo.find_by_id_in_workspace(
        stashed.workspace_id, stashed.collection_id
    )
    return UnregisteredRowsResponse(
        rows=[
            UnregisteredRowResponse(
                row_index=r.row_index,
                registration_number=r.registration_number,
                external_id=r.external_id,
                inchi_key=r.inchi_key,
                smiles=r.smiles,
                name=r.name,
                notes=r.notes,
            )
            for r in stashed.rows
        ],
        collection_id=stashed.collection_id,
        collection_name=getattr(collection, "name", None),
    )
```

(If the `/collections` router is `@router = APIRouter(prefix="/collections")` and the new endpoint lives outside that prefix, register a sibling router and `include_router(sibling_router)` in `app.py`. Otherwise put it in a fresh `routes/collection_import_previews.py` and wire it up. Match whatever module structure other top-level routes use.)

- [ ] **Step 5: Run the tests**

Run: `cd backend && uv run pytest tests/api/research_organization/test_collection_bulk_import.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/interface/routes/ \
        backend/tests/api/research_organization/test_collection_bulk_import.py
git commit -m "feat(research_org): preview-bulk + bulk + unregistered-rows endpoints"
```

---

## Task 10: REST endpoints — CollectionImportTemplate CRUD

**Files:**
- Create: `backend/src/cellar/interface/routes/collection_import_templates.py`
- Modify: `backend/src/cellar/interface/app.py` (or wherever routers are registered) — `include_router`
- Create: `backend/tests/api/research_organization/test_collection_import_templates.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/api/research_organization/test_collection_import_templates.py
import pytest


@pytest.mark.asyncio
async def test_create_and_list_template(api_client):
    create = await api_client.post(
        "/api/v1/collection-import-templates",
        json={
            "name": "Partner ACME Q3",
            "column_mapping": {
                "registration_number": "Reg No.",
                "name": "Compound",
            },
        },
    )
    assert create.status_code == 201
    tid = create.json()["id"]

    listing = await api_client.get("/api/v1/collection-import-templates")
    assert listing.status_code == 200
    assert any(t["id"] == tid for t in listing.json())


@pytest.mark.asyncio
async def test_update_and_delete_template(api_client):
    create = await api_client.post(
        "/api/v1/collection-import-templates",
        json={"name": "t1", "column_mapping": {"name": "X"}},
    )
    tid = create.json()["id"]
    upd = await api_client.put(
        f"/api/v1/collection-import-templates/{tid}",
        json={"column_mapping": {"name": "X", "smiles": "Structure"}},
    )
    assert upd.status_code == 200
    assert upd.json()["column_mapping"]["smiles"] == "Structure"

    delete = await api_client.delete(f"/api/v1/collection-import-templates/{tid}")
    assert delete.status_code == 204
```

(Use the existing `api_client` fixture from the api conftest.)

- [ ] **Step 2: Run the failing test**

Run: `cd backend && uv run pytest tests/api/research_organization/test_collection_import_templates.py -v`
Expected: 404s.

- [ ] **Step 3: Copy the routes module from run_import.py:482-584**

Open `backend/src/cellar/interface/routes/run_import.py:482-584`. Copy those template-CRUD endpoints to a new file `routes/collection_import_templates.py`, then rename:
- `run-import-templates` → `collection-import-templates`
- `RunImportTemplate*` → `CollectionImportTemplate*`
- `concentration_unit` field — drop entirely (not part of CollectionImportTemplate.column_mapping)

Bodies:

```python
class CreateCollectionImportTemplateBody(BaseModel):
    name: str
    description: str | None = None
    column_mapping: dict[str, str]


class UpdateCollectionImportTemplateBody(BaseModel):
    name: str | None = None
    description: str | None = None
    column_mapping: dict[str, str] | None = None


class CollectionImportTemplateResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None
    column_mapping: dict[str, str]
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
```

Endpoints: `GET /api/v1/collection-import-templates`, `POST` (201), `PUT /{id}`, `DELETE /{id}` (204).

- [ ] **Step 4: Register the router**

Find `interface/app.py` (or `interface/__init__.py` — wherever `include_router` calls live). Add:

```python
from cellar.interface.routes.collection_import_templates import router as collection_import_templates_router

app.include_router(collection_import_templates_router)
```

- [ ] **Step 5: Run the tests**

Run: `cd backend && uv run pytest tests/api/research_organization/test_collection_import_templates.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/interface/routes/collection_import_templates.py \
        backend/src/cellar/interface/app.py \
        backend/tests/api/research_organization/test_collection_import_templates.py
git commit -m "feat(research_org): CRUD endpoints for collection-import templates"
```

---

## Task 11: orval client regen

**Files:**
- Run: `frontend/orval.config.ts` already configured to pull from the BE OpenAPI

- [ ] **Step 1: Regenerate the client**

Run: `cd frontend && pnpm run orval`
Expected: TypeScript files regenerated for the new endpoints.

- [ ] **Step 2: Verify the generated symbols exist**

Run: `grep -rn "previewBulkAddToCollection\|bulkAddToCollection\|collectionImportTemplate" frontend/src/shared/api/generated/ | head -10`
Expected: function exports present.

- [ ] **Step 3: Type check**

Run: `cd frontend && pnpm exec tsc --noEmit`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/shared/api/generated/
git commit -m "chore(frontend): orval regen for collection-import endpoints"
```

---

## Task 12: CSV parser + template generator

**Files:**
- Create: `frontend/src/features/research-organization/lib/parse-collection-import-csv.ts`
- Create: `frontend/src/features/research-organization/lib/parse-collection-import-csv.test.ts`

This task mirrors `frontend/src/features/inventory/lib/parse-bulk-identifier-csv.ts`.

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/features/research-organization/lib/parse-collection-import-csv.test.ts
import { describe, expect, it } from "vitest";

import {
  buildCollectionImportTemplate,
  parseCollectionImportCsv,
} from "./parse-collection-import-csv";

describe("parseCollectionImportCsv", () => {
  it("returns header row + raw rows for an arbitrary CSV", async () => {
    const csv = "Reg No.,Compound\nCC-000001,Phenol\n,Acetone\n";
    const result = await parseCollectionImportCsv(csv);
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.headers).toEqual(["Reg No.", "Compound"]);
    expect(result.rows).toEqual([
      { "Reg No.": "CC-000001", Compound: "Phenol" },
      { "Reg No.": "", Compound: "Acetone" },
    ]);
  });

  it("returns an error when CSV is empty", async () => {
    const result = await parseCollectionImportCsv("");
    expect(result.kind).toBe("error");
  });
});

describe("buildCollectionImportTemplate", () => {
  it("returns a CSV string with all six columns and example rows", () => {
    const csv = buildCollectionImportTemplate();
    const lines = csv.trim().split("\n");
    expect(lines[0]).toBe(
      "registration_number,external_id,smiles,inchi_key,name,notes",
    );
    expect(lines.length).toBeGreaterThanOrEqual(2);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run src/features/research-organization/lib/parse-collection-import-csv.test.ts`
Expected: module-not-found.

- [ ] **Step 3: Write the module**

```typescript
// frontend/src/features/research-organization/lib/parse-collection-import-csv.ts
import Papa from "papaparse";

export type ParsedCsv =
  | { kind: "ok"; headers: string[]; rows: Record<string, string>[] }
  | { kind: "error"; message: string };

export async function parseCollectionImportCsv(input: string | File): Promise<ParsedCsv> {
  return new Promise((resolve) => {
    Papa.parse(input as unknown as File, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        if (results.errors.length > 0) {
          resolve({ kind: "error", message: results.errors[0].message });
          return;
        }
        const headers = results.meta.fields ?? [];
        if (headers.length === 0) {
          resolve({ kind: "error", message: "no headers detected" });
          return;
        }
        const rows = (results.data as Record<string, string>[]).map((r) => {
          const norm: Record<string, string> = {};
          for (const h of headers) norm[h] = (r[h] ?? "").trim();
          return norm;
        });
        resolve({ kind: "ok", headers, rows });
      },
    });
  });
}

export function buildCollectionImportTemplate(): string {
  return [
    "registration_number,external_id,smiles,inchi_key,name,notes",
    "CC-000001,,,,,",
    ",ACME-LOT-42,,,,partner sample",
    ",,c1ccccc1O,,phenol,",
    "",
  ].join("\n");
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm vitest run src/features/research-organization/lib/parse-collection-import-csv.test.ts`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/research-organization/lib/parse-collection-import-csv.ts \
        frontend/src/features/research-organization/lib/parse-collection-import-csv.test.ts
git commit -m "feat(frontend): CSV parser + template for collection-import wizard"
```

---

## Task 13: FE hooks — preview / commit / templates / handoff

**Files:**
- Create: `frontend/src/features/research-organization/hooks/use-preview-collection-import.ts`
- Create: `frontend/src/features/research-organization/hooks/use-commit-collection-import.ts`
- Create: `frontend/src/features/research-organization/hooks/use-collection-import-templates.ts`
- Create: `frontend/src/features/research-organization/hooks/use-unregistered-rows.ts`

- [ ] **Step 1: Build the four hooks**

Each is a thin TanStack Query wrapper over the orval-generated client. Naming follows the existing `use-bulk-identifier-import.ts` pattern.

```typescript
// use-preview-collection-import.ts
import { useMutation } from "@tanstack/react-query";
import { previewBulkAddToCollection } from "@/shared/api/generated/collections/collections";

export function usePreviewCollectionImport(collectionId: string) {
  return useMutation({
    mutationFn: (body: { rows: Array<Record<string, unknown>> }) =>
      previewBulkAddToCollection(collectionId, body),
  });
}
```

```typescript
// use-commit-collection-import.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { bulkAddToCollection } from "@/shared/api/generated/collections/collections";

export function useCommitCollectionImport(collectionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { rows: Array<Record<string, unknown>> }) =>
      bulkAddToCollection(collectionId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["collection", collectionId] });
      qc.invalidateQueries({ queryKey: ["collection-search", collectionId] });
      qc.invalidateQueries({ queryKey: ["collections"] });
    },
  });
}
```

```typescript
// use-collection-import-templates.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createCollectionImportTemplate,
  deleteCollectionImportTemplate,
  listCollectionImportTemplates,
  updateCollectionImportTemplate,
} from "@/shared/api/generated/collection-import-templates/collection-import-templates";

const QK = ["collection-import-templates"];

export function useCollectionImportTemplates() {
  return useQuery({ queryKey: QK, queryFn: listCollectionImportTemplates });
}

export function useCreateCollectionImportTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createCollectionImportTemplate,
    onSuccess: () => qc.invalidateQueries({ queryKey: QK }),
  });
}

// updateCollectionImportTemplate / deleteCollectionImportTemplate hooks follow the same shape
```

```typescript
// use-unregistered-rows.ts
import { useQuery } from "@tanstack/react-query";
import { getUnregisteredRows } from "@/shared/api/generated/collection-import-previews/collection-import-previews";

export function useUnregisteredRows(previewId: string | null) {
  return useQuery({
    queryKey: ["unregistered-rows", previewId],
    queryFn: () => getUnregisteredRows(previewId!),
    enabled: !!previewId,
  });
}
```

(Verify orval generated those exact symbols; rename to match. Some teams use `useUseCaseName` orval auto-hooks instead of hand-rolled mutations — if the repo's convention is to call the auto-generated hooks, use those instead.)

- [ ] **Step 2: Type check**

Run: `cd frontend && pnpm exec tsc --noEmit`
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/research-organization/hooks/use-preview-collection-import.ts \
        frontend/src/features/research-organization/hooks/use-commit-collection-import.ts \
        frontend/src/features/research-organization/hooks/use-collection-import-templates.ts \
        frontend/src/features/research-organization/hooks/use-unregistered-rows.ts
git commit -m "feat(frontend): TanStack hooks for collection-import preview/commit/templates"
```

---

## Task 14: Wizard upload step

**Files:**
- Create: `frontend/src/features/research-organization/components/collection-import-wizard/upload-step.tsx`
- Create: `frontend/src/features/research-organization/components/collection-import-wizard/upload-step.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
// upload-step.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { UploadStep } from "./upload-step";

describe("UploadStep", () => {
  it("invokes onParsed when a valid CSV is uploaded", async () => {
    const onParsed = vi.fn();
    render(<UploadStep onParsed={onParsed} />);
    const file = new File(
      ["registration_number,name\nCC-000001,Phenol\n"],
      "import.csv",
      { type: "text/csv" },
    );
    const input = screen.getByLabelText(/upload csv/i) as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    await new Promise((r) => setTimeout(r, 100));
    expect(onParsed).toHaveBeenCalled();
  });

  it("renders a Download Template button", () => {
    render(<UploadStep onParsed={vi.fn()} />);
    expect(
      screen.getByRole("button", { name: /download template/i }),
    ).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run src/features/research-organization/components/collection-import-wizard/upload-step.test.tsx`
Expected: module-not-found.

- [ ] **Step 3: Write the component**

Mirror the shape of `frontend/src/features/inventory/components/bulk-identifier-import-wizard/upload-step.tsx`. Key elements:
- Drag-drop or file-input for `.csv` / `.xlsx`
- `Download Template` button → triggers `buildCollectionImportTemplate()` → `<a download>` blob
- Calls `parseCollectionImportCsv()`; on success, calls `onParsed({ headers, rows })`; on error, shows `<Alert variant="destructive">` with the message

```tsx
"use client";

import { useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/shared/components/ui/alert";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  buildCollectionImportTemplate,
  parseCollectionImportCsv,
} from "@/features/research-organization/lib/parse-collection-import-csv";

export interface UploadStepProps {
  onParsed: (data: { headers: string[]; rows: Record<string, string>[] }) => void;
}

export function UploadStep({ onParsed }: UploadStepProps) {
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File) {
    setError(null);
    const parsed = await parseCollectionImportCsv(file);
    if (parsed.kind === "error") {
      setError(parsed.message);
      return;
    }
    onParsed({ headers: parsed.headers, rows: parsed.rows });
  }

  function handleDownload() {
    const blob = new Blob([buildCollectionImportTemplate()], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "collection-import-template.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Label htmlFor="csv-file">Upload CSV</Label>
        <Input
          id="csv-file"
          type="file"
          accept=".csv,text/csv"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void handleFile(f);
          }}
        />
      </div>
      <Button variant="outline" onClick={handleDownload}>
        Download Template
      </Button>
      {error && (
        <Alert variant="destructive">
          <AlertTitle>Parse error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm vitest run src/features/research-organization/components/collection-import-wizard/upload-step.test.tsx`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/research-organization/components/collection-import-wizard/upload-step.tsx \
        frontend/src/features/research-organization/components/collection-import-wizard/upload-step.test.tsx
git commit -m "feat(frontend): collection-import wizard — upload step"
```

---

## Task 15: Wizard mapping step

**Files:**
- Create: `frontend/src/features/research-organization/components/collection-import-wizard/mapping-step.tsx`
- Create: `frontend/src/features/research-organization/components/collection-import-wizard/mapping-step.test.tsx`

The mapping step renders a table: one row per CSV header, with a `<Select>` of roles (`registration_number` / `external_id` / `inchi_key` / `smiles` / `name` / `notes` / `ignore`). It calls the **synonym detection** on the BE via a separate endpoint? **No** — we'll do the auto-detection client-side from a tiny TS port of the synonym dict, since the BE module is also pure-data. This keeps the mapping step responsive without a roundtrip.

- [ ] **Step 1: Write the failing test**

```typescript
// mapping-step.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MappingStep } from "./mapping-step";

describe("MappingStep", () => {
  it("auto-suggests roles from known synonyms", () => {
    render(
      <MappingStep
        headers={["Reg No.", "Compound", "Foo Bar"]}
        rows={[]}
        templates={[]}
        onContinue={vi.fn()}
      />,
    );
    // Verify Reg No. row's select shows "registration_number"
    expect(screen.getByDisplayValue("registration_number")).toBeInTheDocument();
    expect(screen.getByDisplayValue("name")).toBeInTheDocument();
    // Foo Bar should be unmapped (ignore)
    expect(screen.getAllByDisplayValue("ignore").length).toBeGreaterThan(0);
  });

  it("calls onContinue with the user's mapping", () => {
    const onContinue = vi.fn();
    render(
      <MappingStep
        headers={["Reg No."]}
        rows={[]}
        templates={[]}
        onContinue={onContinue}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(onContinue).toHaveBeenCalledWith(
      expect.objectContaining({
        mapping: { registration_number: "Reg No." },
      }),
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run src/features/research-organization/components/collection-import-wizard/mapping-step.test.tsx`
Expected: module-not-found.

- [ ] **Step 3: Write the component**

```tsx
"use client";

import { useMemo, useState } from "react";

import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";

type Role =
  | "registration_number"
  | "external_id"
  | "inchi_key"
  | "smiles"
  | "name"
  | "notes"
  | "ignore";

const ROLES: Role[] = [
  "registration_number",
  "external_id",
  "inchi_key",
  "smiles",
  "name",
  "notes",
  "ignore",
];

const SYNONYMS: Record<Exclude<Role, "ignore">, string[]> = {
  registration_number: [
    "regno", "reg", "regnumber", "registrationnumber", "registration",
    "compoundid", "cellarid", "ccnumber", "ccno", "compoundnumber",
  ],
  external_id: [
    "externalid", "vendorid", "vendorlot", "cas", "casnumber",
    "chemblid", "pubchemid", "suppliercode", "catalogno", "sku",
    "lotid", "lotnumber",
  ],
  inchi_key: ["inchikey", "inchi"],
  smiles: ["smiles", "canonicalsmiles", "structure", "molsmiles"],
  name: ["name", "compoundname", "moleculename", "commonname", "title", "label", "compound"],
  notes: ["notes", "note", "comment", "comments", "description", "remark"],
};

function norm(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function suggestRole(header: string): Role {
  const n = norm(header);
  for (const r of Object.keys(SYNONYMS) as Array<Exclude<Role, "ignore">>) {
    if (SYNONYMS[r].includes(n)) return r;
  }
  return "ignore";
}

interface TemplateLite {
  id: string;
  name: string;
  column_mapping: Record<string, string>;
}

export interface MappingStepProps {
  headers: string[];
  rows: Record<string, string>[];
  templates: TemplateLite[];
  onContinue: (output: {
    mapping: Record<string, string>;
    saveAsTemplate?: { name: string };
  }) => void;
}

export function MappingStep({
  headers,
  rows: _rows,
  templates,
  onContinue,
}: MappingStepProps) {
  const initial = useMemo<Record<string, Role>>(() => {
    const m: Record<string, Role> = {};
    for (const h of headers) m[h] = suggestRole(h);
    return m;
  }, [headers]);
  const [mapping, setMapping] = useState<Record<string, Role>>(initial);
  const [save, setSave] = useState(false);
  const [tplName, setTplName] = useState("");

  function applyTemplate(tpl: TemplateLite) {
    const next: Record<string, Role> = {};
    for (const h of headers) next[h] = "ignore";
    for (const [role, header] of Object.entries(tpl.column_mapping)) {
      if (headers.includes(header)) next[header] = role as Role;
    }
    setMapping(next);
  }

  function buildOutput() {
    const out: Record<string, string> = {};
    for (const h of headers) {
      const r = mapping[h];
      if (r !== "ignore") out[r] = h;
    }
    return out;
  }

  return (
    <div className="space-y-6">
      {templates.length > 0 && (
        <div className="space-y-2">
          <Label>Apply a saved template</Label>
          <Select onValueChange={(id) => {
            const t = templates.find((x) => x.id === id);
            if (t) applyTemplate(t);
          }}>
            <SelectTrigger><SelectValue placeholder="Choose template…" /></SelectTrigger>
            <SelectContent>
              {templates.map((t) => (
                <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
      <Table>
        <TableHeader>
          <TableRow><TableHead>CSV column</TableHead><TableHead>Role</TableHead></TableRow>
        </TableHeader>
        <TableBody>
          {headers.map((h) => (
            <TableRow key={h}>
              <TableCell className="font-mono text-sm">{h}</TableCell>
              <TableCell>
                <Select
                  value={mapping[h]}
                  onValueChange={(v) => setMapping((m) => ({ ...m, [h]: v as Role }))}
                >
                  <SelectTrigger>
                    <SelectValue>{mapping[h]}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {ROLES.map((r) => (
                      <SelectItem key={r} value={r}>{r}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <div className="flex items-center gap-2">
        <Checkbox id="save" checked={save} onCheckedChange={(v) => setSave(!!v)} />
        <Label htmlFor="save">Save this mapping as a workspace template</Label>
      </div>
      {save && (
        <Input
          placeholder="Template name"
          value={tplName}
          onChange={(e) => setTplName(e.target.value)}
        />
      )}
      <Button
        onClick={() =>
          onContinue({
            mapping: buildOutput(),
            saveAsTemplate: save && tplName ? { name: tplName } : undefined,
          })
        }
      >
        Continue
      </Button>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm vitest run src/features/research-organization/components/collection-import-wizard/mapping-step.test.tsx`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/research-organization/components/collection-import-wizard/mapping-step.tsx \
        frontend/src/features/research-organization/components/collection-import-wizard/mapping-step.test.tsx
git commit -m "feat(frontend): collection-import wizard — mapping step with synonyms"
```

---

## Task 16: Wizard preview step

**Files:**
- Create: `frontend/src/features/research-organization/components/collection-import-wizard/preview-step.tsx`
- Create: `frontend/src/features/research-organization/components/collection-import-wizard/preview-step.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
// preview-step.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PreviewStep } from "./preview-step";

const result = {
  outcomes: [
    { row_index: 0, status: "resolved", molecule_id: "m1", molecule_name: "Phenol" },
    { row_index: 1, status: "unregistered", message: "not_found" },
  ],
  resolved_count: 1,
  already_present_count: 0,
  unregistered_count: 1,
  ambiguous_count: 0,
  error_count: 0,
  preview_id: "p1",
};

describe("PreviewStep", () => {
  it("renders count badges", () => {
    render(
      <PreviewStep
        result={result as any}
        collectionId="c1"
        onCommit={vi.fn()}
      />,
    );
    expect(screen.getByText(/1 resolved/i)).toBeInTheDocument();
    expect(screen.getByText(/1 unregistered/i)).toBeInTheDocument();
  });

  it("renders the Register them handoff link when preview_id is present", () => {
    render(
      <PreviewStep result={result as any} collectionId="c1" onCommit={vi.fn()} />,
    );
    expect(
      screen.getByRole("link", { name: /register them/i }),
    ).toHaveAttribute(
      "href",
      "/compounds/bulk-register?from_collection_import=p1&return_to_collection=c1",
    );
  });

  it("enables commit button only when resolved_count > 0", () => {
    render(
      <PreviewStep result={result as any} collectionId="c1" onCommit={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: /add 1 resolved/i })).toBeEnabled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run src/features/research-organization/components/collection-import-wizard/preview-step.test.tsx`
Expected: module-not-found.

- [ ] **Step 3: Write the component**

```tsx
"use client";

import Link from "next/link";

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/shared/components/ui/table";

interface Outcome {
  row_index: number;
  status: "resolved" | "already_present" | "unregistered" | "ambiguous" | "error";
  molecule_id?: string | null;
  molecule_name?: string | null;
  candidates?: string[];
  message?: string | null;
}

export interface PreviewResult {
  outcomes: Outcome[];
  resolved_count: number;
  already_present_count: number;
  unregistered_count: number;
  ambiguous_count: number;
  error_count: number;
  preview_id: string | null;
}

export interface PreviewStepProps {
  result: PreviewResult;
  collectionId: string;
  onCommit: () => void;
}

const STATUS_VARIANT: Record<Outcome["status"], "default" | "secondary" | "destructive" | "outline"> = {
  resolved: "default",
  already_present: "secondary",
  unregistered: "outline",
  ambiguous: "outline",
  error: "destructive",
};

export function PreviewStep({ result, collectionId, onCommit }: PreviewStepProps) {
  const canCommit = result.resolved_count > 0;
  const handoffHref = result.preview_id
    ? `/compounds/bulk-register?from_collection_import=${result.preview_id}&return_to_collection=${collectionId}`
    : null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-2">
        <Badge className="bg-emerald-100 text-emerald-900">
          {result.resolved_count} resolved
        </Badge>
        <Badge variant="secondary">
          {result.already_present_count} already present
        </Badge>
        <Badge variant="outline" className="border-amber-500 text-amber-700">
          {result.unregistered_count} unregistered
        </Badge>
        <Badge variant="outline" className="border-amber-500 text-amber-700">
          {result.ambiguous_count} ambiguous
        </Badge>
        <Badge variant="destructive">{result.error_count} error</Badge>
      </div>
      {handoffHref && (
        <div className="rounded border border-amber-300 bg-amber-50 p-3">
          <p className="text-sm text-amber-900">
            {result.unregistered_count} rows reference molecules not yet registered.
            They will be skipped by this import.
          </p>
          <Link
            href={handoffHref}
            className="mt-2 inline-block text-sm font-medium underline"
          >
            Register them →
          </Link>
        </div>
      )}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Row</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Molecule</TableHead>
            <TableHead>Diagnostic</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {result.outcomes.map((o) => (
            <TableRow key={o.row_index}>
              <TableCell className="font-mono">{o.row_index + 1}</TableCell>
              <TableCell>
                <Badge variant={STATUS_VARIANT[o.status]}>{o.status}</Badge>
              </TableCell>
              <TableCell>{o.molecule_name ?? "—"}</TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {o.message ?? ""}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <Button disabled={!canCommit} onClick={onCommit}>
        Add {result.resolved_count} resolved {result.resolved_count === 1 ? "row" : "rows"}
      </Button>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm vitest run src/features/research-organization/components/collection-import-wizard/preview-step.test.tsx`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/research-organization/components/collection-import-wizard/preview-step.tsx \
        frontend/src/features/research-organization/components/collection-import-wizard/preview-step.test.tsx
git commit -m "feat(frontend): collection-import wizard — preview step with handoff CTA"
```

---

## Task 17: Wizard confirm step + main composer + page route + entry button

**Files:**
- Create: `frontend/src/features/research-organization/components/collection-import-wizard/confirm-step.tsx`
- Create: `frontend/src/features/research-organization/components/collection-import-wizard/index.tsx`
- Create: `frontend/src/app/(dashboard)/collections/[id]/import/page.tsx`
- Modify: `frontend/src/features/research-organization/components/collection-detail.tsx`

- [ ] **Step 1: Confirm step**

```tsx
// confirm-step.tsx
"use client";

import Link from "next/link";

import { Button } from "@/shared/components/ui/button";

export interface ConfirmStepProps {
  result: {
    resolved_count: number;
    already_present_count: number;
    unregistered_count: number;
    error_count: number;
    preview_id: string | null;
  };
  collectionId: string;
  onClose: () => void;
}

export function ConfirmStep({ result, collectionId, onClose }: ConfirmStepProps) {
  const handoffHref = result.preview_id
    ? `/compounds/bulk-register?from_collection_import=${result.preview_id}&return_to_collection=${collectionId}`
    : null;
  return (
    <div className="space-y-4">
      <div className="rounded border bg-emerald-50 p-4">
        <p className="font-medium">
          {result.resolved_count} molecules added
        </p>
        <p className="text-sm text-muted-foreground">
          {result.already_present_count} already present ·{" "}
          {result.unregistered_count + result.error_count} skipped
        </p>
      </div>
      {handoffHref && (
        <div className="rounded border border-amber-300 bg-amber-50 p-3">
          <p className="text-sm text-amber-900">
            {result.unregistered_count} rows weren't added because they aren't
            registered yet.
          </p>
          <Link
            href={handoffHref}
            className="mt-2 inline-block text-sm font-medium underline"
          >
            Register them now →
          </Link>
        </div>
      )}
      <div className="flex gap-2">
        <Link href={`/collections/${collectionId}`}>
          <Button variant="default">Back to collection</Button>
        </Link>
        <Button variant="outline" onClick={onClose}>
          Import another file
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Main composer**

```tsx
// index.tsx
"use client";

import { useState } from "react";

import {
  useCommitCollectionImport,
  usePreviewCollectionImport,
} from "@/features/research-organization/hooks";
import {
  useCollectionImportTemplates,
  useCreateCollectionImportTemplate,
} from "@/features/research-organization/hooks/use-collection-import-templates";

import { ConfirmStep } from "./confirm-step";
import { MappingStep } from "./mapping-step";
import { PreviewStep, type PreviewResult } from "./preview-step";
import { UploadStep } from "./upload-step";

type Step = "upload" | "mapping" | "preview" | "confirm";

export function CollectionImportWizard({ collectionId }: { collectionId: string }) {
  const [step, setStep] = useState<Step>("upload");
  const [headers, setHeaders] = useState<string[]>([]);
  const [rows, setRows] = useState<Record<string, string>[]>([]);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [pendingTemplateName, setPendingTemplateName] = useState<string | null>(null);

  const templatesQ = useCollectionImportTemplates();
  const createTpl = useCreateCollectionImportTemplate();
  const previewMut = usePreviewCollectionImport(collectionId);
  const commitMut = useCommitCollectionImport(collectionId);

  function buildBody(currentMapping: Record<string, string>) {
    return {
      rows: rows.map((r, i) => {
        const out: Record<string, unknown> = { row_index: i };
        for (const [role, header] of Object.entries(currentMapping)) {
          out[role] = r[header] || null;
        }
        return out;
      }),
    };
  }

  async function handleContinueFromMapping(out: {
    mapping: Record<string, string>;
    saveAsTemplate?: { name: string };
  }) {
    setMapping(out.mapping);
    if (out.saveAsTemplate) setPendingTemplateName(out.saveAsTemplate.name);
    const res = await previewMut.mutateAsync(buildBody(out.mapping));
    setPreview(res as PreviewResult);
    setStep("preview");
  }

  async function handleCommit() {
    const res = await commitMut.mutateAsync(buildBody(mapping));
    setPreview(res as PreviewResult);
    if (pendingTemplateName) {
      await createTpl.mutateAsync({
        name: pendingTemplateName,
        column_mapping: mapping,
      });
    }
    setStep("confirm");
  }

  return (
    <div className="mx-auto max-w-4xl p-6">
      <h1 className="mb-6 text-2xl font-semibold">Bulk import to collection</h1>
      {step === "upload" && (
        <UploadStep
          onParsed={({ headers, rows }) => {
            setHeaders(headers);
            setRows(rows);
            setStep("mapping");
          }}
        />
      )}
      {step === "mapping" && (
        <MappingStep
          headers={headers}
          rows={rows}
          templates={templatesQ.data ?? []}
          onContinue={handleContinueFromMapping}
        />
      )}
      {step === "preview" && preview && (
        <PreviewStep
          result={preview}
          collectionId={collectionId}
          onCommit={handleCommit}
        />
      )}
      {step === "confirm" && preview && (
        <ConfirmStep
          result={preview}
          collectionId={collectionId}
          onClose={() => {
            setStep("upload");
            setHeaders([]);
            setRows([]);
            setMapping({});
            setPreview(null);
          }}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Page route**

```tsx
// frontend/src/app/(dashboard)/collections/[id]/import/page.tsx
import { CollectionImportWizard } from "@/features/research-organization/components/collection-import-wizard";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <CollectionImportWizard collectionId={id} />;
}
```

- [ ] **Step 4: Entry button on collection detail**

Open `frontend/src/features/research-organization/components/collection-detail.tsx`. Find the header action buttons area (the one with "Add Molecules", "Edit", etc.). Add a button next to them:

```tsx
import Link from "next/link";

<Link href={`/collections/${collection.id}/import`}>
  <Button variant="outline">Bulk import</Button>
</Link>
```

(Use the exact existing styling pattern — Button + Link with `variant` matching siblings.)

- [ ] **Step 5: Type check + run wizard tests**

Run: `cd frontend && pnpm exec tsc --noEmit && pnpm vitest run src/features/research-organization/components/collection-import-wizard/`
Expected: clean type-check + all wizard step tests pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/research-organization/components/collection-import-wizard/ \
        frontend/src/app/\(dashboard\)/collections/\[id\]/import/page.tsx \
        frontend/src/features/research-organization/components/collection-detail.tsx
git commit -m "feat(frontend): collection-import wizard — confirm step + composer + entry button"
```

---

## Task 18: Register-wizard handoff — startup branch + return-to-collection CTA

**Files:**
- Modify: the bulk-register wizard's startup component (likely `step-input.tsx` or the wizard composer in `features/chemical-registration/components/registration-wizard/`)
- Modify: `step-summary.tsx` (the success-step file)

- [ ] **Step 1: Identify the wizard composer**

Run: `grep -rln "step-input\|StepInput\|registration-wizard" frontend/src/features/chemical-registration/ | head -5` to find the page or container that mounts the wizard steps. Likely a `wizard.tsx` or `index.tsx` in the registration-wizard folder. Confirm by reading the file.

- [ ] **Step 2: Add the startup-stash branch**

In the wizard composer (or `step-input.tsx` — whichever owns the initial state), after the URL params are accessible:

```tsx
"use client";

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";

import { useUnregisteredRows } from "@/features/research-organization/hooks/use-unregistered-rows";

// inside the component:
const params = useSearchParams();
const fromImport = params.get("from_collection_import");
const { data: stash } = useUnregisteredRows(fromImport);

useEffect(() => {
  if (!stash) return;
  // Pre-fill the wizard's input state from the stash rows.
  // Concrete shape depends on how step-input currently models its input — likely:
  // setInputCsv(stashRowsAsCsv(stash.rows));
  // Confirm the actual prop / state setter and assign accordingly.
}, [stash]);
```

The exact "pre-fill" approach depends on the existing input mechanism:
- If `step-input.tsx` accepts a CSV string, convert `stash.rows` to a CSV with columns `name,smiles,external_id,notes` and inject as the initial input.
- If it accepts a list of parsed rows directly, pass those.

Either way: the goal is the chemist arrives at the wizard with the rows pre-loaded and fills in org/scientist/source on the existing screens.

- [ ] **Step 3: Add the success-step CTA**

In `step-summary.tsx`, find the success area (renders "X molecules registered"). Add a conditional CTA block:

```tsx
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { addMoleculesToCollection } from "@/shared/api/generated/collections/collections";

import { Button } from "@/shared/components/ui/button";

// inside StepSummary, after the existing success card:
const params = useSearchParams();
const returnToCollection = params.get("return_to_collection");

const addMut = useMutation({
  mutationFn: (moleculeIds: string[]) =>
    addMoleculesToCollection(returnToCollection!, {
      references: moleculeIds.map((id) => ({ value: id, ref_type: "uuid" })),
    }),
});

// in the JSX:
{returnToCollection && registeredMoleculeIds.length > 0 && (
  <div className="rounded border border-emerald-300 bg-emerald-50 p-4">
    <p className="font-medium">
      ✓ {registeredMoleculeIds.length} molecules registered.
    </p>
    {addMut.isSuccess ? (
      <Link href={`/collections/${returnToCollection}`}>
        <Button>View collection →</Button>
      </Link>
    ) : (
      <Button
        onClick={() => addMut.mutate(registeredMoleculeIds)}
        disabled={addMut.isPending}
      >
        Add to collection →
      </Button>
    )}
    {addMut.isError && (
      <p className="mt-2 text-sm text-destructive">
        Add failed — try again or open the collection manually.
      </p>
    )}
  </div>
)}
```

(The exact source of `registeredMoleculeIds` depends on how `step-summary.tsx` already reads the bulk-registration result. The bulk_registration items endpoint returns rows with `molecule_id`; gather the successful ones — those with status `registered` or `deduplicated`.)

- [ ] **Step 4: Type check**

Run: `cd frontend && pnpm exec tsc --noEmit`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/chemical-registration/components/registration-wizard/
git commit -m "feat(frontend): register wizard — collection-import handoff + return CTA"
```

---

## Verification before push

After all tasks land, run a full sweep:

- [ ] **Backend**

```bash
cd backend && uv run pytest tests/unit tests/api/research_organization/ tests/integration/persistence/research_organization/ -q
```
Expected: all green; new test count >= existing baseline + the new tests added by this plan.

- [ ] **Frontend**

```bash
cd frontend && pnpm vitest run && pnpm exec tsc --noEmit
```
Expected: green + clean.

- [ ] **Migration**

```bash
cd backend && uv run alembic upgrade head
```
Expected: migration 045 applied (no-op if already at head).

---

## Browser smoke checklist (10 scenarios)

Run on the dev stack after `docker compose up -d && cd frontend && pnpm dev`:

| # | Scenario | Expected |
|---|---|---|
| 1 | Open a collection detail page → click "Bulk import" header button | Lands at `/collections/{id}/import` with the Upload step |
| 2 | Click "Download Template" | Downloads `collection-import-template.csv` with the 6-column header + 3 example rows |
| 3 | Upload a CSV with headers `Reg No., Compound Name, Structure` and 5 rows (4 existing reg numbers, 1 unknown SMILES) | Auto-advances to Mapping; the 3 columns show roles `registration_number`, `name`, `smiles`; no manual override needed |
| 4 | Click Continue on Mapping | Preview shows count badges — 4 resolved, 1 unregistered, 0 errors |
| 5 | Verify the amber unregistered banner | "1 rows reference molecules not yet registered. [Register them →]" link href is `/compounds/bulk-register?from_collection_import=<uuid>&return_to_collection=<id>` |
| 6 | Click "Add 4 resolved rows" | Confirm step shows "4 molecules added · 0 already present · 1 skipped"; the "Register them now" CTA still appears |
| 7 | Click "Register them now" | Routes to bulk-register wizard; the input step shows the unmatched row pre-filled (verify by inspecting the parsed-rows preview area or the CSV textarea) |
| 8 | Complete the register wizard (fill org/scientist/source, submit) | Success step shows "✓ 1 molecules registered. [Add to collection →]" |
| 9 | Click "Add to collection →" | Button shows pending → success; click "View collection →" → the newly-registered molecule appears in the collection's grid |
| 10 | Re-run the collection-import wizard with the SAME CSV → Save mapping as "Smoke Test Template" → commit | Reload the wizard → Mapping step shows "Apply a saved template" dropdown with "Smoke Test Template" available |

---

## Diagnostic anchors

After implementation:
- `application/research_organization/bulk_add_to_collection.py::BulkAddToCollection.__call__` — single source of row classification + commit. `_row_to_refs` is the per-row identifier-priority helper.
- `application/research_organization/bulk_add_to_collection.py::BulkAddToCollection.fetch_stash` — process-local in-memory stash. 30-min TTL via `_STASH_TTL_SECONDS`.
- `interface/routes/collections.py` — three new endpoints (`preview-bulk`, `bulk`, plus the sibling-router unregistered-rows GET).
- `application/research_organization/collection_import_mapping.py::_SYNONYMS` — backend SoT for header role detection; the FE `SYNONYMS` in `mapping-step.tsx` is a manual mirror. Changes to one must be reflected in the other.
- `features/research-organization/components/collection-import-wizard/index.tsx::CollectionImportWizard` — 4-step state machine.
- `features/chemical-registration/components/registration-wizard/step-summary.tsx` — success-step CTA conditional on `return_to_collection` URL param.

---

## Self-review summary

- All 8 spec goals have tasks: header detection (T5,15), preview classification (T6,16), saved templates (T2,4,7,10,15), independent commit of resolved rows (T6,16), handoff to register wizard (T9,17,18). ✓
- No placeholders, no TBDs. Every code step contains complete code or a precise enough description of an existing pattern to copy. ✓
- Type-consistency check: `BulkAddRow` / `RowOutcome` / `RowStatus` / `BulkAddResult` names used identically in T1, T6, T9. `CollectionImportTemplate` consistent in T2, T4, T7, T10. FE prop names (`onParsed`, `onContinue`, `onCommit`, `onClose`) consistent in T14–T17. ✓
- Out-of-scope items from the spec (auto-register, SDF, per-row toggles, pending state) — not tasked, by design. ✓
