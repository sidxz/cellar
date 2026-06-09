# Favorites Primitive (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable, per-user, server-side `Favorite` ("pin") primitive in a new `personalization` bounded context, plus a generic frontend `useFavorites` hook — so any entity can be favorited (projects first).

**Architecture:** A tiny `Favorite` aggregate holds only a *soft* polymorphic reference (`entity_type` string + `entity_id` UUID) — it never imports another context's aggregate, so it has zero cross-context coupling. Full DDD layers (domain → persistence → application → interface), workspace-scoped, auth-guarded. The frontend gets one generic `useFavorites(entityType)` + `useToggleFavorite(entityType)` hook reusable anywhere. No domain events (personal preference, not regulated data — deliberate departure from the events-for-side-effects default).

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy 2.0 async / Alembic / Lagom DI / dry-python returns (Railway) · Next.js / React 19 / TanStack Query v5 / orval.

**Spec:** `docs/superpowers/specs/2026-06-07-projects-folder-dashboard-design.md` (Phase 1).

**Verified facts:** Alembic head = `053_target_link_restrict` → new revision `054_favorites`. Base + mixins at `cellar.infrastructure.persistence.sqlalchemy.base` (`Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin`). Repo base `SQLAlchemyRepository[T, ModelType]` ctor takes `uow`, exposes `self._session`, `_to_domain_tracked`, `save`, `find_by_id_in_workspace`. DI registered in `infrastructure/di/container.py`; dep aliases in `interface/dependencies/`; routers mounted in `interface/app.py`.

---

## Task 1: Domain layer (enums, aggregate, repository protocol)

**Files:**
- Create: `backend/src/cellar/domain/personalization/__init__.py`
- Create: `backend/src/cellar/domain/personalization/enums.py`
- Create: `backend/src/cellar/domain/personalization/favorite.py`
- Create: `backend/src/cellar/domain/personalization/repository.py`
- Test: `backend/tests/unit/domain/personalization/test_favorite.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/domain/personalization/test_favorite.py`:

```python
"""Tests for the Favorite aggregate."""

import uuid

from cellar.domain.personalization.enums import FavoriteEntityType
from cellar.domain.personalization.favorite import Favorite


def test_create_sets_fields() -> None:
    ws, user, entity = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    fav = Favorite.create(
        workspace_id=ws,
        user_id=user,
        entity_type=FavoriteEntityType.PROJECT,
        entity_id=entity,
    )
    assert fav.workspace_id == ws
    assert fav.user_id == user
    assert fav.entity_type is FavoriteEntityType.PROJECT
    assert fav.entity_id == entity
    assert fav.version == 1
    assert fav.id is not None


def test_create_emits_no_events() -> None:
    fav = Favorite.create(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        entity_type=FavoriteEntityType.PROJECT,
        entity_id=uuid.uuid4(),
    )
    assert fav.collect_events() == []


def test_entity_type_is_str_enum() -> None:
    assert FavoriteEntityType.PROJECT == "project"
    assert FavoriteEntityType("project") is FavoriteEntityType.PROJECT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/domain/personalization/test_favorite.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cellar.domain.personalization'`

- [ ] **Step 3: Create the package + enums**

Create `backend/src/cellar/domain/personalization/__init__.py` (empty file).

Create `backend/src/cellar/domain/personalization/enums.py`:

```python
"""Enums for the Personalization bounded context."""

from __future__ import annotations

from enum import StrEnum


class FavoriteEntityType(StrEnum):
    """Kinds of entity a user can favorite.

    Open by extension — add a value as each module adopts favorites
    (``molecule``, ``protocol``, ``collection``, ``campaign`` …). Stored as
    the string value in the ``favorites.entity_type`` column.
    """

    PROJECT = "project"
```

- [ ] **Step 4: Create the aggregate**

Create `backend/src/cellar/domain/personalization/favorite.py`:

