# Tagging — Phase 4: Admin Operations (rename / merge / delete)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Give workspace admins control over the tag registry: rename a tag, merge one tag into another (re-pointing all its links), and delete a tag. These are the workspace-wide, destructive operations the Phase-2 editor APIs deliberately excluded.

**Architecture:** Three admin-guarded use cases on the existing `Tag` aggregate + a new cross-link-table `repoint` on the link repository (merge moves every link from the source tag to the target across all four taggable types, skipping PK collisions, then deletes the source). All emit the `TagRenamed`/`TagMerged`/`TagDeleted` domain events already declared in Phase 1, so the catch-all `AuditEventHandler` records them. Routes hang off the existing `/api/v1/tags` management router.

**Tech Stack:** Python 3.13, SQLAlchemy 2.0 async, FastAPI, `dry-python/returns`, Lagom, pytest + testcontainers.

**Spec:** `docs/superpowers/specs/2026-06-02-tagging-design.md` §6 (admin auth split), §8 (management routes). Builds on Phases 1–3.

**Branch:** `kvt`.

---

## File Structure

### New — Application (`src/cellar/application/workspace_config/tagging/`)
| Path | Responsibility |
|------|----------------|
| `rename_tag.py` | `RenameTagCommand` + `RenameTag` (admin). |
| `merge_tags.py` | `MergeTagsCommand` + `MergeTags` (admin). |
| `delete_tag.py` | `DeleteTagCommand` + `DeleteTag` (admin). |

### Modified
| Path | Change |
|------|--------|
| `domain/workspace_config/tagging/repository.py` | Add `repoint` to `TagLinkRepository` protocol. |
| `infrastructure/persistence/sqlalchemy/tagging/tag_link_repository.py` | Implement `repoint` on the base. |
| `infrastructure/di/_workspace_config.py` | Register the 3 use cases. |
| `interface/dependencies/_workspace_config.py` | Add `RenameTagDep`/`MergeTagsDep`/`DeleteTagDep`. |
| `interface/routes/tags.py` | Add `PATCH /tags/{id}`, `POST /tags/{id}/merge`, `DELETE /tags/{id}` + request bodies. |

### New — Tests
| Path | Responsibility |
|------|----------------|
| `tests/integration/test_tag_admin.py` | `repoint` + merge/delete cascade integration tests. |
| `tests/unit/application/workspace_config/tagging/test_admin.py` | Unit tests for the 3 use cases. |
| `tests/api/test_tag_admin.py` | API tests (rename/merge/delete + admin-only auth). |

---

## Task P4-1: `repoint` on the link repository

**Files:**
- Modify: `domain/workspace_config/tagging/repository.py`
- Modify: `infrastructure/persistence/sqlalchemy/tagging/tag_link_repository.py`
- Test: `backend/tests/integration/test_tag_admin.py`

- [ ] **Step 1: Add `repoint` to the `TagLinkRepository` protocol**

In `repository.py`, inside `class TagLinkRepository(Protocol)`, add:

```python
    async def repoint(
        self, from_tag_id: uuid.UUID, to_tag_id: uuid.UUID
    ) -> None: ...
```

(No `workspace_id` — both tags are workspace-verified by the caller, and links only exist for in-workspace entities.)

- [ ] **Step 2: Write the failing integration test**

Create `backend/tests/integration/test_tag_admin.py`:

