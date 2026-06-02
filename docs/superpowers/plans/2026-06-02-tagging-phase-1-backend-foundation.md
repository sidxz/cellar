# Tagging — Phase 1: Backend Foundation (Domain + Persistence + Migration)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the domain + persistence foundation for AWS-style key-value tags — a `Tag` aggregate (key + optional value, case-insensitive dedup, provenance), per-entity link tables, their repositories, and migration `047` that creates the schema and backfills the existing `molecules.tags` strings.

**Architecture:** Normalized tag **registry** (`tags` table, a `Tag` aggregate in the Workspace Config context) + **per-entity link tables** (`molecule_tags`, `protocol_tags`, `project_tags`, `collection_tags`) with real FKs and `ON DELETE CASCADE`. Links are managed by a lightweight, non-aggregate repository (mirrors `SQLAlchemyProjectMemberRepository`). A `tag_links_all` `UNION ALL` view supports cross-type queries. This phase delivers everything at the repository level + a tested backfill; **no** application use cases or API yet (Phase 2).

**Tech Stack:** Python 3.13, SQLAlchemy 2.0 async (asyncpg), PostgreSQL 16 (`pg_trgm`, `NULLS NOT DISTINCT`), Alembic, Pydantic v2, `dry-python/returns`, pytest + testcontainers.

**Spec:** `docs/superpowers/specs/2026-06-02-tagging-design.md` (this plan implements §4 Domain, §5 Persistence, §11 Performance, and the create+backfill half of §5.5 / §13 steps 1–2).

**Branch:** `kvt`

---

## File Structure

### New files — Domain

| Path | Responsibility |
|------|----------------|
| `backend/src/cellar/domain/workspace_config/tagging/__init__.py` | Package marker. |
| `backend/src/cellar/domain/workspace_config/tagging/tag.py` | `TaggableEntityType` enum, `TagName` value object (normalization/validation), `Tag` aggregate. |
| `backend/src/cellar/domain/workspace_config/tagging/events.py` | Tag domain events (`TagCreated`, `TagRenamed`, `TagMerged`, `TagDeleted`, `TagAssigned`, `TagUnassigned`). |
| `backend/src/cellar/domain/workspace_config/tagging/repository.py` | `TagRepository`, `TagLinkRepository`, `TagLinkRepositoryProvider` protocols. |

### New files — Persistence

| Path | Responsibility |
|------|----------------|
| `backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/__init__.py` | Package marker. |
| `backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/models.py` | `TagModel`, `TagLinkMixin`, four link models. |
| `backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/backfill_sql.py` | Frozen backfill SQL constants (shared by migration + test — DRY). |
| `backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/tag_repository.py` | `SQLAlchemyTagRepository` (data mapper, `get_or_create`, `search`) + `tag_model_to_domain` helper. |
| `backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/tag_link_repository.py` | Generic `SQLAlchemyTagLinkRepository` base, four subclasses, `get_tag_link_repository` factory. |
| `backend/alembic/versions/047_tagging.py` | Create extension/tables/indexes/view + backfill molecule tags. |

### Modified files

| Path | Change |
|------|--------|
| `backend/alembic/env.py` | Add `import …tagging.models  # noqa: F401` so autogenerate/metadata sees the new tables. |

### New files — Tests

| Path | Responsibility |
|------|----------------|
| `backend/tests/unit/domain/workspace_config/test_tag_name.py` | `TagName` normalization/validation unit tests. |
| `backend/tests/unit/domain/workspace_config/test_tag.py` | `Tag` aggregate unit tests (create/rename/events). |
| `backend/tests/integration/test_tagging.py` | `SQLAlchemyTagRepository` + link repository + cascade + backfill integration tests. |

---

## Task 1: `TaggableEntityType` enum + `TagName` value object

**Files:**
- Create: `backend/src/cellar/domain/workspace_config/tagging/__init__.py`
- Create: `backend/src/cellar/domain/workspace_config/tagging/tag.py` (partial — enum + VO)
- Test: `backend/tests/unit/domain/workspace_config/test_tag_name.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/domain/workspace_config/test_tag_name.py`:

```python
"""Tests for the TagName value object (normalization + validation)."""

import pytest

from cellar.domain.workspace_config.tagging.tag import TagName


class TestTagNameNormalization:
    def test_key_only(self) -> None:
        name = TagName(key="favorite")
        assert name.key == "favorite"
        assert name.value is None
        assert name.normalized_key == "favorite"
        assert name.normalized_value is None

    def test_key_and_value(self) -> None:
        name = TagName(key="Project", value="Alpha")
        assert name.key == "Project"
        assert name.value == "Alpha"
        assert name.normalized_key == "project"
        assert name.normalized_value == "alpha"

    def test_key_and_value_are_trimmed(self) -> None:
        name = TagName(key="  Env  ", value="  Prod  ")
        assert name.key == "Env"
        assert name.value == "Prod"

    def test_empty_value_string_becomes_none(self) -> None:
        name = TagName(key="favorite", value="   ")
        assert name.value is None
        assert name.normalized_value is None

    def test_case_insensitive_normalization(self) -> None:
        assert TagName(key="ENV").normalized_key == TagName(key="env").normalized_key
        assert (
            TagName(key="k", value="PROD").normalized_value
            == TagName(key="k", value="prod").normalized_value
        )

    def test_is_frozen(self) -> None:
        name = TagName(key="env")
        with pytest.raises(Exception):
            name.key = "other"  # type: ignore[misc]


class TestTagNameValidation:
    def test_empty_key_raises(self) -> None:
        with pytest.raises(ValueError, match="key must not be empty"):
            TagName(key="   ")

    def test_key_too_long_raises(self) -> None:
        with pytest.raises(ValueError, match="128"):
            TagName(key="x" * 129)

    def test_value_too_long_raises(self) -> None:
        with pytest.raises(ValueError, match="256"):
            TagName(key="k", value="x" * 257)

    def test_control_chars_in_key_raise(self) -> None:
        with pytest.raises(ValueError, match="control"):
            TagName(key="bad\tkey")

    def test_control_chars_in_value_raise(self) -> None:
        with pytest.raises(ValueError, match="control"):
            TagName(key="k", value="bad\nvalue")
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `backend/`): `uv run pytest tests/unit/domain/workspace_config/test_tag_name.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cellar.domain.workspace_config.tagging'`.

- [ ] **Step 3: Create the package marker**

Create `backend/src/cellar/domain/workspace_config/tagging/__init__.py` (empty file).

- [ ] **Step 4: Write the enum + value object**

Create `backend/src/cellar/domain/workspace_config/tagging/tag.py`:

```python
"""Tag aggregate, TagName value object, and the taggable-entity enum.

A tag is a ``key`` with an OPTIONAL ``value`` (AWS-style). Equality / dedup is
case-insensitive on the *normalized* key+value; the original casing is kept for
display. Tags are shared workspace-wide and carry creator provenance.
"""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator

_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_MAX_KEY_LEN = 128
_MAX_VALUE_LEN = 256


class TaggableEntityType(str, Enum):
    """Entity types that can carry tags (one link table each)."""

    MOLECULE = "Molecule"
    PROTOCOL = "Protocol"
    PROJECT = "Project"
    COLLECTION = "Collection"


class TagName(BaseModel):
    """Immutable (key, optional value) with case-insensitive normalization.

    - ``key`` is required and non-empty after trim (<= 128 chars).
    - ``value`` is optional (<= 256 chars); an all-whitespace value becomes ``None``.
    - Control characters are rejected in both.
    """

    model_config = ConfigDict(frozen=True)

    key: str
    value: str | None = None

    @field_validator("key")
    @classmethod
    def _validate_key(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Tag key must not be empty")
        if len(v) > _MAX_KEY_LEN:
            raise ValueError(f"Tag key must be at most {_MAX_KEY_LEN} characters")
        if _CONTROL_RE.search(v):
            raise ValueError("Tag key must not contain control characters")
        return v

    @field_validator("value")
    @classmethod
    def _validate_value(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if v == "":
            return None
        if len(v) > _MAX_VALUE_LEN:
            raise ValueError(f"Tag value must be at most {_MAX_VALUE_LEN} characters")
        if _CONTROL_RE.search(v):
            raise ValueError("Tag value must not contain control characters")
        return v

    @property
    def normalized_key(self) -> str:
        return self.key.casefold()

    @property
    def normalized_value(self) -> str | None:
        return self.value.casefold() if self.value is not None else None
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/unit/domain/workspace_config/test_tag_name.py -v`
Expected: PASS (all tests green).

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/domain/workspace_config/tagging/__init__.py \
        backend/src/cellar/domain/workspace_config/tagging/tag.py \
        backend/tests/unit/domain/workspace_config/test_tag_name.py
git commit -m "feat(tagging): TagName value object + TaggableEntityType enum"
```

---

## Task 2: `Tag` aggregate + domain events

**Files:**
- Create: `backend/src/cellar/domain/workspace_config/tagging/events.py`
- Modify: `backend/src/cellar/domain/workspace_config/tagging/tag.py` (append `Tag` aggregate)
- Test: `backend/tests/unit/domain/workspace_config/test_tag.py`

- [ ] **Step 1: Write the events module**

Create `backend/src/cellar/domain/workspace_config/tagging/events.py`:

```python
"""Domain events for the tagging capability."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from cellar.domain.shared.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class TagCreated(DomainEvent):
    key: str
    value: str | None


@dataclass(frozen=True, kw_only=True)
class TagRenamed(DomainEvent):
    key: str
    value: str | None


@dataclass(frozen=True, kw_only=True)
class TagDeleted(DomainEvent):
    key: str
    value: str | None


@dataclass(frozen=True, kw_only=True)
class TagMerged(DomainEvent):
    """Emitted on the source tag when it is merged into ``target_tag_id``."""

    target_tag_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class TagAssigned(DomainEvent):
    """Emitted when a tag is applied to an entity. ``aggregate_id`` is the tag id."""

    target_type: str
    target_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class TagUnassigned(DomainEvent):
    target_type: str
    target_id: uuid.UUID
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/unit/domain/workspace_config/test_tag.py`:

```python
"""Tests for the Tag aggregate."""

import uuid

import pytest

from cellar.domain.workspace_config.tagging.events import TagCreated, TagRenamed
from cellar.domain.workspace_config.tagging.tag import Tag, TagName


@pytest.fixture
def ws_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


class TestTagCreate:
    def test_factory_sets_fields(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        tag = Tag.create(
            workspace_id=ws_id, name=TagName(key="Project", value="Alpha"), created_by=user_id
        )
        assert tag.workspace_id == ws_id
        assert tag.key == "Project"
        assert tag.value == "Alpha"
        assert tag.normalized_key == "project"
        assert tag.normalized_value == "alpha"
        assert tag.created_by == user_id
        assert tag.version == 1

    def test_factory_emits_created_event(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        tag = Tag.create(
            workspace_id=ws_id, name=TagName(key="favorite"), created_by=user_id
        )
        events = tag.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], TagCreated)
        assert events[0].key == "favorite"
        assert events[0].value is None
        assert events[0].aggregate_type == "Tag"
        assert events[0].workspace_id == ws_id

    def test_valueless_tag(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        tag = Tag.create(workspace_id=ws_id, name=TagName(key="hit"), created_by=user_id)
        assert tag.value is None
        assert tag.normalized_value is None


class TestTagRename:
    def test_rename_changes_name_and_emits(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        tag = Tag.create(workspace_id=ws_id, name=TagName(key="old"), created_by=user_id)
        tag.clear_events()
        tag.rename(TagName(key="New", value="V"))
        assert tag.key == "New"
        assert tag.value == "V"
        events = tag.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], TagRenamed)
        assert events[0].key == "New"
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/unit/domain/workspace_config/test_tag.py -v`
Expected: FAIL — `ImportError: cannot import name 'Tag'`.

- [ ] **Step 4: Append the `Tag` aggregate to `tag.py`**

Add to the END of `backend/src/cellar/domain/workspace_config/tagging/tag.py` (add `import uuid` and the datetime/entity imports at the top with the existing imports):

```python
# --- add to the top-of-file imports block ---
import uuid
from datetime import UTC, datetime

from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.workspace_config.tagging.events import TagCreated, TagRenamed
```

```python
# --- append at end of tag.py ---
class Tag(AggregateRoot):
    """Workspace-scoped, free-form (key, optional value) tag with provenance.

    Dedup/identity is by normalized (key, value) within a workspace — enforced
    by a unique index at the persistence layer. The display casing is preserved.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        name: TagName,
        created_by: uuid.UUID,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        self.workspace_id = workspace_id
        self._name = name
        self.created_by = created_by

    @property
    def name(self) -> TagName:
        return self._name

    @property
    def key(self) -> str:
        return self._name.key

    @property
    def value(self) -> str | None:
        return self._name.value

    @property
    def normalized_key(self) -> str:
        return self._name.normalized_key

    @property
    def normalized_value(self) -> str | None:
        return self._name.normalized_value

    @classmethod
    def create(
        cls, *, workspace_id: uuid.UUID, name: TagName, created_by: uuid.UUID
    ) -> Tag:
        tag = cls(workspace_id=workspace_id, name=name, created_by=created_by)
        tag.register_event(
            TagCreated(
                aggregate_id=tag.id,
                aggregate_type="Tag",
                workspace_id=workspace_id,
                key=name.key,
                value=name.value,
            )
        )
        return tag

    def rename(self, new: TagName) -> None:
        self._name = new
        self.updated_at = datetime.now(UTC)
        self.register_event(
            TagRenamed(
                aggregate_id=self.id,
                aggregate_type="Tag",
                workspace_id=self.workspace_id,
                key=new.key,
                value=new.value,
            )
        )
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/unit/domain/workspace_config/test_tag.py tests/unit/domain/workspace_config/test_tag_name.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/domain/workspace_config/tagging/events.py \
        backend/src/cellar/domain/workspace_config/tagging/tag.py \
        backend/tests/unit/domain/workspace_config/test_tag.py