```python
"""Favorite aggregate — a per-user bookmark ("pin") of any entity."""

from __future__ import annotations

import uuid
from datetime import datetime

from cellar.domain.personalization.enums import FavoriteEntityType
from cellar.domain.shared.entity import AggregateRoot


class Favorite(AggregateRoot):
    """A user's favorite of a single entity.

    Holds only a *soft* reference — ``entity_type`` + ``entity_id`` — so the
    Personalization context never depends on the favorited entity's context.
    Immutable once created: favorites are added and removed, never edited.
    No domain events: a personal preference, not regulated/audited data.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        entity_type: FavoriteEntityType,
        entity_id: uuid.UUID,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        self.workspace_id = workspace_id
        self.user_id = user_id
        self.entity_type = entity_type
        self.entity_id = entity_id

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        entity_type: FavoriteEntityType,
        entity_id: uuid.UUID,
    ) -> Favorite:
        return cls(
            workspace_id=workspace_id,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )
```

- [ ] **Step 5: Create the repository protocol**

Create `backend/src/cellar/domain/personalization/repository.py`:

```python
"""Repository protocol for Favorite aggregates."""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from cellar.domain.personalization.enums import FavoriteEntityType
from cellar.domain.personalization.favorite import Favorite


@runtime_checkable
class FavoriteRepository(Protocol):
    async def save(self, aggregate: Favorite) -> None: ...

    async def find_by_entity(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        entity_type: FavoriteEntityType,
        entity_id: uuid.UUID,
    ) -> Favorite | None: ...

    async def list_for_user(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        entity_type: FavoriteEntityType,
    ) -> list[Favorite]: ...

    async def remove(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        entity_type: FavoriteEntityType,
        entity_id: uuid.UUID,
    ) -> None: ...
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/domain/personalization/test_favorite.py -v`
Expected: PASS (3 passed)

- [ ] **Step 7: Commit**

```bash
git add backend/src/cellar/domain/personalization backend/tests/unit/domain/personalization
git commit -m "feat(personalization): add Favorite domain aggregate"
```

---

## Task 2: Persistence layer (model, migration, repository)

**Files:**
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/personalization/__init__.py`
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/personalization/models.py`
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/personalization/favorite_repository.py`
- Create: `backend/alembic/versions/054_favorites.py`
- Test: `backend/tests/integration/persistence/personalization/test_favorite_repository.py`

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/integration/persistence/personalization/test_favorite_repository.py`:

```python
"""Integration tests for SQLAlchemyFavoriteRepository."""

from __future__ import annotations

import uuid

import pytest

from cellar.domain.personalization.enums import FavoriteEntityType
from cellar.domain.personalization.favorite import Favorite
from cellar.infrastructure.persistence.sqlalchemy.personalization.favorite_repository import (
    SQLAlchemyFavoriteRepository,
)

pytestmark = pytest.mark.integration


def _fav(ws: uuid.UUID, user: uuid.UUID, entity: uuid.UUID) -> Favorite:
    return Favorite.create(
        workspace_id=ws,
        user_id=user,
        entity_type=FavoriteEntityType.PROJECT,
        entity_id=entity,
    )


async def test_save_and_find_by_entity(uow) -> None:
    ws, user, entity = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with uow:
        repo = SQLAlchemyFavoriteRepository(uow)
        await repo.save(_fav(ws, user, entity))
        await uow.commit()

    async with uow:
        repo = SQLAlchemyFavoriteRepository(uow)
        found = await repo.find_by_entity(ws, user, FavoriteEntityType.PROJECT, entity)

    assert found is not None
    assert found.entity_id == entity


async def test_list_for_user_scopes_to_user_and_type(uow) -> None:
    ws, user_a, user_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    e1, e2, e3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with uow:
        repo = SQLAlchemyFavoriteRepository(uow)
        await repo.save(_fav(ws, user_a, e1))
        await repo.save(_fav(ws, user_a, e2))
        await repo.save(_fav(ws, user_b, e3))
        await uow.commit()

    async with uow:
        repo = SQLAlchemyFavoriteRepository(uow)
        a_favs = await repo.list_for_user(ws, user_a, FavoriteEntityType.PROJECT)

    assert {f.entity_id for f in a_favs} == {e1, e2}


async def test_remove_deletes_the_row(uow) -> None:
    ws, user, entity = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with uow:
        repo = SQLAlchemyFavoriteRepository(uow)
        await repo.save(_fav(ws, user, entity))
        await uow.commit()

    async with uow:
        repo = SQLAlchemyFavoriteRepository(uow)
        await repo.remove(ws, user, FavoriteEntityType.PROJECT, entity)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyFavoriteRepository(uow)
        found = await repo.find_by_entity(ws, user, FavoriteEntityType.PROJECT, entity)

    assert found is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/integration/persistence/personalization/test_favorite_repository.py -v`