```python
"""Integration tests for tag admin ops (repoint / merge / delete cascade)."""

from __future__ import annotations

import uuid

from sqlalchemy import text

from cellar.domain.workspace_config.tagging.tag import TaggableEntityType, TagName
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_link_repository import (
    get_tag_link_repository,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_repository import (
    SQLAlchemyTagRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


async def _org_and_molecule(uow: AsyncUnitOfWork, ws: uuid.UUID, reg: str) -> uuid.UUID:
    org_id, mol_id = uuid.uuid4(), uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, "
            "version) VALUES (:id, :ws, :n, 'internal', true, 1)"
        ),
        {"id": org_id, "ws": ws, "n": f"org-{reg}"},
    )
    await uow.session.execute(
        text(
            "INSERT INTO molecules (id, workspace_id, registration_number, name, "
            "molecule_type, version, originating_org_id) VALUES "
            "(:id, :ws, :r, :r, 'small_molecule', 1, :org)"
        ),
        {"id": mol_id, "ws": ws, "r": reg, "org": org_id},
    )
    return mol_id


class TestRepoint:
    async def test_repoint_moves_links_and_dedups(self, uow: AsyncUnitOfWork) -> None:
        ws, user = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            a = await tag_repo.get_or_create(ws, TagName(key="a"), user)
            b = await tag_repo.get_or_create(ws, TagName(key="b"), user)
            m1 = await _org_and_molecule(uow, ws, "RP-1")  # has a
            m2 = await _org_and_molecule(uow, ws, "RP-2")  # has a + b
            links = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            await links.add(ws, m1, a.id, user)
            await links.add(ws, m2, a.id, user)
            await links.add(ws, m2, b.id, user)
            await uow.commit()
        async with uow:
            links = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            await links.repoint(a.id, b.id)
            await uow.commit()
        async with uow:
            links = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            m1_tags = {t.key for t in await links.find_tags_for_entity(ws, m1)}
            m2_tags = {t.key for t in await links.find_tags_for_entity(ws, m2)}
            # m1's "a" link moved to "b"; m2 already had "b" so the moved link
            # was dropped on conflict and its "a" link deleted -> both just "b".
            assert m1_tags == {"b"}
            assert m2_tags == {"b"}
            # no "a" links remain anywhere
            res = await uow.session.execute(
                text("SELECT count(*) FROM molecule_tags WHERE tag_id = :id"),
                {"id": a.id},
            )
            assert res.scalar_one() == 0
```

- [ ] **Step 3: Run to verify it fails**

Run (Docker up; up to 600000 ms): `uv run pytest tests/integration/test_tag_admin.py -v`
Expected: FAIL — `AttributeError: … has no attribute 'repoint'`.

- [ ] **Step 4: Implement `repoint`**

In `tag_link_repository.py`, add to the `SQLAlchemyTagLinkRepository` base (and ensure `literal` is imported: `from sqlalchemy import delete, distinct, func, literal, select`):

```python
    async def repoint(
        self, from_tag_id: uuid.UUID, to_tag_id: uuid.UUID
    ) -> None:
        """Move every link from ``from_tag_id`` to ``to_tag_id`` (merge).

        Copies the source links onto the target tag (skipping rows where the
        entity already carries the target — composite-PK conflict), then deletes
        the source links.
        """
        col = self._entity_col
        src = select(
            col,
            literal(to_tag_id),
            self.link_model.assigned_by,
            self.link_model.assigned_at,
        ).where(self.link_model.tag_id == from_tag_id)
        ins = (
            pg_insert(self.link_model)
            .from_select(
                [self.entity_id_attr, "tag_id", "assigned_by", "assigned_at"], src
            )
            .on_conflict_do_nothing()
        )
        await self._session.execute(ins)
        await self._session.execute(
            delete(self.link_model).where(self.link_model.tag_id == from_tag_id)
        )
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/integration/test_tag_admin.py -v` → PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/domain/workspace_config/tagging/repository.py \
        backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/tag_link_repository.py \
        backend/tests/integration/test_tag_admin.py