git commit -m "feat(tagging): Tag aggregate + domain events"
```

---

## Task 3: Repository protocols (domain)

**Files:**
- Create: `backend/src/cellar/domain/workspace_config/tagging/repository.py`

No test (interfaces only; concrete repos are tested in Tasks 6–8).

- [ ] **Step 1: Write the repository protocols**

Create `backend/src/cellar/domain/workspace_config/tagging/repository.py`:

```python
"""Repository protocols for the tagging capability."""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from cellar.domain.workspace_config.tagging.tag import Tag, TaggableEntityType, TagName


@runtime_checkable
class TagRepository(Protocol):
    """Registry of Tag aggregates (the deduplicated set of key/value pairs)."""

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> Tag | None: ...

    async def find_by_normalized(
        self, workspace_id: uuid.UUID, name: TagName
    ) -> Tag | None: ...

    async def get_or_create(
        self, workspace_id: uuid.UUID, name: TagName, created_by: uuid.UUID
    ) -> Tag:
        """Return the existing tag for ``name`` or create it (race-safe).

        Emits ``TagCreated`` (collected on commit) only when a new row is
        actually inserted.
        """
        ...

    async def search(
        self,
        workspace_id: uuid.UUID,
        *,
        q: str | None = None,
        created_by: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[Tag]:
        """Autocomplete / listing — substring match on normalized key/value."""
        ...

    async def save(self, aggregate: Tag) -> None: ...

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...


@runtime_checkable
class TagLinkRepository(Protocol):
    """Manages tag↔entity links for ONE taggable entity type.

    Each concrete implementation is bound to a single link table; obtain the
    right one from a ``TagLinkRepositoryProvider``.
    """

    async def add(
        self,
        workspace_id: uuid.UUID,
        entity_id: uuid.UUID,
        tag_id: uuid.UUID,
        assigned_by: uuid.UUID,
    ) -> None: ...

    async def remove(
        self, workspace_id: uuid.UUID, entity_id: uuid.UUID, tag_id: uuid.UUID
    ) -> None: ...

    async def set_for_entity(
        self,
        workspace_id: uuid.UUID,
        entity_id: uuid.UUID,
        tag_ids: list[uuid.UUID],
        assigned_by: uuid.UUID,
    ) -> None: ...

    async def find_tags_for_entity(
        self, workspace_id: uuid.UUID, entity_id: uuid.UUID
    ) -> list[Tag]: ...

    async def find_entity_ids_for_tags(
        self,
        workspace_id: uuid.UUID,
        tag_ids: list[uuid.UUID],
        *,
        match_all: bool,
    ) -> list[uuid.UUID]: ...


@runtime_checkable
class TagLinkRepositoryProvider(Protocol):
    """Resolves the right ``TagLinkRepository`` for a given entity type."""

    def for_type(self, entity_type: TaggableEntityType) -> TagLinkRepository: ...
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `uv run python -c "import cellar.domain.workspace_config.tagging.repository"`
Expected: no output, exit 0.

- [ ] **Step 3: Commit**

```bash
git add backend/src/cellar/domain/workspace_config/tagging/repository.py
git commit -m "feat(tagging): repository protocols"
```

---

## Task 4: ORM models + Alembic registration

**Files:**
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/__init__.py`
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/models.py`
- Modify: `backend/alembic/env.py`

- [ ] **Step 1: Create the package marker**

Create `backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/__init__.py` (empty).

- [ ] **Step 2: Write the ORM models**

Create `backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/models.py`:

```python
"""SQLAlchemy models for tags + per-entity link tables.

The unique index on (workspace_id, normalized_key, normalized_value) uses
``NULLS NOT DISTINCT`` (PG15+) so value-less tags dedup correctly. Trigram GIN
indexes back autocomplete. Each link table has real FKs with ON DELETE CASCADE.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from cellar.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    VersionMixin,
    WorkspaceIdMixin,
)


class TagModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Tag registry — one row per distinct (key, optional value) per workspace."""

    __tablename__ = "tags"

    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str | None] = mapped_column(String(256))
    normalized_key: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_value: Mapped[str | None] = mapped_column(String(256))
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)

    __table_args__ = (
        Index(
            "uq_tags_ws_norm",
            "workspace_id",
            "normalized_key",
            "normalized_value",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        Index(
            "ix_tags_norm_key_trgm",
            "normalized_key",
            postgresql_using="gin",
            postgresql_ops={"normalized_key": "gin_trgm_ops"},
        ),
        Index(
            "ix_tags_norm_value_trgm",
            "normalized_value",
            postgresql_using="gin",
            postgresql_ops={"normalized_value": "gin_trgm_ops"},
        ),
        Index("ix_tags_ws_created_by", "workspace_id", "created_by"),
    )


class TagLinkMixin:
    """Shared non-PK columns for every tag link table."""

    assigned_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MoleculeTagLinkModel(Base, TagLinkMixin):
    __tablename__ = "molecule_tags"

    molecule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("molecules.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (Index("ix_molecule_tags_tag_id", "tag_id"),)


class ProtocolTagLinkModel(Base, TagLinkMixin):
    __tablename__ = "protocol_tags"

    protocol_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("protocols.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (Index("ix_protocol_tags_tag_id", "tag_id"),)


class ProjectTagLinkModel(Base, TagLinkMixin):
    __tablename__ = "project_tags"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (Index("ix_project_tags_tag_id", "tag_id"),)


class CollectionTagLinkModel(Base, TagLinkMixin):
    __tablename__ = "collection_tags"

    collection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (Index("ix_collection_tags_tag_id", "tag_id"),)
```

> Note: `postgresql_nulls_not_distinct=True` on the unique `Index` requires SQLAlchemy ≥ 2.0.10. The migration (Task 5) creates the real index via raw SQL and is authoritative for the test DB; the model declaration exists for autogenerate parity. If your SQLAlchemy version rejects the kwarg at import, drop it from the model (the migration still enforces `NULLS NOT DISTINCT`).

- [ ] **Step 3: Register the model module with Alembic**

In `backend/alembic/env.py`, find the block of `import cellar.infrastructure.persistence.sqlalchemy.*.models  # noqa: F401` lines. Add this line alongside them (e.g. right after the `workspace_config.models` import):

```python
import cellar.infrastructure.persistence.sqlalchemy.tagging.models  # noqa: F401
```

- [ ] **Step 4: Verify the models import and register on the metadata**

Run: `uv run python -c "import cellar.infrastructure.persistence.sqlalchemy.tagging.models as m; from cellar.infrastructure.persistence.sqlalchemy.base import Base; print(sorted(t for t in Base.metadata.tables if 'tag' in t))"`
Expected output includes: `['collection_tags', 'molecule_tags', 'project_tags', 'protocol_tags', 'tags']`.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/__init__.py \
        backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/models.py \
        backend/alembic/env.py
git commit -m "feat(tagging): ORM models for tags + link tables"
```

---

## Task 5: Migration 047 — create schema + backfill

**Files:**
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/backfill_sql.py`
- Create: `backend/alembic/versions/047_tagging.py`

The backfill SQL lives in a frozen constants module so the migration **and** the
Task 8 test execute the identical statements (DRY). Both statements are
idempotent (`ON CONFLICT DO NOTHING`).

- [ ] **Step 1: Write the backfill SQL constants**

Create `backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/backfill_sql.py`:

```python
"""Frozen backfill SQL: migrate legacy ``molecules.tags`` strings into the tag
registry + ``molecule_tags`` links. Shared by migration 047 and its test.

Both statements are idempotent. They read ``molecules.tags`` (a JSON array of
strings), which still exists until migration 048 drops it.
"""

from __future__ import annotations

# 1) One value-less tag per distinct (workspace, normalized key). DISTINCT ON
#    picks the earliest-created molecule's casing + creator as the canonical row.
BACKFILL_TAGS_SQL = """
INSERT INTO tags
    (id, workspace_id, key, value, normalized_key, normalized_value,
     created_by, created_at, updated_at, version)
SELECT
    gen_random_uuid(), d.workspace_id, d.key, NULL,
    lower(btrim(d.key)), NULL, d.created_by, now(), now(), 1
FROM (
    SELECT DISTINCT ON (m.workspace_id, lower(btrim(elem)))
        m.workspace_id AS workspace_id,
        btrim(elem)    AS key,
        m.created_by   AS created_by
    FROM molecules m
    CROSS JOIN LATERAL json_array_elements_text(m.tags) AS elem
    WHERE m.tags IS NOT NULL AND btrim(elem) <> ''
    ORDER BY m.workspace_id, lower(btrim(elem)), m.created_at
) d
ON CONFLICT (workspace_id, normalized_key, normalized_value) DO NOTHING;
"""

# 2) One link per (molecule, tag string), joined back to the canonical tag row.
BACKFILL_LINKS_SQL = """
INSERT INTO molecule_tags (molecule_id, tag_id, assigned_by, assigned_at)
SELECT m.id, t.id, m.created_by, m.created_at
FROM molecules m
CROSS JOIN LATERAL json_array_elements_text(m.tags) AS elem
JOIN tags t
    ON t.workspace_id = m.workspace_id
   AND t.normalized_key = lower(btrim(elem))
   AND t.normalized_value IS NULL
WHERE m.tags IS NOT NULL AND btrim(elem) <> ''
ON CONFLICT (molecule_id, tag_id) DO NOTHING;
"""
```

- [ ] **Step 2: Write the migration**

Create `backend/alembic/versions/047_tagging.py` (matches the minimal style of `046`):

```python
"""047 — tagging: tags registry + per-entity link tables + backfill.

Creates the tag registry, four per-entity link tables (molecule/protocol/
project/collection), a tag_links_all UNION ALL view, and backfills the legacy
molecules.tags strings as value-less tags. The molecules.tags column is dropped
later in migration 048, after all readers are repointed.

Revision ID: 047_tagging
Revises: 046_template_used_in_collections
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from cellar.infrastructure.persistence.sqlalchemy.tagging.backfill_sql import (
    BACKFILL_LINKS_SQL,
    BACKFILL_TAGS_SQL,
)

revision = "047_tagging"
down_revision = "046_template_used_in_collections"


def _create_link_table(name: str, entity_col: str, entity_table: str) -> None:
    op.create_table(
        name,
        sa.Column(
            entity_col,
            sa.Uuid(),
            sa.ForeignKey(f"{entity_table}.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.Uuid(),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("assigned_by", sa.Uuid(), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(f"ix_{name}_tag_id", name, ["tag_id"])


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # --- tag registry ---
    op.create_table(
        "tags",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.String(length=256), nullable=True),
        sa.Column("normalized_key", sa.String(length=128), nullable=False),
        sa.Column("normalized_value", sa.String(length=256), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_tags_workspace_id", "tags", ["workspace_id"])
    op.create_index("ix_tags_ws_created_by", "tags", ["workspace_id", "created_by"])
    # Unique dedup index — NULLS NOT DISTINCT so value-less tags collapse.
    op.execute(
        "CREATE UNIQUE INDEX uq_tags_ws_norm ON tags "
        "(workspace_id, normalized_key, normalized_value) NULLS NOT DISTINCT"
    )
    # Trigram GIN indexes for autocomplete.
    op.execute(
        "CREATE INDEX ix_tags_norm_key_trgm ON tags "
        "USING gin (normalized_key gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_tags_norm_value_trgm ON tags "
        "USING gin (normalized_value gin_trgm_ops)"
    )

    # --- per-entity link tables ---
    _create_link_table("molecule_tags", "molecule_id", "molecules")
    _create_link_table("protocol_tags", "protocol_id", "protocols")
    _create_link_table("project_tags", "project_id", "projects")
    _create_link_table("collection_tags", "collection_id", "collections")

    # --- cross-type view ---
    op.execute(
        """
        CREATE VIEW tag_links_all AS
            SELECT 'Molecule' AS entity_type, molecule_id AS entity_id,
                   tag_id, assigned_by, assigned_at FROM molecule_tags
            UNION ALL
            SELECT 'Protocol', protocol_id, tag_id, assigned_by, assigned_at
                   FROM protocol_tags
            UNION ALL
            SELECT 'Project', project_id, tag_id, assigned_by, assigned_at
                   FROM project_tags
            UNION ALL
            SELECT 'Collection', collection_id, tag_id, assigned_by, assigned_at
                   FROM collection_tags
        """
    )

    # --- backfill legacy molecules.tags ---
    op.execute(BACKFILL_TAGS_SQL)
    op.execute(BACKFILL_LINKS_SQL)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS tag_links_all")
    op.drop_table("collection_tags")
    op.drop_table("project_tags")
    op.drop_table("protocol_tags")
    op.drop_table("molecule_tags")
    op.drop_table("tags")
```

- [ ] **Step 3: Apply the migration against a scratch DB to verify it runs**

If you have the dev database up (`docker compose -f docker-compose.dev.yml up -d`), run:
`uv run alembic upgrade head`
Expected: `Running upgrade 046_template_used_in_collections -> 047_tagging`. No errors.
Then sanity-check the downgrade is reversible: `uv run alembic downgrade -1 && uv run alembic upgrade head`.

(If you don't run a dev DB locally, the integration tests in Tasks 6–8 will exercise the migration via testcontainers — proceed and rely on those.)

- [ ] **Step 4: Commit**

```bash
git add backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/backfill_sql.py \
        backend/alembic/versions/047_tagging.py
git commit -m "feat(tagging): migration 047 — tag schema + molecule-tag backfill"
```

---

## Task 6: `SQLAlchemyTagRepository`

**Files:**
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/tag_repository.py`
- Test: `backend/tests/integration/test_tagging.py` (create file; add the `TestTagRepository` class)

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/integration/test_tagging.py`:

```python
"""Integration tests for tagging persistence (tag registry + links + backfill)."""

from __future__ import annotations

import uuid

from sqlalchemy import text

from cellar.domain.workspace_config.tagging.events import TagCreated
from cellar.domain.workspace_config.tagging.tag import TagName
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_repository import (
    SQLAlchemyTagRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class TestTagRepository:
    async def test_get_or_create_inserts_and_emits_event(
        self, uow: AsyncUnitOfWork
    ) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            tag = await repo.get_or_create(ws_id, TagName(key="Project", value="Alpha"), user_id)
            events = await uow.commit()
        assert tag.key == "Project"
        assert tag.value == "Alpha"
        assert any(isinstance(e, TagCreated) for e in events)

    async def test_get_or_create_dedups_case_insensitively(
        self, uow: AsyncUnitOfWork
    ) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            first = await repo.get_or_create(ws_id, TagName(key="Env", value="Prod"), user_id)
            await uow.commit()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            second = await repo.get_or_create(ws_id, TagName(key="env", value="prod"), user_id)
            events = await uow.commit()
        assert first.id == second.id  # same registry row
        assert not [e for e in events if isinstance(e, TagCreated)]  # no second create

    async def test_valueless_tags_dedup(self, uow: AsyncUnitOfWork) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            a = await repo.get_or_create(ws_id, TagName(key="favorite"), user_id)
            await uow.commit()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            b = await repo.get_or_create(ws_id, TagName(key="FAVORITE"), user_id)
            await uow.commit()
        assert a.id == b.id

    async def test_same_name_distinct_across_workspaces(
        self, uow: AsyncUnitOfWork
    ) -> None:
        ws_a, ws_b, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            ta = await repo.get_or_create(ws_a, TagName(key="shared"), user_id)
            tb = await repo.get_or_create(ws_b, TagName(key="shared"), user_id)
            await uow.commit()
        assert ta.id != tb.id

    async def test_search_substring_and_created_by(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        alice, bob = uuid.uuid4(), uuid.uuid4()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            await repo.get_or_create(ws_id, TagName(key="kinase"), alice)
            await repo.get_or_create(ws_id, TagName(key="kinetics"), bob)
            await repo.get_or_create(ws_id, TagName(key="solubility"), alice)
            await uow.commit()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            kin = await repo.search(ws_id, q="kin")
            mine = await repo.search(ws_id, created_by=alice)
        assert {t.key for t in kin} == {"kinase", "kinetics"}
        assert {t.key for t in mine} == {"kinase", "solubility"}

    async def test_find_by_id_in_workspace_scoping(self, uow: AsyncUnitOfWork) -> None:
        ws_id, other_ws, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            tag = await repo.get_or_create(ws_id, TagName(key="x"), user_id)
            await uow.commit()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            assert await repo.find_by_id_in_workspace(ws_id, tag.id) is not None
            assert await repo.find_by_id_in_workspace(other_ws, tag.id) is None
```

- [ ] **Step 2: Run to verify it fails**

Run (Docker must be running for testcontainers): `uv run pytest tests/integration/test_tagging.py -v`
Expected: FAIL — `ModuleNotFoundError: …tag_repository`.

- [ ] **Step 3: Write the repository**

Create `backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/tag_repository.py`:

```python
"""SQLAlchemy repository for Tag aggregates (registry)."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from cellar.domain.workspace_config.tagging.tag import Tag, TagName
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.models import TagModel


def tag_model_to_domain(model: TagModel) -> Tag:
    """Map a TagModel row to a Tag aggregate. Shared with the link repository."""
    return Tag(
        id=model.id,
        workspace_id=model.workspace_id,
        name=TagName(key=model.key, value=model.value),
        created_by=model.created_by,
        created_at=model.created_at,
        updated_at=model.updated_at,
        version=model.version,
    )


class SQLAlchemyTagRepository(SQLAlchemyRepository[Tag, TagModel]):
    model_class = TagModel

    def _to_domain(self, model: TagModel) -> Tag:
        return tag_model_to_domain(model)

    def _to_model(self, aggregate: Tag) -> TagModel:
        return TagModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            key=aggregate.key,
            value=aggregate.value,
            normalized_key=aggregate.normalized_key,
            normalized_value=aggregate.normalized_value,
            created_by=aggregate.created_by,
            version=aggregate.version,
        )

    def _update_model(self, model: TagModel, aggregate: Tag) -> None:
        model.key = aggregate.key
        model.value = aggregate.value
        model.normalized_key = aggregate.normalized_key
        model.normalized_value = aggregate.normalized_value

    async def find_by_normalized(
        self, workspace_id: uuid.UUID, name: TagName
    ) -> Tag | None:
        stmt = select(TagModel).where(
            TagModel.workspace_id == workspace_id,
            TagModel.normalized_key == name.normalized_key,
            TagModel.normalized_value.is_not_distinct_from(name.normalized_value),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain_tracked(model) if model else None

    async def get_or_create(
        self, workspace_id: uuid.UUID, name: TagName, created_by: uuid.UUID
    ) -> Tag:
        existing = await self.find_by_normalized(workspace_id, name)
        if existing is not None:
            return existing

        tag = Tag.create(workspace_id=workspace_id, name=name, created_by=created_by)
        stmt = (
            pg_insert(TagModel)
            .values(
                id=tag.id,
                workspace_id=workspace_id,
                key=tag.key,
                value=tag.value,
                normalized_key=tag.normalized_key,
                normalized_value=tag.normalized_value,
                created_by=created_by,
                version=tag.version,
            )
            .on_conflict_do_nothing(
                index_elements=["workspace_id", "normalized_key", "normalized_value"]
            )
        )
        result = await self._session.execute(stmt)
        if result.rowcount == 0:
            # Lost the race — another tx created it. Return the winner, no event.
            tag.clear_events()
            winner = await self.find_by_normalized(workspace_id, name)
            assert winner is not None
            return winner

        self._uow.track(tag)  # so TagCreated is collected on commit
        return tag

    async def search(
        self,
        workspace_id: uuid.UUID,
        *,
        q: str | None = None,
        created_by: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[Tag]:
        stmt = select(TagModel).where(TagModel.workspace_id == workspace_id)
        if q and q.strip():
            pattern = f"%{q.strip().casefold()}%"
            stmt = stmt.where(
                or_(
                    TagModel.normalized_key.like(pattern),
                    TagModel.normalized_value.like(pattern),
                )
            )
        if created_by is not None:
            stmt = stmt.where(TagModel.created_by == created_by)
        stmt = stmt.order_by(
            TagModel.normalized_key, TagModel.normalized_value, TagModel.id
        ).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars()]

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        stmt = delete(TagModel).where(
            TagModel.workspace_id == workspace_id, TagModel.id == id
        )
        await self._session.execute(stmt)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/integration/test_tagging.py::TestTagRepository -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/tag_repository.py \
        backend/tests/integration/test_tagging.py
git commit -m "feat(tagging): SQLAlchemyTagRepository with race-safe get_or_create"
```

---

## Task 7: `SQLAlchemyTagLinkRepository` (base + 4 subclasses + factory)

**Files:**
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/tag_link_repository.py`
- Test: `backend/tests/integration/test_tagging.py` (add `TestTagLinkRepository` class)

- [ ] **Step 1: Write the failing integration test**

Append to `backend/tests/integration/test_tagging.py` (add imports at top, then the class):

```python
# --- add to the imports at the top of tests/integration/test_tagging.py ---
from cellar.domain.workspace_config.tagging.tag import TaggableEntityType
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_link_repository import (
    get_tag_link_repository,
)
```

```python
async def _insert_molecule(
    uow: AsyncUnitOfWork, workspace_id: uuid.UUID, reg: str
) -> uuid.UUID:
    """Insert a minimal molecules row (status columns have server defaults)."""
    mol_id = uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO molecules (id, workspace_id, registration_number, name, "
            "molecule_type, version) VALUES (:id, :ws, :reg, :name, :mtype, 1)"
        ),
        {"id": mol_id, "ws": workspace_id, "reg": reg, "name": reg, "mtype": "small_molecule"},
    )
    return mol_id


class TestTagLinkRepository:
    async def test_add_find_remove(self, uow: AsyncUnitOfWork) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            tag = await tag_repo.get_or_create(ws_id, TagName(key="hit"), user_id)
            mol_id = await _insert_molecule(uow, ws_id, "REG-1")
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            await link_repo.add(ws_id, mol_id, tag.id, user_id)
            await uow.commit()
        async with uow:
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            tags = await link_repo.find_tags_for_entity(ws_id, mol_id)
            assert [t.key for t in tags] == ["hit"]
            await link_repo.remove(ws_id, mol_id, tag.id)
            await uow.commit()
        async with uow:
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            assert await link_repo.find_tags_for_entity(ws_id, mol_id) == []

    async def test_add_is_idempotent(self, uow: AsyncUnitOfWork) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            tag = await tag_repo.get_or_create(ws_id, TagName(key="x"), user_id)
            mol_id = await _insert_molecule(uow, ws_id, "REG-2")
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            await link_repo.add(ws_id, mol_id, tag.id, user_id)
            await link_repo.add(ws_id, mol_id, tag.id, user_id)
            await uow.commit()
        async with uow:
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            assert len(await link_repo.find_tags_for_entity(ws_id, mol_id)) == 1

    async def test_add_noop_when_entity_in_other_workspace(
        self, uow: AsyncUnitOfWork
    ) -> None:
        ws_id, other_ws, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            tag = await tag_repo.get_or_create(ws_id, TagName(key="x"), user_id)
            mol_id = await _insert_molecule(uow, ws_id, "REG-3")
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            await link_repo.add(other_ws, mol_id, tag.id, user_id)  # wrong ws → no-op
            await uow.commit()
        async with uow:
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            assert await link_repo.find_tags_for_entity(ws_id, mol_id) == []

    async def test_find_entity_ids_any_and_all(self, uow: AsyncUnitOfWork) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            t1 = await tag_repo.get_or_create(ws_id, TagName(key="a"), user_id)
            t2 = await tag_repo.get_or_create(ws_id, TagName(key="b"), user_id)
            m1 = await _insert_molecule(uow, ws_id, "M1")
            m2 = await _insert_molecule(uow, ws_id, "M2")
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            await link_repo.add(ws_id, m1, t1.id, user_id)
            await link_repo.add(ws_id, m1, t2.id, user_id)
            await link_repo.add(ws_id, m2, t1.id, user_id)
            await uow.commit()
        async with uow:
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            any_ids = await link_repo.find_entity_ids_for_tags(
                ws_id, [t1.id, t2.id], match_all=False
            )
            all_ids = await link_repo.find_entity_ids_for_tags(
                ws_id, [t1.id, t2.id], match_all=True
            )
        assert set(any_ids) == {m1, m2}
        assert set(all_ids) == {m1}

    async def test_set_for_entity_reconciles(self, uow: AsyncUnitOfWork) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            t1 = await tag_repo.get_or_create(ws_id, TagName(key="a"), user_id)
            t2 = await tag_repo.get_or_create(ws_id, TagName(key="b"), user_id)
            t3 = await tag_repo.get_or_create(ws_id, TagName(key="c"), user_id)
            mol_id = await _insert_molecule(uow, ws_id, "M-set")
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            await link_repo.set_for_entity(ws_id, mol_id, [t1.id, t2.id], user_id)
            await uow.commit()
        async with uow:
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            await link_repo.set_for_entity(ws_id, mol_id, [t2.id, t3.id], user_id)
            await uow.commit()
        async with uow:
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            keys = {t.key for t in await link_repo.find_tags_for_entity(ws_id, mol_id)}
        assert keys == {"b", "c"}

    async def test_cascade_on_molecule_delete(self, uow: AsyncUnitOfWork) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            tag = await tag_repo.get_or_create(ws_id, TagName(key="x"), user_id)
            mol_id = await _insert_molecule(uow, ws_id, "M-del")
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            await link_repo.add(ws_id, mol_id, tag.id, user_id)
            await uow.commit()
        async with uow:
            await uow.session.execute(
                text("DELETE FROM molecules WHERE id = :id"), {"id": mol_id}
            )
            await uow.commit()
        async with uow:
            res = await uow.session.execute(
                text("SELECT count(*) FROM molecule_tags WHERE molecule_id = :id"),
                {"id": mol_id},
            )
            assert res.scalar_one() == 0

    async def test_cascade_on_tag_delete(self, uow: AsyncUnitOfWork) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            tag = await tag_repo.get_or_create(ws_id, TagName(key="x"), user_id)
            mol_id = await _insert_molecule(uow, ws_id, "M-tagdel")
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            await link_repo.add(ws_id, mol_id, tag.id, user_id)
            await uow.commit()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            await tag_repo.delete(ws_id, tag.id)
            await uow.commit()
        async with uow:
            res = await uow.session.execute(
                text("SELECT count(*) FROM molecule_tags WHERE tag_id = :id"),
                {"id": tag.id},
            )
            assert res.scalar_one() == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/integration/test_tagging.py::TestTagLinkRepository -v`
Expected: FAIL — `ModuleNotFoundError: …tag_link_repository`.

- [ ] **Step 3: Write the link repository**

Create `backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/tag_link_repository.py`:

```python
"""Lightweight (non-aggregate) repositories for tag↔entity links.

One generic base, four type-bound subclasses, and a factory. Mirrors
SQLAlchemyProjectMemberRepository: direct SQL, on_conflict_do_nothing,
workspace defense via a subquery to the entity table.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, distinct, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from cellar.domain.workspace_config.tagging.tag import Tag, TaggableEntityType
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CollectionModel,
    ProjectModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    ProtocolModel,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.models import (
    CollectionTagLinkModel,
    MoleculeTagLinkModel,
    ProjectTagLinkModel,
    ProtocolTagLinkModel,
    TagModel,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_repository import (
    tag_model_to_domain,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyTagLinkRepository:
    """Base for a single link table. Subclasses set the three class attributes."""

    link_model: type
    entity_model: type
    entity_id_attr: str

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    @property
    def _session(self):  # noqa: ANN202 - AsyncSession
        return self._uow.session

    @property
    def _entity_col(self):  # noqa: ANN202 - InstrumentedAttribute
        return getattr(self.link_model, self.entity_id_attr)

    async def _entity_in_workspace(
        self, workspace_id: uuid.UUID, entity_id: uuid.UUID
    ) -> bool:
        stmt = select(self.entity_model.id).where(
            self.entity_model.id == entity_id,
            self.entity_model.workspace_id == workspace_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def add(
        self,
        workspace_id: uuid.UUID,
        entity_id: uuid.UUID,
        tag_id: uuid.UUID,
        assigned_by: uuid.UUID,
    ) -> None:
        if not await self._entity_in_workspace(workspace_id, entity_id):
            return
        stmt = (
            pg_insert(self.link_model)
            .values(
                **{self.entity_id_attr: entity_id},
                tag_id=tag_id,
                assigned_by=assigned_by,
            )
            .on_conflict_do_nothing()
        )
        await self._session.execute(stmt)

    async def remove(
        self, workspace_id: uuid.UUID, entity_id: uuid.UUID, tag_id: uuid.UUID
    ) -> None:
        if not await self._entity_in_workspace(workspace_id, entity_id):
            return
        stmt = delete(self.link_model).where(
            self._entity_col == entity_id, self.link_model.tag_id == tag_id
        )
        await self._session.execute(stmt)

    async def set_for_entity(
        self,
        workspace_id: uuid.UUID,
        entity_id: uuid.UUID,
        tag_ids: list[uuid.UUID],
        assigned_by: uuid.UUID,
    ) -> None:
        if not await self._entity_in_workspace(workspace_id, entity_id):
            return
        del_stmt = delete(self.link_model).where(self._entity_col == entity_id)
        if tag_ids:
            del_stmt = del_stmt.where(self.link_model.tag_id.not_in(tag_ids))
        await self._session.execute(del_stmt)
        for tag_id in tag_ids:
            stmt = (
                pg_insert(self.link_model)
                .values(
                    **{self.entity_id_attr: entity_id},
                    tag_id=tag_id,
                    assigned_by=assigned_by,
                )
                .on_conflict_do_nothing()
            )
            await self._session.execute(stmt)

    async def find_tags_for_entity(
        self, workspace_id: uuid.UUID, entity_id: uuid.UUID
    ) -> list[Tag]:
        stmt = (
            select(TagModel)
            .join(self.link_model, TagModel.id == self.link_model.tag_id)
            .where(self._entity_col == entity_id, TagModel.workspace_id == workspace_id)
            .order_by(TagModel.normalized_key, TagModel.normalized_value)
        )
        result = await self._session.execute(stmt)
        return [tag_model_to_domain(m) for m in result.scalars()]

    async def find_entity_ids_for_tags(
        self,
        workspace_id: uuid.UUID,
        tag_ids: list[uuid.UUID],
        *,
        match_all: bool,
    ) -> list[uuid.UUID]:
        if not tag_ids:
            return []
        unique_ids = list(set(tag_ids))
        col = self._entity_col
        stmt = (
            select(col)
            .join(self.entity_model, self.entity_model.id == col)
            .where(
                self.link_model.tag_id.in_(unique_ids),
                self.entity_model.workspace_id == workspace_id,
            )
        )
        if match_all:
            stmt = stmt.group_by(col).having(
                func.count(distinct(self.link_model.tag_id)) == len(unique_ids)
            )
        else:
            stmt = stmt.distinct()
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class MoleculeTagLinkRepository(SQLAlchemyTagLinkRepository):
    link_model = MoleculeTagLinkModel
    entity_model = MoleculeModel
    entity_id_attr = "molecule_id"


class ProtocolTagLinkRepository(SQLAlchemyTagLinkRepository):
    link_model = ProtocolTagLinkModel
    entity_model = ProtocolModel
    entity_id_attr = "protocol_id"


class ProjectTagLinkRepository(SQLAlchemyTagLinkRepository):
    link_model = ProjectTagLinkModel
    entity_model = ProjectModel
    entity_id_attr = "project_id"


class CollectionTagLinkRepository(SQLAlchemyTagLinkRepository):
    link_model = CollectionTagLinkModel
    entity_model = CollectionModel
    entity_id_attr = "collection_id"


_REGISTRY: dict[TaggableEntityType, type[SQLAlchemyTagLinkRepository]] = {
    TaggableEntityType.MOLECULE: MoleculeTagLinkRepository,
    TaggableEntityType.PROTOCOL: ProtocolTagLinkRepository,
    TaggableEntityType.PROJECT: ProjectTagLinkRepository,
    TaggableEntityType.COLLECTION: CollectionTagLinkRepository,
}


def get_tag_link_repository(
    entity_type: TaggableEntityType, uow: AsyncUnitOfWork
) -> SQLAlchemyTagLinkRepository:
    """Factory: the link repository bound to ``entity_type``'s table."""
    return _REGISTRY[entity_type](uow)
```

> Verify the imported ORM class names (`MoleculeModel`, `ProtocolModel`, `ProjectModel`, `CollectionModel`) match the actual class names in their `models.py` modules; adjust the imports if a name differs.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/integration/test_tagging.py::TestTagLinkRepository -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/tag_link_repository.py \
        backend/tests/integration/test_tagging.py
git commit -m "feat(tagging): per-entity tag link repositories + factory"
```

---

## Task 8: Backfill integration test

Proves migration 047's backfill correctly turns legacy `molecules.tags` strings
into value-less tags + links, with case-insensitive dedup. Runs the same frozen
SQL the migration uses.

**Files:**
- Test: `backend/tests/integration/test_tagging.py` (add `TestBackfill` class)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/integration/test_tagging.py` (add the import, then the class):

```python
# --- add to imports at top ---
from cellar.infrastructure.persistence.sqlalchemy.tagging.backfill_sql import (
    BACKFILL_LINKS_SQL,
    BACKFILL_TAGS_SQL,
)
```

```python
class TestBackfill:
    async def test_backfill_creates_tags_and_links_with_dedup(
        self, uow: AsyncUnitOfWork
    ) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        # Two molecules sharing a tag (different casing) + one unique tag.
        m1, m2 = uuid.uuid4(), uuid.uuid4()
        async with uow:
            await uow.session.execute(
                text(
                    "INSERT INTO molecules (id, workspace_id, registration_number, "
                    "name, molecule_type, version, tags, created_by) VALUES "
                    "(:id, :ws, :reg, :name, 'small_molecule', 1, "
                    "CAST(:tags AS json), :uid)"
                ),
                {"id": m1, "ws": ws_id, "reg": "BF-1", "name": "BF-1",
                 "tags": '["Kinase", "hit"]', "uid": user_id},
            )
            await uow.session.execute(
                text(
                    "INSERT INTO molecules (id, workspace_id, registration_number, "
                    "name, molecule_type, version, tags, created_by) VALUES "
                    "(:id, :ws, :reg, :name, 'small_molecule', 1, "
                    "CAST(:tags AS json), :uid)"
                ),
                {"id": m2, "ws": ws_id, "reg": "BF-2", "name": "BF-2",
                 "tags": '["kinase"]', "uid": user_id},
            )
            await uow.session.execute(text(BACKFILL_TAGS_SQL))
            await uow.session.execute(text(BACKFILL_LINKS_SQL))
            await uow.commit()

        async with uow:
            # "Kinase"/"kinase" dedup to one tag; "hit" is a second.
            res = await uow.session.execute(
                text(
                    "SELECT count(*) FROM tags WHERE workspace_id = :ws "
                    "AND normalized_key IN ('kinase', 'hit')"
                ),
                {"ws": ws_id},
            )
            assert res.scalar_one() == 2
            # m1 has 2 links, m2 has 1, both pointing at the shared kinase tag.
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            m1_keys = {t.key for t in await link_repo.find_tags_for_entity(ws_id, m1)}
            m2_keys = {t.key for t in await link_repo.find_tags_for_entity(ws_id, m2)}
            assert m1_keys == {"Kinase", "hit"}
            assert m2_keys == {"Kinase"}  # canonical casing from earliest molecule

    async def test_backfill_is_idempotent(self, uow: AsyncUnitOfWork) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        m1 = uuid.uuid4()
        async with uow:
            await uow.session.execute(
                text(
                    "INSERT INTO molecules (id, workspace_id, registration_number, "
                    "name, molecule_type, version, tags, created_by) VALUES "
                    "(:id, :ws, :reg, :name, 'small_molecule', 1, "
                    "CAST(:tags AS json), :uid)"
                ),
                {"id": m1, "ws": ws_id, "reg": "BF-3", "name": "BF-3",
                 "tags": '["solubility"]', "uid": user_id},
            )
            for _ in range(2):  # run twice — ON CONFLICT DO NOTHING
                await uow.session.execute(text(BACKFILL_TAGS_SQL))
                await uow.session.execute(text(BACKFILL_LINKS_SQL))
            await uow.commit()
        async with uow:
            res = await uow.session.execute(
                text(
                    "SELECT count(*) FROM tags WHERE workspace_id = :ws "
                    "AND normalized_key = 'solubility'"
                ),
                {"ws": ws_id},
            )
            assert res.scalar_one() == 1
```

- [ ] **Step 2: Run to verify it passes**

Run: `uv run pytest tests/integration/test_tagging.py::TestBackfill -v`
Expected: PASS (2 tests). (The schema + canonical-casing logic already exist from migration 047 + the frozen SQL; this test asserts they behave correctly.)

> If `test_backfill_creates_tags_and_links_with_dedup` fails on the canonical casing assertion (`m2_keys == {"Kinase"}`), confirm the `DISTINCT ON … ORDER BY … m.created_at` in `BACKFILL_TAGS_SQL` picks the earliest molecule — m1 (BF-1) is inserted first but both rows get `now()`; if casing is nondeterministic in your run, make it deterministic by also adding `, m.id` to the `ORDER BY` and asserting against whichever casing that yields. This is a test-determinism fix, not a logic bug.

- [ ] **Step 3: Run the full tagging integration suite**

Run: `uv run pytest tests/integration/test_tagging.py -v`
Expected: PASS (all classes — TagRepository, TagLinkRepository, Backfill).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/integration/test_tagging.py
git commit -m "test(tagging): migration 047 backfill integration tests"
```

---

## Phase 1 Done — Definition of Done

- [ ] `uv run pytest tests/unit/domain/workspace_config/test_tag_name.py tests/unit/domain/workspace_config/test_tag.py -v` → all pass.
- [ ] `uv run pytest tests/integration/test_tagging.py -v` → all pass (Docker running).
- [ ] `uv run alembic upgrade head` then `uv run alembic downgrade -1` then `uv run alembic upgrade head` → clean (if a dev DB is available).
- [ ] No new lint/type errors introduced in the touched files (run the repo's configured linter/type-checker).

**Delivered:** A `Tag` aggregate + registry repository with race-safe, case-insensitive `get_or_create` and autocomplete `search`; four per-entity link tables with cascade + a generic link repository + factory; a `tag_links_all` view; and migration 047 that creates the schema and backfills existing molecule tags (legacy `molecules.tags` column intentionally retained until Phase 3).

**Next (Phase 2 — Application + API, written after this lands):** `AssignTag` / `UnassignTag` / `SetEntityTags` / `ListTags` / `GetTagsForEntity` use cases (emitting `TagAssigned`/`TagUnassigned` for audit), DI wiring, and the nested assignment + management API routes with tests.

---

## Implementation Notes — deviations discovered during execution (2026-06-02)

Phase 1 was executed via subagent-driven development. Running against the live dev DB + testcontainers surfaced three facts the plan got wrong; all were fixed in code, and the final state is recorded here so Phases 2–3 don't re-trip on them:

1. **`molecules` has no `created_by` column.** `EntityModelMixin` provides only `id`/`created_at`/`updated_at`, and `MoleculeModel` adds no creator column (the `created_by` in that module belongs to `MoleculeRelationshipModel`). The backfill (`backfill_sql.py`) therefore stamps a sentinel zero UUID (`00000000-0000-0000-0000-000000000000`) as `tags.created_by` / `molecule_tags.assigned_by` for migrated rows.
2. **`molecules.tags` stores JSON `null` scalars** (~61k rows in the dev vault), which `WHERE tags IS NOT NULL` does not exclude. The backfill guards with `WHERE json_typeof(m.tags) = 'array'` — a base-relation restriction applied (proven via `EXPLAIN`) before the `LATERAL json_array_elements_text`, so scalar/null rows never reach the set-returning function.
3. **`molecules.originating_org_id` is a NOT-NULL FK to `organizations`.** The `_insert_molecule` test helper seeds a minimal org per (fresh) workspace and supplies `originating_org_id`.

**Bonus finding (de-risks §7/§14 of the spec):** the existing `keyword_list` search criterion (`_field_clauses.py`) filters `registration_number`/`inchi_key`/`name`/`uuid` — **not** `Molecule.tags`. So the Phase 3 "readers to repoint before dropping `molecules.tags`" list is just the UI/serializer fields + the CDD import mapping; no `keyword_list` search-DSL change is needed.

**Minor follow-ups for Phase 2:** `TagLinkRepositoryProvider` (protocol) is currently a forward-declaration — wire DI to it or drop it. `search()` uses `LIKE %…%`; the trigram GIN indexes accelerate ≥3-char patterns but very short autocomplete queries fall back to a scan (fine at current scale; revisit if load-tested).

**Final state:** 8 commits (`32b24c68`…`ef54da0d`), 17 unit + 15 integration tagging tests green, full backend unit suite (2588) green. Reviewed READY TO MERGE.