Expected: FAIL — `ModuleNotFoundError` for the repository module.

- [ ] **Step 3: Create the SQLAlchemy model**

Create `backend/src/cellar/infrastructure/persistence/sqlalchemy/personalization/__init__.py` (empty file).

Create `backend/src/cellar/infrastructure/persistence/sqlalchemy/personalization/models.py`:

```python
"""SQLAlchemy model for the Personalization context."""

from __future__ import annotations

import uuid

from sqlalchemy import Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from cellar.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    VersionMixin,
    WorkspaceIdMixin,
)


class FavoriteModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """A user's favorite (pin) of an entity — soft polymorphic reference."""

    __tablename__ = "favorites"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)

    __table_args__ = (
        Index(
            "uq_favorites_user_entity",
            "user_id",
            "workspace_id",
            "entity_type",
            "entity_id",
            unique=True,
        ),
        Index("ix_favorites_user_type", "user_id", "workspace_id", "entity_type"),
    )
```

- [ ] **Step 4: Create the repository**

Create `backend/src/cellar/infrastructure/persistence/sqlalchemy/personalization/favorite_repository.py`:

```python
"""SQLAlchemy repository for Favorite aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from cellar.domain.personalization.enums import FavoriteEntityType
from cellar.domain.personalization.favorite import Favorite
from cellar.infrastructure.persistence.sqlalchemy.base_repository import SQLAlchemyRepository
from cellar.infrastructure.persistence.sqlalchemy.personalization.models import FavoriteModel


class SQLAlchemyFavoriteRepository(SQLAlchemyRepository[Favorite, FavoriteModel]):
    model_class = FavoriteModel

    def _to_domain(self, model: FavoriteModel) -> Favorite:
        return Favorite(
            id=model.id,
            workspace_id=model.workspace_id,
            user_id=model.user_id,
            entity_type=FavoriteEntityType(model.entity_type),
            entity_id=model.entity_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: Favorite) -> FavoriteModel:
        return FavoriteModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            user_id=aggregate.user_id,
            entity_type=aggregate.entity_type.value,
            entity_id=aggregate.entity_id,
            version=aggregate.version,
        )

    def _update_model(self, model: FavoriteModel, aggregate: Favorite) -> None:
        # Favorites are immutable (add/remove only); nothing to update.
        return

    async def find_by_entity(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        entity_type: FavoriteEntityType,
        entity_id: uuid.UUID,
    ) -> Favorite | None:
        stmt = select(FavoriteModel).where(
            FavoriteModel.workspace_id == workspace_id,
            FavoriteModel.user_id == user_id,
            FavoriteModel.entity_type == entity_type.value,
            FavoriteModel.entity_id == entity_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_domain_tracked(model) if model else None

    async def list_for_user(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        entity_type: FavoriteEntityType,
    ) -> list[Favorite]:
        stmt = (
            select(FavoriteModel)
            .where(
                FavoriteModel.workspace_id == workspace_id,
                FavoriteModel.user_id == user_id,
                FavoriteModel.entity_type == entity_type.value,
            )
            .order_by(FavoriteModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars()]

    async def remove(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        entity_type: FavoriteEntityType,
        entity_id: uuid.UUID,
    ) -> None:
        stmt = delete(FavoriteModel).where(
            FavoriteModel.workspace_id == workspace_id,
            FavoriteModel.user_id == user_id,
            FavoriteModel.entity_type == entity_type.value,
            FavoriteModel.entity_id == entity_id,
        )
        await self._session.execute(stmt)
```

- [ ] **Step 5: Create the Alembic migration**

Create `backend/alembic/versions/054_favorites.py`:

```python
"""054 — favorites table.

Per-user, workspace-scoped bookmarks of any entity. Polymorphic by design:
``entity_type`` + ``entity_id`` is a soft reference (no FK) so the
Personalization context stays decoupled from the favorited entity's context.

Revision ID: 054_favorites
Revises: 053_target_link_restrict
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "054_favorites"
down_revision = "053_target_link_restrict"


def upgrade() -> None:
    op.create_table(
        "favorites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_favorites_user_entity",
        "favorites",
        ["user_id", "workspace_id", "entity_type", "entity_id"],
        unique=True,
    )
    op.create_index(
        "ix_favorites_user_type", "favorites", ["user_id", "workspace_id", "entity_type"]
    )
    op.create_index("ix_favorites_workspace_id", "favorites", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_favorites_workspace_id", table_name="favorites")
    op.drop_index("ix_favorites_user_type", table_name="favorites")
    op.drop_index("uq_favorites_user_entity", table_name="favorites")
    op.drop_table("favorites")
```

- [ ] **Step 6: Run the test to verify it passes**

The integration test fixtures run `alembic upgrade head` automatically (session-scoped `_run_migrations`), so the new table is created.

Run: `cd backend && uv run pytest tests/integration/persistence/personalization/test_favorite_repository.py -v`
Expected: PASS (3 passed). Requires Docker (testcontainers).

- [ ] **Step 7: Commit**

```bash
git add backend/src/cellar/infrastructure/persistence/sqlalchemy/personalization \
        backend/alembic/versions/054_favorites.py \
        backend/tests/integration/persistence/personalization
git commit -m "feat(personalization): add favorites table, model, repository (migration 054)"
```

---

## Task 3: Application layer (add / remove / list use cases)

**Files:**
- Create: `backend/src/cellar/application/personalization/__init__.py`
- Create: `backend/src/cellar/application/personalization/add_favorite.py`
- Create: `backend/src/cellar/application/personalization/remove_favorite.py`
- Create: `backend/src/cellar/application/personalization/list_favorites.py`
- Test: `backend/tests/integration/application/personalization/test_favorite_use_cases.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/application/personalization/test_favorite_use_cases.py`:

```python
"""Integration tests for Favorite use cases (Railway Result)."""

from __future__ import annotations

import uuid

import pytest
from returns.result import Success

from cellar.application.personalization.add_favorite import AddFavorite, AddFavoriteCommand
from cellar.application.personalization.list_favorites import ListFavorites, ListFavoritesQuery
from cellar.application.personalization.remove_favorite import (
    RemoveFavorite,
    RemoveFavoriteCommand,
)
from cellar.domain.personalization.enums import FavoriteEntityType
from cellar.infrastructure.persistence.sqlalchemy.personalization.favorite_repository import (
    SQLAlchemyFavoriteRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.fakes.fake_auth import FakeAuth

pytestmark = pytest.mark.integration


def _add(session_factory) -> AddFavorite:
    uow = AsyncUnitOfWork(session_factory)
    return AddFavorite(uow, SQLAlchemyFavoriteRepository(uow), _NoOpDispatcher())


def _remove(session_factory) -> RemoveFavorite:
    uow = AsyncUnitOfWork(session_factory)
    return RemoveFavorite(uow, SQLAlchemyFavoriteRepository(uow), _NoOpDispatcher())


def _list(session_factory) -> ListFavorites:
    uow = AsyncUnitOfWork(session_factory)
    return ListFavorites(uow, SQLAlchemyFavoriteRepository(uow))


class _NoOpDispatcher:
    async def dispatch_all(self, events) -> None:  # noqa: ANN001
        return None


async def test_add_is_idempotent(session_factory, workspace_id, user_id) -> None:
    auth = FakeAuth(role="viewer", workspace_id=workspace_id, user_id=user_id)
    entity = uuid.uuid4()
    cmd = AddFavoriteCommand(
        workspace_id=workspace_id,
        user_id=user_id,
        entity_type=FavoriteEntityType.PROJECT,
        entity_id=entity,
    )
    first = await _add(session_factory)(cmd, auth=auth)
    second = await _add(session_factory)(cmd, auth=auth)
    assert isinstance(first, Success)
    assert isinstance(second, Success)

    listed = await _list(session_factory)(
        ListFavoritesQuery(
            workspace_id=workspace_id, user_id=user_id, entity_type=FavoriteEntityType.PROJECT
        ),
        auth=auth,
    )
    assert isinstance(listed, Success)
    assert len(listed.unwrap()) == 1  # not duplicated


async def test_remove_absent_is_noop(session_factory, workspace_id, user_id) -> None:
    auth = FakeAuth(role="viewer", workspace_id=workspace_id, user_id=user_id)
    cmd = RemoveFavoriteCommand(
        workspace_id=workspace_id,
        user_id=user_id,
        entity_type=FavoriteEntityType.PROJECT,
        entity_id=uuid.uuid4(),
    )
    result = await _remove(session_factory)(cmd, auth=auth)
    assert isinstance(result, Success)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/integration/application/personalization/test_favorite_use_cases.py -v`