git commit -m "feat(tagging): repoint links for tag merge"
```

---

## Task P4-2: `RenameTag` + `DeleteTag` use cases

**Files:**
- Create: `src/cellar/application/workspace_config/tagging/rename_tag.py`
- Create: `src/cellar/application/workspace_config/tagging/delete_tag.py`
- Test: `backend/tests/unit/application/workspace_config/tagging/test_admin.py`

- [ ] **Step 1: Write the failing unit tests**

Create `backend/tests/unit/application/workspace_config/tagging/test_admin.py`:

```python
"""Unit tests for admin tag use cases (rename / delete; merge in test_admin too)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.workspace_config.tagging.delete_tag import (
    DeleteTag,
    DeleteTagCommand,
)
from cellar.application.workspace_config.tagging.rename_tag import (
    RenameTag,
    RenameTagCommand,
)
from cellar.domain.shared.errors import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
)
from cellar.domain.workspace_config.tagging.events import TagDeleted, TagRenamed
from tests.unit.application.workspace_config.tagging._helpers import (
    FakeUnitOfWork,
    fake_auth,
    make_tag,
)


def _tag_repo(*, find_by_id, find_by_normalized=None) -> AsyncMock:
    repo = AsyncMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=find_by_id)
    repo.find_by_normalized = AsyncMock(return_value=find_by_normalized)
    repo.save = AsyncMock()
    repo.delete = AsyncMock()
    return repo


class TestRenameTag:
    @pytest.mark.asyncio
    async def test_renames_and_emits(self) -> None:
        auth = fake_auth(role="admin")
        tag = make_tag(auth.workspace_id, "old", None, auth.user_id)
        tag.clear_events()
        repo = _tag_repo(find_by_id=tag, find_by_normalized=None)
        dispatcher = AsyncMock()
        uc = RenameTag(FakeUnitOfWork(), repo, dispatcher)
        cmd = RenameTagCommand(
            workspace_id=auth.workspace_id, tag_id=tag.id, key="New", value="V"
        )
        result = await uc(cmd, auth=auth)
        assert isinstance(result, Success)
        assert result.unwrap().key == "New"
        repo.save.assert_awaited_once()
        events = dispatcher.dispatch_all.call_args.args[0]
        assert any(isinstance(e, TagRenamed) for e in events)

    @pytest.mark.asyncio
    async def test_collision_returns_conflict(self) -> None:
        auth = fake_auth(role="admin")
        tag = make_tag(auth.workspace_id, "old", None, auth.user_id)
        other = make_tag(auth.workspace_id, "taken", None, auth.user_id)
        repo = _tag_repo(find_by_id=tag, find_by_normalized=other)  # name already used
        uc = RenameTag(FakeUnitOfWork(), repo, AsyncMock())
        cmd = RenameTagCommand(
            workspace_id=auth.workspace_id, tag_id=tag.id, key="taken", value=None
        )
        result = await uc(cmd, auth=auth)
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ConflictError)
        repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        auth = fake_auth(role="admin")
        repo = _tag_repo(find_by_id=None)
        uc = RenameTag(FakeUnitOfWork(), repo, AsyncMock())
        cmd = RenameTagCommand(
            workspace_id=auth.workspace_id, tag_id=uuid.uuid4(), key="x", value=None
        )
        result = await uc(cmd, auth=auth)
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_editor_denied(self) -> None:
        auth = fake_auth(role="editor")  # editor is NOT admin
        tag = make_tag(auth.workspace_id, "old", None, auth.user_id)
        uc = RenameTag(FakeUnitOfWork(), _tag_repo(find_by_id=tag), AsyncMock())
        cmd = RenameTagCommand(
            workspace_id=auth.workspace_id, tag_id=tag.id, key="new", value=None
        )
        with pytest.raises(AuthorizationError):
            await uc(cmd, auth=auth)


class TestDeleteTag:
    @pytest.mark.asyncio
    async def test_deletes_and_emits(self) -> None:
        auth = fake_auth(role="admin")
        tag = make_tag(auth.workspace_id, "junk", None, auth.user_id)
        tag.clear_events()
        repo = _tag_repo(find_by_id=tag)
        dispatcher = AsyncMock()
        uc = DeleteTag(FakeUnitOfWork(), repo, dispatcher)
        cmd = DeleteTagCommand(workspace_id=auth.workspace_id, tag_id=tag.id)
        result = await uc(cmd, auth=auth)
        assert isinstance(result, Success)
        repo.delete.assert_awaited_once()
        events = dispatcher.dispatch_all.call_args.args[0]
        assert any(isinstance(e, TagDeleted) for e in events)

    @pytest.mark.asyncio
    async def test_editor_denied(self) -> None:
        auth = fake_auth(role="editor")
        tag = make_tag(auth.workspace_id, "junk", None, auth.user_id)
        uc = DeleteTag(FakeUnitOfWork(), _tag_repo(find_by_id=tag), AsyncMock())
        cmd = DeleteTagCommand(workspace_id=auth.workspace_id, tag_id=tag.id)
        with pytest.raises(AuthorizationError):
            await uc(cmd, auth=auth)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/application/workspace_config/tagging/test_admin.py -v`
Expected: FAIL — `ModuleNotFoundError: …rename_tag`.

- [ ] **Step 3: Write `RenameTag`**

Create `src/cellar/application/workspace_config/tagging/rename_tag.py`:

```python
"""RenameTag — change a tag's key/value (admin)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_admin
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)
from cellar.domain.workspace_config.tagging.repository import TagRepository
from cellar.domain.workspace_config.tagging.tag import Tag, TagName


@dataclass(frozen=True, kw_only=True)
class RenameTagCommand(Command):
    workspace_id: uuid.UUID
    tag_id: uuid.UUID
    key: str
    value: str | None


class RenameTag:
    def __init__(
        self,
        uow: UnitOfWork,
        tag_repo: TagRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._tag_repo = tag_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: RenameTagCommand, auth: AuthContext | None = None
    ) -> Result[Tag, DomainError]:
        require_admin(auth)
        try:
            new_name = TagName(key=input.key, value=input.value)
        except ValueError as exc:
            return Failure(ValidationError(str(exc)))

        async with self._uow:
            tag = await self._tag_repo.find_by_id_in_workspace(
                input.workspace_id, input.tag_id
            )
            if tag is None:
                return Failure(NotFoundError("Tag", str(input.tag_id)))

            existing = await self._tag_repo.find_by_normalized(
                input.workspace_id, new_name
            )
            if existing is not None and existing.id != tag.id:
                return Failure(
                    ConflictError(
                        f"A tag '{new_name.key}' already exists — merge instead of rename"
                    )
                )

            tag.rename(new_name)
            await self._tag_repo.save(tag)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(tag)
```

- [ ] **Step 4: Write `DeleteTag`**

Create `src/cellar/application/workspace_config/tagging/delete_tag.py`:

```python
"""DeleteTag — remove a tag and (via DB CASCADE) all its links (admin)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_admin
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError
from cellar.domain.workspace_config.tagging.events import TagDeleted
from cellar.domain.workspace_config.tagging.repository import TagRepository


@dataclass(frozen=True, kw_only=True)
class DeleteTagCommand(Command):
    workspace_id: uuid.UUID
    tag_id: uuid.UUID


class DeleteTag:
    def __init__(
        self,
        uow: UnitOfWork,
        tag_repo: TagRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._tag_repo = tag_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: DeleteTagCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_admin(auth)

        async with self._uow:
            tag = await self._tag_repo.find_by_id_in_workspace(
                input.workspace_id, input.tag_id
            )
            if tag is None:
                return Failure(NotFoundError("Tag", str(input.tag_id)))

            tag.register_event(
                TagDeleted(
                    aggregate_id=tag.id,
                    aggregate_type="Tag",
                    workspace_id=input.workspace_id,
                    key=tag.key,
                    value=tag.value,
                )
            )
            self._uow.track(tag)
            await self._tag_repo.delete(input.workspace_id, tag.id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/unit/application/workspace_config/tagging/test_admin.py -v`
Expected: PASS — `TestRenameTag` + `TestDeleteTag` (the Merge tests are appended in Task P4-3, so they aren't in this file yet).

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/application/workspace_config/tagging/rename_tag.py \
        backend/src/cellar/application/workspace_config/tagging/delete_tag.py \
        backend/tests/unit/application/workspace_config/tagging/test_admin.py
git commit -m "feat(tagging): RenameTag + DeleteTag admin use cases"
```

---

## Task P4-3: `MergeTags` use case

**Files:**
- Create: `src/cellar/application/workspace_config/tagging/merge_tags.py`
- Test: append to `tests/unit/application/workspace_config/tagging/test_admin.py` + `tests/integration/test_tag_admin.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/application/workspace_config/tagging/test_admin.py`:

```python
from cellar.application.workspace_config.tagging.merge_tags import (
    MergeTags,
    MergeTagsCommand,
)
from cellar.domain.workspace_config.tagging.events import TagMerged
from cellar.domain.workspace_config.tagging.tag import TaggableEntityType


def _merge_link_provider() -> AsyncMock:
    link_repo = AsyncMock()
    link_repo.repoint = AsyncMock()
    provider = AsyncMock()
    provider.for_type = lambda _et: link_repo
    provider.link_repo = link_repo
    return provider


class TestMergeTags:
    @pytest.mark.asyncio
    async def test_merges_repoints_all_types_and_deletes_source(self) -> None:
        auth = fake_auth(role="admin")
        src = make_tag(auth.workspace_id, "src", None, auth.user_id); src.clear_events()
        tgt = make_tag(auth.workspace_id, "tgt", None, auth.user_id); tgt.clear_events()
        repo = AsyncMock()
        repo.find_by_id_in_workspace = AsyncMock(side_effect=[src, tgt])
        repo.delete = AsyncMock()
        provider = _merge_link_provider()
        dispatcher = AsyncMock()
        uc = MergeTags(FakeUnitOfWork(), repo, provider, dispatcher)
        cmd = MergeTagsCommand(
            workspace_id=auth.workspace_id, source_tag_id=src.id, target_tag_id=tgt.id
        )
        result = await uc(cmd, auth=auth)
        assert isinstance(result, Success)
        assert result.unwrap().id == tgt.id
        # repoint called once per taggable entity type
        assert provider.link_repo.repoint.await_count == len(TaggableEntityType)
        repo.delete.assert_awaited_once()
        events = dispatcher.dispatch_all.call_args.args[0]
        assert any(isinstance(e, TagMerged) for e in events)

    @pytest.mark.asyncio
    async def test_merge_into_self_is_validation_error(self) -> None:
        auth = fake_auth(role="admin")
        tid = uuid.uuid4()
        uc = MergeTags(FakeUnitOfWork(), AsyncMock(), _merge_link_provider(), AsyncMock())
        cmd = MergeTagsCommand(
            workspace_id=auth.workspace_id, source_tag_id=tid, target_tag_id=tid
        )
        result = await uc(cmd, auth=auth)
        assert isinstance(result, Failure)

    @pytest.mark.asyncio
    async def test_missing_source_not_found(self) -> None:
        auth = fake_auth(role="admin")
        repo = AsyncMock()
        repo.find_by_id_in_workspace = AsyncMock(return_value=None)
        uc = MergeTags(FakeUnitOfWork(), repo, _merge_link_provider(), AsyncMock())
        cmd = MergeTagsCommand(
            workspace_id=auth.workspace_id,
            source_tag_id=uuid.uuid4(),
            target_tag_id=uuid.uuid4(),
        )
        result = await uc(cmd, auth=auth)
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
```

And append an integration test to `tests/integration/test_tag_admin.py`:

```python
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_link_repository import (
    SQLAlchemyTagLinkRepositoryProvider,
)


class TestMergeIntegration:
    async def test_merge_moves_links_and_drops_source_tag(
        self, uow: AsyncUnitOfWork
    ) -> None:
        from cellar.application.workspace_config.tagging.merge_tags import (
            MergeTags,
            MergeTagsCommand,
        )
        from unittest.mock import AsyncMock

        ws, user = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            src = await tag_repo.get_or_create(ws, TagName(key="src"), user)
            tgt = await tag_repo.get_or_create(ws, TagName(key="tgt"), user)
            m1 = await _org_and_molecule(uow, ws, "MG-1")
            links = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            await links.add(ws, m1, src.id, user)
            await uow.commit()

        class _Auth:
            user_id = user
            workspace_id = ws
            workspace_role = "admin"
            is_admin = True
            def has_role(self, m: str) -> bool:
                return True

        uc = MergeTags(
            uow,
            SQLAlchemyTagRepository(uow),
            SQLAlchemyTagLinkRepositoryProvider(uow),
            AsyncMock(),
        )
        result = await uc(
            MergeTagsCommand(workspace_id=ws, source_tag_id=src.id, target_tag_id=tgt.id),
            auth=_Auth(),
        )
        assert result.unwrap().id == tgt.id

        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            assert await tag_repo.find_by_id_in_workspace(ws, src.id) is None  # source gone
            links = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            assert {t.key for t in await links.find_tags_for_entity(ws, m1)} == {"tgt"}
```

> Note: the integration test instantiates `MergeTags` with the *real* `uow` directly (the use case opens its own `async with self._uow:`), so do NOT wrap the `uc(...)` call in `async with uow`.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/application/workspace_config/tagging/test_admin.py -v` → Merge tests FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write `MergeTags`**

Create `src/cellar/application/workspace_config/tagging/merge_tags.py`:

```python
"""MergeTags — fold a source tag into a target, repointing all links (admin)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_admin
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError
from cellar.domain.workspace_config.tagging.events import TagMerged
from cellar.domain.workspace_config.tagging.repository import (
    TagLinkRepositoryProvider,
    TagRepository,
)
from cellar.domain.workspace_config.tagging.tag import Tag, TaggableEntityType