Expected: FAIL — `ModuleNotFoundError` for the use-case modules.

- [ ] **Step 3: Create the package + AddFavorite**

Create `backend/src/cellar/application/personalization/__init__.py` (empty file).

Create `backend/src/cellar/application/personalization/add_favorite.py`:

```python
"""AddFavorite — idempotently favorite an entity for the current user."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.personalization.enums import FavoriteEntityType
from cellar.domain.personalization.favorite import Favorite
from cellar.domain.personalization.repository import FavoriteRepository
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class AddFavoriteCommand(Command):
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    entity_type: FavoriteEntityType
    entity_id: uuid.UUID


class AddFavorite:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: FavoriteRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: AddFavoriteCommand, auth: AuthContext | None = None
    ) -> Result[Favorite, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            existing = await self._repo.find_by_entity(
                input.workspace_id, input.user_id, input.entity_type, input.entity_id
            )
            if existing is not None:
                return Success(existing)  # idempotent

            favorite = Favorite.create(
                workspace_id=input.workspace_id,
                user_id=input.user_id,
                entity_type=input.entity_type,
                entity_id=input.entity_id,
            )
            await self._repo.save(favorite)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(favorite)
```

- [ ] **Step 4: Create RemoveFavorite**

Create `backend/src/cellar/application/personalization/remove_favorite.py`:

```python
"""RemoveFavorite — un-favorite an entity for the current user (no-op if absent)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.personalization.enums import FavoriteEntityType
from cellar.domain.personalization.repository import FavoriteRepository
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class RemoveFavoriteCommand(Command):
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    entity_type: FavoriteEntityType
    entity_id: uuid.UUID


class RemoveFavorite:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: FavoriteRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: RemoveFavoriteCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            await self._repo.remove(
                input.workspace_id, input.user_id, input.entity_type, input.entity_id
            )
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)
```

- [ ] **Step 5: Create ListFavorites**

Create `backend/src/cellar/application/personalization/list_favorites.py`:

```python
"""ListFavorites — the current user's favorites of a given entity type."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.personalization.enums import FavoriteEntityType
from cellar.domain.personalization.favorite import Favorite
from cellar.domain.personalization.repository import FavoriteRepository
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListFavoritesQuery(Query):
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    entity_type: FavoriteEntityType


class ListFavorites:
    def __init__(self, uow: UnitOfWork, repo: FavoriteRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListFavoritesQuery, auth: AuthContext | None = None
    ) -> Result[list[Favorite], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            favorites = await self._repo.list_for_user(
                input.workspace_id, input.user_id, input.entity_type
            )
            return Success(favorites)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/integration/application/personalization/test_favorite_use_cases.py -v`
Expected: PASS (2 passed). Requires Docker.

- [ ] **Step 7: Commit**

```bash
git add backend/src/cellar/application/personalization backend/tests/integration/application/personalization
git commit -m "feat(personalization): add/remove/list favorite use cases"
```

---

## Task 4: Interface layer (DI, dependencies, route, app mount)