@dataclass(frozen=True, kw_only=True)
class MergeTagsCommand(Command):
    workspace_id: uuid.UUID
    source_tag_id: uuid.UUID
    target_tag_id: uuid.UUID


class MergeTags:
    def __init__(
        self,
        uow: UnitOfWork,
        tag_repo: TagRepository,
        link_provider: TagLinkRepositoryProvider,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._tag_repo = tag_repo
        self._link_provider = link_provider
        self._dispatcher = dispatcher

    async def __call__(
        self, input: MergeTagsCommand, auth: AuthContext | None = None
    ) -> Result[Tag, DomainError]:
        require_admin(auth)
        if input.source_tag_id == input.target_tag_id:
            return Failure(ValidationError("Cannot merge a tag into itself"))

        async with self._uow:
            source = await self._tag_repo.find_by_id_in_workspace(
                input.workspace_id, input.source_tag_id
            )
            if source is None:
                return Failure(NotFoundError("Tag", str(input.source_tag_id)))
            target = await self._tag_repo.find_by_id_in_workspace(
                input.workspace_id, input.target_tag_id
            )
            if target is None:
                return Failure(NotFoundError("Tag", str(input.target_tag_id)))

            for entity_type in TaggableEntityType:
                link_repo = self._link_provider.for_type(entity_type)
                await link_repo.repoint(source.id, target.id)

            source.register_event(
                TagMerged(
                    aggregate_id=source.id,
                    aggregate_type="Tag",
                    workspace_id=input.workspace_id,
                    target_tag_id=target.id,
                )
            )
            self._uow.track(source)
            await self._tag_repo.delete(input.workspace_id, source.id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(target)
```

- [ ] **Step 4: Run to verify it passes**

Run:
- `uv run pytest tests/unit/application/workspace_config/tagging/test_admin.py -v` (all admin unit tests pass).
- `uv run pytest tests/integration/test_tag_admin.py -v` (repoint + merge integration pass).

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/application/workspace_config/tagging/merge_tags.py \
        backend/tests/unit/application/workspace_config/tagging/test_admin.py \
        backend/tests/integration/test_tag_admin.py
git commit -m "feat(tagging): MergeTags admin use case"
```

---

## Task P4-4: DI wiring + dependency aliases + routes

**Files:**
- Modify: `infrastructure/di/_workspace_config.py`
- Modify: `interface/dependencies/_workspace_config.py`
- Modify: `interface/routes/tags.py`

- [ ] **Step 1: Register the use cases in DI**

In `infrastructure/di/_workspace_config.py`, add imports for `RenameTag`, `DeleteTag`, `MergeTags`, then in `register_workspace_config` (after the Phase-2 tag registrations) add:

```python
    def _rename_or_delete(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyTagRepository(uow), c[EventDispatcher])

        return _f

    container.define(RenameTag, _rename_or_delete(RenameTag))
    container.define(DeleteTag, _rename_or_delete(DeleteTag))

    def _merge_tags(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return MergeTags(
            uow,
            SQLAlchemyTagRepository(uow),
            SQLAlchemyTagLinkRepositoryProvider(uow),
            c[EventDispatcher],
        )

    container.define(MergeTags, _merge_tags)
```

(`SQLAlchemyTagRepository`, `SQLAlchemyTagLinkRepositoryProvider`, `AsyncUnitOfWork`, `async_sessionmaker`, `EventDispatcher`, `Container` are already imported from Phase 2.)

- [ ] **Step 2: Add dependency aliases**

In `interface/dependencies/_workspace_config.py`, import the 3 use cases and add (with the other tag `*Dep` aliases + to `__all__` if present):

```python
RenameTagDep = Annotated[RenameTag, Depends(_get_use_case(RenameTag))]
MergeTagsDep = Annotated[MergeTags, Depends(_get_use_case(MergeTags))]
DeleteTagDep = Annotated[DeleteTag, Depends(_get_use_case(DeleteTag))]
```

- [ ] **Step 3: Add the management routes**

In `interface/routes/tags.py`, add request bodies near the existing ones:

```python
class RenameTagBody(BaseModel):
    key: str
    value: str | None = None


class MergeTagBody(BaseModel):
    target_tag_id: uuid.UUID
```

import the new commands + deps (alongside the existing tag imports):

```python
from cellar.application.workspace_config.tagging.delete_tag import DeleteTagCommand
from cellar.application.workspace_config.tagging.merge_tags import MergeTagsCommand
from cellar.application.workspace_config.tagging.rename_tag import RenameTagCommand
from cellar.interface.dependencies._workspace_config import (
    DeleteTagDep,
    MergeTagsDep,
    RenameTagDep,
)
```

and add these handlers to the management `router` (the one with `prefix="/api/v1/tags"`):

```python
@router.patch("/{tag_id}", response_model=TagResponse)
async def rename_tag(
    tag_id: uuid.UUID,
    body: RenameTagBody,
    auth: AuthDep,
    use_case: RenameTagDep,
) -> TagResponse:
    command = RenameTagCommand(
        workspace_id=auth.workspace_id, tag_id=tag_id, key=body.key, value=body.value
    )
    tag = result_to_response(await use_case(command, auth=auth))
    return TagResponse.from_domain(tag)


@router.post("/{tag_id}/merge", response_model=TagResponse)
async def merge_tag(
    tag_id: uuid.UUID,
    body: MergeTagBody,
    auth: AuthDep,
    use_case: MergeTagsDep,
) -> TagResponse:
    command = MergeTagsCommand(
        workspace_id=auth.workspace_id,
        source_tag_id=tag_id,
        target_tag_id=body.target_tag_id,
    )
    tag = result_to_response(await use_case(command, auth=auth))
    return TagResponse.from_domain(tag)


@router.delete("/{tag_id}", status_code=204)
async def delete_tag(
    tag_id: uuid.UUID,
    auth: AuthDep,
    use_case: DeleteTagDep,
) -> Response:
    command = DeleteTagCommand(workspace_id=auth.workspace_id, tag_id=tag_id)
    result_to_response(await use_case(command, auth=auth))
    return Response(status_code=204)
```

> Route-ordering check: the management router already has `GET ""` (list). The new `PATCH/DELETE /{tag_id}` and `POST /{tag_id}/merge` are distinct paths — no collision with the generic `assignment_router` (which only matches `/{entity_collection}/{entity_id}/tags…`, a different shape).

- [ ] **Step 4: Verify the wiring**

Run: `uv run python -c "import cellar.infrastructure.di._workspace_config"` → exit 0.
Run: `env DUAR_SERVICE_KEY=test DUAR_URL=https://duar.example.com DUAR_SERVICE_NAME=cellar TEMPORAL_DISABLED=1 uv run python -c "import cellar.interface.routes.tags as t; print(len(t.router.routes))"` → `4` (GET + PATCH + POST-merge + DELETE).

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/di/_workspace_config.py \
        backend/src/cellar/interface/dependencies/_workspace_config.py \
        backend/src/cellar/interface/routes/tags.py
git commit -m "feat(tagging): admin tag routes (rename/merge/delete) + DI"
```

---

## Task P4-5: API tests

**Files:**
- Test: `backend/tests/api/test_tag_admin.py`

The `client` fixture is admin; `editor_client` is editor. Tags/collections are created via the existing APIs. Assignment uses collections (creatable with just a name, per Phase 2).

- [ ] **Step 1: Write the API tests**

Create `backend/tests/api/test_tag_admin.py`:

```python
"""API tests for admin tag operations (rename/merge/delete + auth)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def _collection(client: AsyncClient, name: str) -> str:
    resp = await client.post("/api/v1/collections", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _tag_collection(client: AsyncClient, cid: str, key: str, value=None) -> str:
    resp = await client.post(
        f"/api/v1/collections/{cid}/tags", json={"key": key, "value": value}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class TestRename:
    async def test_rename(self, client: AsyncClient) -> None:
        cid = await _collection(client, "AdminCol-1")
        tid = await _tag_collection(client, cid, "oldname")
        resp = await client.patch(f"/api/v1/tags/{tid}", json={"key": "newname"})
        assert resp.status_code == 200
        assert resp.json()["key"] == "newname"

    async def test_rename_collision_409(self, client: AsyncClient) -> None:
        cid = await _collection(client, "AdminCol-2")
        await _tag_collection(client, cid, "taken")
        tid = await _tag_collection(client, cid, "other")
        resp = await client.patch(f"/api/v1/tags/{tid}", json={"key": "taken"})
        assert resp.status_code == 409


class TestMerge:
    async def test_merge(self, client: AsyncClient) -> None:
        cid = await _collection(client, "AdminCol-3")
        src = await _tag_collection(client, cid, "source")
        tgt = await _tag_collection(client, cid, "target")
        resp = await client.post(f"/api/v1/tags/{src}/merge", json={"target_tag_id": tgt})
        assert resp.status_code == 200
        assert resp.json()["id"] == tgt
        # the collection now carries only the target tag
        got = await client.get(f"/api/v1/collections/{cid}/tags")
        keys = {t["key"] for t in got.json()}
        assert keys == {"target"}


class TestDelete:
    async def test_delete(self, client: AsyncClient) -> None:
        cid = await _collection(client, "AdminCol-4")
        tid = await _tag_collection(client, cid, "doomed")
        resp = await client.delete(f"/api/v1/tags/{tid}")
        assert resp.status_code == 204
        # link cascade-cleared
        got = await client.get(f"/api/v1/collections/{cid}/tags")
        assert got.json() == []

    async def test_delete_not_found_404(self, client: AsyncClient) -> None:
        resp = await client.delete(f"/api/v1/tags/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestAuth:
    async def test_editor_cannot_rename_403(
        self, client: AsyncClient, editor_client: AsyncClient
    ) -> None:
        cid = await _collection(client, "AdminCol-5")
        tid = await _tag_collection(client, cid, "x")
        resp = await editor_client.patch(f"/api/v1/tags/{tid}", json={"key": "y"})
        assert resp.status_code == 403

    async def test_editor_cannot_delete_403(
        self, client: AsyncClient, editor_client: AsyncClient
    ) -> None:
        cid = await _collection(client, "AdminCol-6")
        tid = await _tag_collection(client, cid, "x")
        resp = await editor_client.delete(f"/api/v1/tags/{tid}")
        assert resp.status_code == 403
```

- [ ] **Step 2: Run the API tests**

Run (Docker up; up to 600000 ms): `uv run pytest tests/api/test_tag_admin.py -v` → PASS.

- [ ] **Step 3: Run the whole tagging surface (regression)**

Run: `uv run pytest tests/unit/application/workspace_config/tagging tests/integration/test_tag_admin.py tests/api/test_tags.py tests/api/test_tag_admin.py -q` → PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/api/test_tag_admin.py
git commit -m "test(tagging): API tests for admin tag operations"
```

---

## Phase 4 Done — Definition of Done

- [ ] `uv run pytest tests/unit/application/workspace_config/tagging -v` → pass (incl. admin).
- [ ] `uv run pytest tests/integration/test_tag_admin.py -v` → pass (repoint + merge).
- [ ] `uv run pytest tests/api/test_tag_admin.py -v` → pass (rename/merge/delete + editor-403).
- [ ] No regression in `tests/unit -q` (the 3 pre-existing `test_molecules.py` API failures + 2 bemis integration failures remain known/unrelated).

**Delivered:** admins can rename, merge, and delete tags through `/api/v1/tags/{id}` (PATCH / POST `/merge` / DELETE), all audited via `TagRenamed`/`TagMerged`/`TagDeleted`; merge re-points every link across all four taggable types and removes the source tag.

**Next:** Phase 5 (frontend: chips, autocomplete editor, filter control, management page wiring rename/merge/delete + orval regen).

---

## Implementation Notes — execution findings (2026-06-02)

- **`RenameTag` needed `self._uow.track(tag)`** (the plan's draft omitted it). It's required so the `TagRenamed` event is collected on commit (matches the established Phase-2 pattern; idempotent in production where `find_by_id_in_workspace` already tracks). Added during P4-2.
- **Audit mapping (confirmed):** the catch-all `AuditEventHandler` records `TagMerged`→`OperationType.MERGE` and `TagRenamed`/`TagDeleted`→`DATA_ENTRY` with no per-event registration.
- A no-op rename (new name == current) emits no event (the aggregate's `rename` guard) → no audit row; intentional.

**Final state:** 5 implementation commits (`041e6929`…`7ee6952e`). Tagging admin suite: 9 unit + 2 integration + 7 API = green; full backend unit suite **2603 passed, 0 failed**. The 5 pre-existing non-tagging failures (backlog) are unchanged. Final review: READY TO MERGE.