**Files:**
- Create: `backend/src/cellar/infrastructure/di/_personalization.py`
- Modify: `backend/src/cellar/infrastructure/di/container.py`
- Create: `backend/src/cellar/interface/dependencies/_personalization.py`
- Modify: `backend/src/cellar/interface/dependencies/__init__.py`
- Create: `backend/src/cellar/interface/routes/favorites.py`
- Modify: `backend/src/cellar/interface/app.py`
- Test: `backend/tests/api/test_favorites.py`

- [ ] **Step 1: Write the failing API test**

Create `backend/tests/api/test_favorites.py`:

```python
"""API contract tests for the favorites endpoints."""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration


async def test_add_list_remove_roundtrip(client) -> None:
    entity = str(uuid.uuid4())

    # add
    resp = await client.post(
        "/api/v1/favorites", json={"entity_type": "project", "entity_id": entity}
    )
    assert resp.status_code == 200
    assert resp.json()["entity_id"] == entity

    # list
    resp = await client.get("/api/v1/favorites", params={"entity_type": "project"})
    assert resp.status_code == 200
    assert entity in [f["entity_id"] for f in resp.json()]

    # remove
    resp = await client.delete(f"/api/v1/favorites/project/{entity}")
    assert resp.status_code == 204

    # gone
    resp = await client.get("/api/v1/favorites", params={"entity_type": "project"})
    assert entity not in [f["entity_id"] for f in resp.json()]


async def test_add_is_idempotent(client) -> None:
    entity = str(uuid.uuid4())
    await client.post(
        "/api/v1/favorites", json={"entity_type": "project", "entity_id": entity}
    )
    await client.post(
        "/api/v1/favorites", json={"entity_type": "project", "entity_id": entity}
    )
    resp = await client.get("/api/v1/favorites", params={"entity_type": "project"})
    assert [f["entity_id"] for f in resp.json()].count(entity) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/api/test_favorites.py -v`
Expected: FAIL — 404 (route not mounted yet).

- [ ] **Step 3: Register use cases in the DI container**

Create `backend/src/cellar/infrastructure/di/_personalization.py`:

```python
"""DI registrations for the Personalization context."""

from __future__ import annotations

from lagom import Container
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.application.personalization.add_favorite import AddFavorite
from cellar.application.personalization.list_favorites import ListFavorites
from cellar.application.personalization.remove_favorite import RemoveFavorite
from cellar.infrastructure.messaging.event_dispatcher import EventDispatcher
from cellar.infrastructure.persistence.sqlalchemy.personalization.favorite_repository import (
    SQLAlchemyFavoriteRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


def register_personalization(container: Container) -> None:
    def _cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyFavoriteRepository(uow), c[EventDispatcher])

        return _f

    def _query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyFavoriteRepository(uow))

        return _f

    container.define(AddFavorite, _cmd(AddFavorite))
    container.define(RemoveFavorite, _cmd(RemoveFavorite))
    container.define(ListFavorites, _query(ListFavorites))
```

- [ ] **Step 4: Wire it into the container builder**

Modify `backend/src/cellar/infrastructure/di/container.py`. Add the import alongside the other `register_*` imports (near line 25):

```python
from cellar.infrastructure.di._personalization import register_personalization
```

And add the call in the build function, right after `register_research_organization(container)` (line ~45):

```python
    register_research_organization(container)
    register_personalization(container)
```

- [ ] **Step 5: Create the dependency aliases**

Create `backend/src/cellar/interface/dependencies/_personalization.py`:

```python
"""FastAPI dependency aliases for the Personalization context."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from cellar.application.personalization.add_favorite import AddFavorite
from cellar.application.personalization.list_favorites import ListFavorites
from cellar.application.personalization.remove_favorite import RemoveFavorite
from cellar.interface.dependencies._core import _get_use_case

AddFavoriteDep = Annotated[AddFavorite, Depends(_get_use_case(AddFavorite))]
RemoveFavoriteDep = Annotated[RemoveFavorite, Depends(_get_use_case(RemoveFavorite))]
ListFavoritesDep = Annotated[ListFavorites, Depends(_get_use_case(ListFavorites))]

__all__ = ["AddFavoriteDep", "RemoveFavoriteDep", "ListFavoritesDep"]
```

- [ ] **Step 6: Aggregate the new deps in the dependencies package**

Modify `backend/src/cellar/interface/dependencies/__init__.py`:
1. Add `_personalization` to the `from . import (...)` tuple (alphabetically near `_inventory`).
2. Add `from ._personalization import *  # noqa: F403` alongside the other star-imports.
3. Add `+ _personalization.__all__` to the `__all__` aggregation expression.

- [ ] **Step 7: Create the route module**

Create `backend/src/cellar/interface/routes/favorites.py`:

```python
"""Favorite (pin) endpoints — per-user bookmarks of any entity."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from starlette.responses import Response

from cellar.application.personalization.add_favorite import AddFavoriteCommand
from cellar.application.personalization.list_favorites import ListFavoritesQuery
from cellar.application.personalization.remove_favorite import RemoveFavoriteCommand
from cellar.domain.personalization.enums import FavoriteEntityType
from cellar.domain.personalization.favorite import Favorite
from cellar.interface.dependencies import (
    AddFavoriteDep,
    AuthDep,
    ListFavoritesDep,
    RemoveFavoriteDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/favorites", tags=["favorites"])


class FavoriteResponse(BaseModel):
    entity_type: FavoriteEntityType
    entity_id: uuid.UUID
    created_at: datetime

    @classmethod
    def from_domain(cls, favorite: Favorite) -> "FavoriteResponse":
        return cls(
            entity_type=favorite.entity_type,
            entity_id=favorite.entity_id,
            created_at=favorite.created_at,
        )


class CreateFavoriteBody(BaseModel):
    entity_type: FavoriteEntityType
    entity_id: uuid.UUID


@router.get("", response_model=list[FavoriteResponse])
async def list_favorites(
    auth: AuthDep,
    use_case: ListFavoritesDep,
    entity_type: FavoriteEntityType,
) -> list[FavoriteResponse]:
    query = ListFavoritesQuery(
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
        entity_type=entity_type,
    )
    favorites = result_to_response(await use_case(query, auth=auth))
    return [FavoriteResponse.from_domain(f) for f in favorites]


@router.post("", response_model=FavoriteResponse)
async def add_favorite(
    auth: AuthDep,
    use_case: AddFavoriteDep,
    body: CreateFavoriteBody,
) -> FavoriteResponse:
    command = AddFavoriteCommand(
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
    )
    favorite = result_to_response(await use_case(command, auth=auth))
    return FavoriteResponse.from_domain(favorite)


@router.delete("/{entity_type}/{entity_id}", status_code=204)
async def remove_favorite(
    auth: AuthDep,
    use_case: RemoveFavoriteDep,
    entity_type: FavoriteEntityType,
    entity_id: uuid.UUID,
) -> Response:
    command = RemoveFavoriteCommand(
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    result_to_response(await use_case(command, auth=auth))
    return Response(status_code=204)
```

- [ ] **Step 8: Mount the router**

Modify `backend/src/cellar/interface/app.py`. Add the import alongside the other route imports:

```python
from cellar.interface.routes.favorites import router as favorites_router
```

And mount it alongside the other `app.include_router(...)` calls (near the project router):

```python
app.include_router(favorites_router)
```

- [ ] **Step 9: Run the API test to verify it passes**

Run: `cd backend && uv run pytest tests/api/test_favorites.py -v`
Expected: PASS (2 passed). Requires Docker.

- [ ] **Step 10: Run import-linter and commit**

Run: `cd backend && uv run lint-imports`
Expected: layer contracts pass (personalization domain imports nothing outward).

```bash
git add backend/src/cellar/infrastructure/di/_personalization.py \
        backend/src/cellar/infrastructure/di/container.py \
        backend/src/cellar/interface/dependencies/_personalization.py \
        backend/src/cellar/interface/dependencies/__init__.py \
        backend/src/cellar/interface/routes/favorites.py \
        backend/src/cellar/interface/app.py \
        backend/tests/api/test_favorites.py
git commit -m "feat(personalization): favorites REST endpoints + DI wiring"
```

---

## Task 5: Frontend — regenerate types + generic favorites hook

**Files:**
- Regenerate: `frontend/src/shared/lib/api/model/*` (orval — adds `FavoriteResponse`)
- Create: `frontend/src/shared/hooks/use-favorites.ts`
- Test: `frontend/src/shared/hooks/use-favorites.test.tsx`

- [ ] **Step 1: Regenerate orval types**

With the backend running on `:8000`:

Run: `cd frontend && pnpm generate:api`
Expected: `frontend/src/shared/lib/api/model/favoriteResponse.ts` appears (and is re-exported from `model/index.ts`). Review the diff — it should be additive.

- [ ] **Step 2: Write the failing test**

Create `frontend/src/shared/hooks/use-favorites.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useFavorites } from "./use-favorites";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(async () => [
    { entity_type: "project", entity_id: "p1", created_at: "2026-06-07T00:00:00Z" },
    { entity_type: "project", entity_id: "p2", created_at: "2026-06-07T00:00:00Z" },
  ]),
}));

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useFavorites", () => {
  beforeEach(() => vi.clearAllMocks());

  it("maps the favorites list into a Set of entity ids", async () => {
    const { result } = renderHook(() => useFavorites("project"), { wrapper });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.has("p1")).toBe(true);
    expect(result.current.data?.has("p2")).toBe(true);
    expect(result.current.data?.size).toBe(2);
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && pnpm test -- use-favorites`
Expected: FAIL — cannot find module `./use-favorites`.

- [ ] **Step 4: Create the hook**

Create `frontend/src/shared/hooks/use-favorites.ts`:

```ts
"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { FavoriteResponse } from "@/shared/lib/api/model";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

/** Widen this union as the backend FavoriteEntityType enum grows. */
export type FavoriteEntityType = "project";

export const favoritesKey = (entityType: FavoriteEntityType) => ["favorites", entityType];

/** Set of the current user's favorited entity ids of the given type. */
export function useFavorites(entityType: FavoriteEntityType) {
  return useQuery({
    queryKey: favoritesKey(entityType),
    queryFn: async () => {
      const list = await customInstance<FavoriteResponse[]>({
        url: `${API_V1}/favorites`,
        method: "GET",
        params: { entity_type: entityType },
      });
      return new Set(list.map((f) => f.entity_id));
    },
  });
}

/**
 * Toggle a favorite with an optimistic update.
 *
 * Call `mutate({ entityId, favorited })` where `favorited` is the CURRENT
 * state: `true` → remove (DELETE), `false` → add (POST).
 */
export function useToggleFavorite(entityType: FavoriteEntityType) {
  const qc = useQueryClient();
  const key = favoritesKey(entityType);
  return useMutation({
    mutationFn: ({ entityId, favorited }: { entityId: string; favorited: boolean }) =>
      favorited
        ? customInstance<void>({
            url: `${API_V1}/favorites/${entityType}/${entityId}`,
            method: "DELETE",
          })
        : customInstance<FavoriteResponse>({
            url: `${API_V1}/favorites`,
            method: "POST",
            data: { entity_type: entityType, entity_id: entityId },
          }),
    onMutate: async ({ entityId, favorited }) => {
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<Set<string>>(key);
      const next = new Set(prev ?? []);
      if (favorited) next.delete(entityId);
      else next.add(entityId);
      qc.setQueryData(key, next);
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(key, ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && pnpm test -- use-favorites`
Expected: PASS (1 passed)

- [ ] **Step 6: Lint and commit**

Run: `cd frontend && pnpm lint`
Expected: exit 0 (no errors).

```bash
git add frontend/src/shared/hooks/use-favorites.ts \
        frontend/src/shared/hooks/use-favorites.test.tsx \
        frontend/src/shared/lib/api/model
git commit -m "feat(favorites): generic useFavorites/useToggleFavorite hook + generated type"
```

---

## Phase 1 Done — verification

- [ ] `cd backend && uv run pytest tests/unit/domain/personalization tests/integration/persistence/personalization tests/integration/application/personalization tests/api/test_favorites.py -v` — all green
- [ ] `cd backend && uv run lint-imports` — contracts pass
- [ ] `cd frontend && pnpm test -- use-favorites && pnpm lint` — green
- [ ] Update the GitHub project board (Phase 1 favorites primitive done).
