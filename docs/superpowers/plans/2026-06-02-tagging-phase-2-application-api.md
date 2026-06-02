# Tagging — Phase 2: Application Use Cases + API

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Expose tagging through the application + interface layers: use cases to assign/unassign/set/list tags and read an entity's tags, wired into DI, behind nested REST routes — so the frontend (Phase 5) and filtering (Phase 3) have a working API.

**Architecture:** Thin FastAPI routes → frozen Command/Query → use case (railway `Result`, auth guard, UoW, event dispatch) → Phase 1 repositories. Assignment is generic over the four taggable entity types via a `TagLinkRepositoryProvider`. Tag-assignment events (`TagAssigned`/`TagUnassigned`) ride on the `Tag` aggregate so the existing UoW collection + catch-all `AuditEventHandler` audit them automatically. Mutations require `editor`; reads are workspace-scoped with no role gate. Admin ops (rename/merge/delete) are **Phase 4**, not here.

**Tech Stack:** Python 3.13, FastAPI, `dry-python/returns`, Lagom DI, Pydantic v2, pytest + httpx `AsyncClient` (+ testcontainers DB).

**Spec:** `docs/superpowers/specs/2026-06-02-tagging-design.md` §6 (Application), §8 (API). Builds on Phase 1 (`docs/superpowers/plans/2026-06-02-tagging-phase-1-backend-foundation.md`).

**Branch:** `kvt` (continues directly on the Phase 1 commits).

---

## File Structure

### New — Application (`src/cellar/application/workspace_config/tagging/`)
| Path | Responsibility |
|------|----------------|
| `__init__.py` | Package marker. |
| `assign_tag.py` | `AssignTagCommand` + `AssignTag`. |
| `unassign_tag.py` | `UnassignTagCommand` + `UnassignTag`. |
| `set_entity_tags.py` | `TagInput`, `SetEntityTagsCommand` + `SetEntityTags`. |
| `list_tags.py` | `ListTagsQuery` + `ListTags`. |
| `get_tags_for_entity.py` | `GetTagsForEntityQuery` + `GetTagsForEntity`. |

### New — Interface
| Path | Responsibility |
|------|----------------|
| `src/cellar/interface/routes/tags.py` | `TagResponse`, request bodies, management `router` (list) + generic `assignment_router`. |

### Modified
| Path | Change |
|------|--------|
| `src/cellar/domain/workspace_config/tagging/repository.py` | Add `entity_exists_in_workspace` to `TagLinkRepository` protocol. |
| `src/cellar/infrastructure/persistence/sqlalchemy/tagging/tag_link_repository.py` | Rename `_entity_in_workspace` → public `entity_exists_in_workspace`; add `SQLAlchemyTagLinkRepositoryProvider`. |
| `src/cellar/infrastructure/di/_workspace_config.py` | Register the 5 tag use cases. |
| `src/cellar/interface/dependencies/_workspace_config.py` | Add `*Dep` aliases for the 5 use cases. |
| `src/cellar/interface/app.py` | Include the two tag routers. |
| `backend/tests/api/conftest.py` | Include the two tag routers in the test app; add a `viewer_client` fixture. |

### New — Tests
| Path | Responsibility |
|------|----------------|
| `backend/tests/unit/application/workspace_config/tagging/__init__.py` | Package marker. |
| `backend/tests/unit/application/workspace_config/tagging/_helpers.py` | `FakeUnitOfWork`, fakes for tag repo + link provider. |
| `backend/tests/unit/application/workspace_config/tagging/test_assign_unassign.py` | Unit tests for `AssignTag`/`UnassignTag`. |
| `backend/tests/unit/application/workspace_config/tagging/test_set_entity_tags.py` | Unit tests for `SetEntityTags`. |
| `backend/tests/unit/application/workspace_config/tagging/test_list_and_get.py` | Unit tests for `ListTags`/`GetTagsForEntity`. |
| `backend/tests/integration/test_tagging_provider.py` | Integration test for `entity_exists_in_workspace` + provider. |
| `backend/tests/api/test_tags.py` | API tests (assign/get/set/unassign/list + auth + 404s). |

---

## Task 1: Link-repo `entity_exists_in_workspace` + provider

**Files:**
- Modify: `src/cellar/domain/workspace_config/tagging/repository.py`
- Modify: `src/cellar/infrastructure/persistence/sqlalchemy/tagging/tag_link_repository.py`
- Test: `backend/tests/integration/test_tagging_provider.py`

- [ ] **Step 1: Add `entity_exists_in_workspace` to the `TagLinkRepository` protocol**

In `repository.py`, inside `class TagLinkRepository(Protocol)`, add this method (e.g. right after `add`):

```python
    async def entity_exists_in_workspace(
        self, workspace_id: uuid.UUID, entity_id: uuid.UUID
    ) -> bool: ...
```

- [ ] **Step 2: Write the failing integration test**

Create `backend/tests/integration/test_tagging_provider.py`:

```python
"""Integration tests for entity_exists_in_workspace + the link-repo provider."""

from __future__ import annotations

import uuid

from sqlalchemy import text

from cellar.domain.workspace_config.tagging.tag import TaggableEntityType
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_link_repository import (
    MoleculeTagLinkRepository,
    SQLAlchemyTagLinkRepositoryProvider,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


async def _insert_org_and_molecule(
    uow: AsyncUnitOfWork, workspace_id: uuid.UUID, reg: str
) -> uuid.UUID:
    org_id = uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO organizations (id, workspace_id, name, org_type, "
            "is_active, version) VALUES (:id, :ws, :name, 'internal', true, 1)"
        ),
        {"id": org_id, "ws": workspace_id, "name": f"org-{reg}"},
    )
    mol_id = uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO molecules (id, workspace_id, registration_number, name, "
            "molecule_type, version, originating_org_id) VALUES "
            "(:id, :ws, :reg, :name, 'small_molecule', 1, :org)"
        ),
        {"id": mol_id, "ws": workspace_id, "reg": reg, "name": reg, "org": org_id},
    )
    return mol_id


class TestEntityExistsAndProvider:
    async def test_entity_exists_in_workspace(self, uow: AsyncUnitOfWork) -> None:
        ws_id, other_ws = uuid.uuid4(), uuid.uuid4()
        async with uow:
            mol_id = await _insert_org_and_molecule(uow, ws_id, "EX-1")
            await uow.commit()
        async with uow:
            repo = MoleculeTagLinkRepository(uow)
            assert await repo.entity_exists_in_workspace(ws_id, mol_id) is True
            assert await repo.entity_exists_in_workspace(other_ws, mol_id) is False
            assert await repo.entity_exists_in_workspace(ws_id, uuid.uuid4()) is False

    async def test_provider_returns_bound_repo(self, uow: AsyncUnitOfWork) -> None:
        provider = SQLAlchemyTagLinkRepositoryProvider(uow)
        repo = provider.for_type(TaggableEntityType.MOLECULE)
        assert isinstance(repo, MoleculeTagLinkRepository)
        assert repo._uow is uow
```

- [ ] **Step 3: Run to verify it fails**

Run (Docker up; up to 600000 ms): `uv run pytest tests/integration/test_tagging_provider.py -v`
Expected: FAIL — `ImportError: cannot import name 'SQLAlchemyTagLinkRepositoryProvider'` (and `entity_exists_in_workspace` not yet public).

- [ ] **Step 4: Make `entity_exists_in_workspace` public + add the provider**

In `tag_link_repository.py`:

(a) Rename the private method to public and update its three internal callers (`add`, `remove`, `set_for_entity`). Change the method definition:

```python
    async def entity_exists_in_workspace(
        self, workspace_id: uuid.UUID, entity_id: uuid.UUID
    ) -> bool:
        stmt = select(self.entity_model.id).where(
            self.entity_model.id == entity_id,
            self.entity_model.workspace_id == workspace_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None
```

Then in `add`, `remove`, and `set_for_entity`, replace every `await self._entity_in_workspace(workspace_id, entity_id)` with `await self.entity_exists_in_workspace(workspace_id, entity_id)`. (There are exactly three call sites.)

(b) Append the provider class at the END of the file (it implements the domain `TagLinkRepositoryProvider` protocol structurally):

```python
class SQLAlchemyTagLinkRepositoryProvider:
    """Resolves the right link repository for an entity type, bound to a uow."""

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    def for_type(self, entity_type: TaggableEntityType) -> SQLAlchemyTagLinkRepository:
        return get_tag_link_repository(entity_type, self._uow)
```

- [ ] **Step 5: Run to verify it passes (and no Phase 1 regressions)**

Run: `uv run pytest tests/integration/test_tagging_provider.py tests/integration/test_tagging.py -v`
Expected: PASS (2 new + 15 Phase 1 = 17). The Phase 1 link tests still pass because the renamed guard is called internally.

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/domain/workspace_config/tagging/repository.py \
        backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/tag_link_repository.py \
        backend/tests/integration/test_tagging_provider.py
git commit -m "feat(tagging): public entity_exists_in_workspace + link-repo provider"
```

---

## Task 2: `AssignTag` + `UnassignTag` use cases

**Files:**
- Create: `src/cellar/application/workspace_config/tagging/__init__.py`
- Create: `src/cellar/application/workspace_config/tagging/assign_tag.py`
- Create: `src/cellar/application/workspace_config/tagging/unassign_tag.py`
- Create: `backend/tests/unit/application/workspace_config/tagging/__init__.py`
- Create: `backend/tests/unit/application/workspace_config/tagging/_helpers.py`
- Test: `backend/tests/unit/application/workspace_config/tagging/test_assign_unassign.py`

- [ ] **Step 1: Create the application package marker**

Create `src/cellar/application/workspace_config/tagging/__init__.py` (empty).

- [ ] **Step 2: Write the test helpers**

Create `backend/tests/unit/application/workspace_config/tagging/__init__.py` (empty), then `backend/tests/unit/application/workspace_config/tagging/_helpers.py`:

```python
"""Fakes for tagging use-case unit tests."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

from cellar.domain.shared.events import DomainEvent
from cellar.domain.workspace_config.tagging.tag import Tag, TaggableEntityType, TagName


class FakeUnitOfWork:
    """Async-context UoW that collects + clears events from tracked aggregates."""

    def __init__(self) -> None:
        self._tracked: list = []

    @property
    def is_active(self) -> bool:
        return True

    def track(self, aggregate) -> None:
        if aggregate not in self._tracked:
            self._tracked.append(aggregate)

    async def commit(self) -> list[DomainEvent]:
        events: list[DomainEvent] = []
        for agg in self._tracked:
            events.extend(agg.collect_events())
            agg.clear_events()
        return events

    async def rollback(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass


def fake_auth(*, role: str = "editor"):
    auth = AsyncMock()
    auth.user_id = uuid.uuid4()
    auth.workspace_id = uuid.uuid4()
    auth.workspace_role = role
    auth.is_admin = role in ("admin", "owner")
    rank = {"viewer": 0, "editor": 1, "admin": 2, "owner": 3}
    auth.has_role = lambda m: rank.get(role, 0) >= rank.get(m, 99)
    return auth


def make_tag(workspace_id: uuid.UUID, key: str, value: str | None, created_by: uuid.UUID) -> Tag:
    """A freshly-created Tag (carries a TagCreated event, like get_or_create on a new row)."""
    return Tag.create(
        workspace_id=workspace_id, name=TagName(key=key, value=value), created_by=created_by
    )


def make_tag_repo(*, get_or_create: Tag, find_by_id: Tag | None = None) -> AsyncMock:
    repo = AsyncMock()
    repo.get_or_create = AsyncMock(return_value=get_or_create)
    repo.find_by_id_in_workspace = AsyncMock(return_value=find_by_id)
    return repo


def make_link_provider(
    *, entity_exists: bool = True, current_tags: list[Tag] | None = None
) -> AsyncMock:
    link_repo = AsyncMock()
    link_repo.entity_exists_in_workspace = AsyncMock(return_value=entity_exists)
    link_repo.add = AsyncMock()
    link_repo.remove = AsyncMock()
    link_repo.set_for_entity = AsyncMock()
    link_repo.find_tags_for_entity = AsyncMock(return_value=current_tags or [])
    provider = AsyncMock()
    provider.for_type = lambda _et: link_repo
    provider.link_repo = link_repo  # exposed for assertions
    return provider
```

- [ ] **Step 3: Write the failing unit tests**

Create `backend/tests/unit/application/workspace_config/tagging/test_assign_unassign.py`:

```python
"""Unit tests for AssignTag and UnassignTag use cases."""

from __future__ import annotations

import uuid

import pytest
from returns.result import Failure, Success

from cellar.application.workspace_config.tagging.assign_tag import (
    AssignTag,
    AssignTagCommand,
)
from cellar.application.workspace_config.tagging.unassign_tag import (
    UnassignTag,
    UnassignTagCommand,
)
from cellar.domain.shared.errors import AuthorizationError, NotFoundError, ValidationError
from cellar.domain.workspace_config.tagging.events import TagAssigned, TagUnassigned
from cellar.domain.workspace_config.tagging.tag import TaggableEntityType
from tests.unit.application.workspace_config.tagging._helpers import (
    FakeUnitOfWork,
    fake_auth,
    make_link_provider,
    make_tag,
    make_tag_repo,
)
from unittest.mock import AsyncMock


def _assign_cmd(auth, *, key="env", value="prod"):
    return AssignTagCommand(
        workspace_id=auth.workspace_id,
        entity_type=TaggableEntityType.MOLECULE,
        entity_id=uuid.uuid4(),
        key=key,
        value=value,
        assigned_by=auth.user_id,
    )


class TestAssignTag:
    @pytest.mark.asyncio
    async def test_assigns_and_emits_event(self) -> None:
        auth = fake_auth()
        tag = make_tag(auth.workspace_id, "env", "prod", auth.user_id)
        repo = make_tag_repo(get_or_create=tag)
        provider = make_link_provider(entity_exists=True)
        dispatcher = AsyncMock()
        uc = AssignTag(FakeUnitOfWork(), repo, provider, dispatcher)

        result = await uc(_assign_cmd(auth), auth=auth)

        assert isinstance(result, Success)
        provider.link_repo.add.assert_awaited_once()
        events = dispatcher.dispatch_all.call_args.args[0]
        assert any(isinstance(e, TagAssigned) for e in events)

    @pytest.mark.asyncio
    async def test_missing_entity_returns_not_found(self) -> None:
        auth = fake_auth()
        tag = make_tag(auth.workspace_id, "env", "prod", auth.user_id)
        repo = make_tag_repo(get_or_create=tag)
        provider = make_link_provider(entity_exists=False)
        uc = AssignTag(FakeUnitOfWork(), repo, provider, AsyncMock())

        result = await uc(_assign_cmd(auth), auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        provider.link_repo.add.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_key_returns_validation_error(self) -> None:
        auth = fake_auth()
        tag = make_tag(auth.workspace_id, "x", None, auth.user_id)
        uc = AssignTag(FakeUnitOfWork(), make_tag_repo(get_or_create=tag), make_link_provider(), AsyncMock())

        result = await uc(_assign_cmd(auth, key="   ", value=None), auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)

    @pytest.mark.asyncio
    async def test_viewer_denied(self) -> None:
        auth = fake_auth(role="viewer")
        tag = make_tag(auth.workspace_id, "env", "prod", auth.user_id)
        uc = AssignTag(FakeUnitOfWork(), make_tag_repo(get_or_create=tag), make_link_provider(), AsyncMock())

        with pytest.raises(AuthorizationError):
            await uc(_assign_cmd(auth), auth=auth)


class TestUnassignTag:
    @pytest.mark.asyncio
    async def test_unassigns_and_emits_event(self) -> None:
        auth = fake_auth()
        tag = make_tag(auth.workspace_id, "env", "prod", auth.user_id)
        tag.clear_events()  # simulate an existing (already-persisted) tag
        repo = make_tag_repo(get_or_create=tag, find_by_id=tag)
        provider = make_link_provider(entity_exists=True)
        dispatcher = AsyncMock()
        uc = UnassignTag(FakeUnitOfWork(), repo, provider, dispatcher)

        cmd = UnassignTagCommand(
            workspace_id=auth.workspace_id,
            entity_type=TaggableEntityType.MOLECULE,
            entity_id=uuid.uuid4(),
            tag_id=tag.id,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        provider.link_repo.remove.assert_awaited_once()
        events = dispatcher.dispatch_all.call_args.args[0]
        assert any(isinstance(e, TagUnassigned) for e in events)

    @pytest.mark.asyncio
    async def test_unknown_tag_returns_not_found(self) -> None:
        auth = fake_auth()
        repo = make_tag_repo(get_or_create=make_tag(auth.workspace_id, "x", None, auth.user_id), find_by_id=None)
        uc = UnassignTag(FakeUnitOfWork(), repo, make_link_provider(), AsyncMock())

        cmd = UnassignTagCommand(
            workspace_id=auth.workspace_id,
            entity_type=TaggableEntityType.MOLECULE,
            entity_id=uuid.uuid4(),
            tag_id=uuid.uuid4(),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
```

- [ ] **Step 4: Run to verify it fails**

Run: `uv run pytest tests/unit/application/workspace_config/tagging/test_assign_unassign.py -v`
Expected: FAIL — `ModuleNotFoundError: …assign_tag`.

- [ ] **Step 5: Write `AssignTag`**

Create `src/cellar/application/workspace_config/tagging/assign_tag.py`:

```python
"""AssignTag — apply a (key, optional value) tag to an entity."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError
from cellar.domain.workspace_config.tagging.events import TagAssigned
from cellar.domain.workspace_config.tagging.repository import (
    TagLinkRepositoryProvider,
    TagRepository,
)
from cellar.domain.workspace_config.tagging.tag import Tag, TaggableEntityType, TagName


@dataclass(frozen=True, kw_only=True)
class AssignTagCommand(Command):
    workspace_id: uuid.UUID
    entity_type: TaggableEntityType
    entity_id: uuid.UUID
    key: str
    value: str | None
    assigned_by: uuid.UUID


class AssignTag:
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
        self, input: AssignTagCommand, auth: AuthContext | None = None
    ) -> Result[Tag, DomainError]:
        require_editor(auth)
        try:
            name = TagName(key=input.key, value=input.value)
        except ValueError as exc:
            return Failure(ValidationError(str(exc)))

        async with self._uow:
            link_repo = self._link_provider.for_type(input.entity_type)
            if not await link_repo.entity_exists_in_workspace(
                input.workspace_id, input.entity_id
            ):
                return Failure(NotFoundError(input.entity_type.value, str(input.entity_id)))

            tag = await self._tag_repo.get_or_create(
                input.workspace_id, name, input.assigned_by
            )
            tag.register_event(
                TagAssigned(
                    aggregate_id=tag.id,
                    aggregate_type="Tag",
                    workspace_id=input.workspace_id,
                    target_type=input.entity_type.value,
                    target_id=input.entity_id,
                )
            )
            self._uow.track(tag)
            await link_repo.add(
                input.workspace_id, input.entity_id, tag.id, input.assigned_by
            )
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(tag)
```

- [ ] **Step 6: Write `UnassignTag`**

Create `src/cellar/application/workspace_config/tagging/unassign_tag.py`:

```python
"""UnassignTag — remove a tag from an entity."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError
from cellar.domain.workspace_config.tagging.events import TagUnassigned
from cellar.domain.workspace_config.tagging.repository import (
    TagLinkRepositoryProvider,
    TagRepository,
)
from cellar.domain.workspace_config.tagging.tag import TaggableEntityType


@dataclass(frozen=True, kw_only=True)
class UnassignTagCommand(Command):
    workspace_id: uuid.UUID
    entity_type: TaggableEntityType
    entity_id: uuid.UUID
    tag_id: uuid.UUID


class UnassignTag:
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
        self, input: UnassignTagCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)

        async with self._uow:
            tag = await self._tag_repo.find_by_id_in_workspace(
                input.workspace_id, input.tag_id
            )
            if tag is None:
                return Failure(NotFoundError("Tag", str(input.tag_id)))

            link_repo = self._link_provider.for_type(input.entity_type)
            if not await link_repo.entity_exists_in_workspace(
                input.workspace_id, input.entity_id
            ):
                return Failure(NotFoundError(input.entity_type.value, str(input.entity_id)))

            await link_repo.remove(input.workspace_id, input.entity_id, input.tag_id)
            tag.register_event(
                TagUnassigned(
                    aggregate_id=tag.id,
                    aggregate_type="Tag",
                    workspace_id=input.workspace_id,
                    target_type=input.entity_type.value,
                    target_id=input.entity_id,
                )
            )
            self._uow.track(tag)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)
```

- [ ] **Step 7: Run to verify it passes**

Run: `uv run pytest tests/unit/application/workspace_config/tagging/test_assign_unassign.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/src/cellar/application/workspace_config/tagging/__init__.py \
        backend/src/cellar/application/workspace_config/tagging/assign_tag.py \
        backend/src/cellar/application/workspace_config/tagging/unassign_tag.py \
        backend/tests/unit/application/workspace_config/tagging/
git commit -m "feat(tagging): AssignTag + UnassignTag use cases"
```

---

## Task 3: `SetEntityTags` use case

**Files:**
- Create: `src/cellar/application/workspace_config/tagging/set_entity_tags.py`
- Test: `backend/tests/unit/application/workspace_config/tagging/test_set_entity_tags.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/application/workspace_config/tagging/test_set_entity_tags.py`:

```python
"""Unit tests for SetEntityTags (reconcile an entity's tag set)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.workspace_config.tagging.set_entity_tags import (
    SetEntityTags,
    SetEntityTagsCommand,
    TagInput,
)
from cellar.domain.shared.errors import NotFoundError
from cellar.domain.workspace_config.tagging.events import TagAssigned, TagUnassigned
from cellar.domain.workspace_config.tagging.tag import TaggableEntityType
from tests.unit.application.workspace_config.tagging._helpers import (
    FakeUnitOfWork,
    fake_auth,
    make_link_provider,
    make_tag,
)


class TestSetEntityTags:
    @pytest.mark.asyncio
    async def test_reconcile_emits_added_and_removed_events(self) -> None:
        auth = fake_auth()
        keep = make_tag(auth.workspace_id, "keep", None, auth.user_id); keep.clear_events()
        drop = make_tag(auth.workspace_id, "drop", None, auth.user_id); drop.clear_events()
        add = make_tag(auth.workspace_id, "add", None, auth.user_id); add.clear_events()

        # current set on the entity = {keep, drop}; desired = {keep, add}
        provider = make_link_provider(entity_exists=True, current_tags=[keep, drop])

        # get_or_create returns keep then add (in input order)
        tag_repo = AsyncMock()
        tag_repo.get_or_create = AsyncMock(side_effect=[keep, add])

        dispatcher = AsyncMock()
        uc = SetEntityTags(FakeUnitOfWork(), tag_repo, provider, dispatcher)

        cmd = SetEntityTagsCommand(
            workspace_id=auth.workspace_id,
            entity_type=TaggableEntityType.MOLECULE,
            entity_id=uuid.uuid4(),
            tags=(TagInput(key="keep"), TagInput(key="add")),
            assigned_by=auth.user_id,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        provider.link_repo.set_for_entity.assert_awaited_once()
        events = dispatcher.dispatch_all.call_args.args[0]
        assigned = [e for e in events if isinstance(e, TagAssigned)]
        unassigned = [e for e in events if isinstance(e, TagUnassigned)]
        assert len(assigned) == 1 and assigned[0].aggregate_id == add.id
        assert len(unassigned) == 1 and unassigned[0].aggregate_id == drop.id

    @pytest.mark.asyncio
    async def test_missing_entity_returns_not_found(self) -> None:
        auth = fake_auth()
        provider = make_link_provider(entity_exists=False)
        uc = SetEntityTags(FakeUnitOfWork(), AsyncMock(), provider, AsyncMock())
        cmd = SetEntityTagsCommand(
            workspace_id=auth.workspace_id,
            entity_type=TaggableEntityType.MOLECULE,
            entity_id=uuid.uuid4(),
            tags=(TagInput(key="a"),),
            assigned_by=auth.user_id,
        )
        result = await uc(cmd, auth=auth)
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/application/workspace_config/tagging/test_set_entity_tags.py -v`
Expected: FAIL — `ModuleNotFoundError: …set_entity_tags`.

- [ ] **Step 3: Write `SetEntityTags`**

Create `src/cellar/application/workspace_config/tagging/set_entity_tags.py`:

```python
"""SetEntityTags — reconcile an entity's full tag set (detail-page editor)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError
from cellar.domain.workspace_config.tagging.events import TagAssigned, TagUnassigned
from cellar.domain.workspace_config.tagging.repository import (
    TagLinkRepositoryProvider,
    TagRepository,
)
from cellar.domain.workspace_config.tagging.tag import Tag, TaggableEntityType, TagName


@dataclass(frozen=True, kw_only=True)
class TagInput:
    key: str
    value: str | None = None


@dataclass(frozen=True, kw_only=True)
class SetEntityTagsCommand(Command):
    workspace_id: uuid.UUID
    entity_type: TaggableEntityType
    entity_id: uuid.UUID
    tags: tuple[TagInput, ...]
    assigned_by: uuid.UUID


class SetEntityTags:
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
        self, input: SetEntityTagsCommand, auth: AuthContext | None = None
    ) -> Result[list[Tag], DomainError]:
        require_editor(auth)
        try:
            names = [TagName(key=t.key, value=t.value) for t in input.tags]
        except ValueError as exc:
            return Failure(ValidationError(str(exc)))

        async with self._uow:
            link_repo = self._link_provider.for_type(input.entity_type)
            if not await link_repo.entity_exists_in_workspace(
                input.workspace_id, input.entity_id
            ):
                return Failure(NotFoundError(input.entity_type.value, str(input.entity_id)))

            current = await link_repo.find_tags_for_entity(
                input.workspace_id, input.entity_id
            )
            current_by_id = {t.id: t for t in current}

            desired: dict[uuid.UUID, Tag] = {}
            for name in names:
                tag = await self._tag_repo.get_or_create(
                    input.workspace_id, name, input.assigned_by
                )
                desired[tag.id] = tag

            for tag_id, tag in desired.items():
                if tag_id not in current_by_id:
                    tag.register_event(
                        TagAssigned(
                            aggregate_id=tag.id,
                            aggregate_type="Tag",
                            workspace_id=input.workspace_id,
                            target_type=input.entity_type.value,
                            target_id=input.entity_id,
                        )
                    )
                    self._uow.track(tag)
            for tag_id, tag in current_by_id.items():
                if tag_id not in desired:
                    tag.register_event(
                        TagUnassigned(
                            aggregate_id=tag.id,
                            aggregate_type="Tag",
                            workspace_id=input.workspace_id,
                            target_type=input.entity_type.value,
                            target_id=input.entity_id,
                        )
                    )
                    self._uow.track(tag)

            await link_repo.set_for_entity(
                input.workspace_id, input.entity_id, list(desired.keys()), input.assigned_by
            )
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(list(desired.values()))
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/application/workspace_config/tagging/test_set_entity_tags.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/application/workspace_config/tagging/set_entity_tags.py \
        backend/tests/unit/application/workspace_config/tagging/test_set_entity_tags.py
git commit -m "feat(tagging): SetEntityTags reconcile use case"
```

---

## Task 4: `ListTags` + `GetTagsForEntity` queries

**Files:**
- Create: `src/cellar/application/workspace_config/tagging/list_tags.py`
- Create: `src/cellar/application/workspace_config/tagging/get_tags_for_entity.py`
- Test: `backend/tests/unit/application/workspace_config/tagging/test_list_and_get.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/application/workspace_config/tagging/test_list_and_get.py`:

```python
"""Unit tests for ListTags and GetTagsForEntity queries."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Success

from cellar.application.workspace_config.tagging.get_tags_for_entity import (
    GetTagsForEntity,
    GetTagsForEntityQuery,
)
from cellar.application.workspace_config.tagging.list_tags import ListTags, ListTagsQuery
from cellar.domain.workspace_config.tagging.tag import TaggableEntityType
from tests.unit.application.workspace_config.tagging._helpers import (
    FakeUnitOfWork,
    fake_auth,
    make_link_provider,
    make_tag,
)


class TestListTags:
    @pytest.mark.asyncio
    async def test_passes_filters_to_repo(self) -> None:
        auth = fake_auth()
        tag = make_tag(auth.workspace_id, "kinase", None, auth.user_id)
        repo = AsyncMock()
        repo.search = AsyncMock(return_value=[tag])
        uc = ListTags(FakeUnitOfWork(), repo)

        query = ListTagsQuery(workspace_id=auth.workspace_id, q="kin", created_by=auth.user_id, limit=10)
        result = await uc(query, auth=auth)

        assert isinstance(result, Success)
        assert result.unwrap() == [tag]
        repo.search.assert_awaited_once_with(
            auth.workspace_id, q="kin", created_by=auth.user_id, limit=10
        )


class TestGetTagsForEntity:
    @pytest.mark.asyncio
    async def test_returns_entity_tags(self) -> None:
        auth = fake_auth()
        tag = make_tag(auth.workspace_id, "hit", None, auth.user_id)
        provider = make_link_provider(current_tags=[tag])
        uc = GetTagsForEntity(FakeUnitOfWork(), provider)

        query = GetTagsForEntityQuery(
            workspace_id=auth.workspace_id,
            entity_type=TaggableEntityType.MOLECULE,
            entity_id=uuid.uuid4(),
        )
        result = await uc(query, auth=auth)

        assert isinstance(result, Success)
        assert result.unwrap() == [tag]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/application/workspace_config/tagging/test_list_and_get.py -v`
Expected: FAIL — `ModuleNotFoundError: …list_tags`.

- [ ] **Step 3: Write `ListTags`**

Create `src/cellar/application/workspace_config/tagging/list_tags.py`:

```python
"""ListTags — autocomplete / listing of tags in a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError
from cellar.domain.workspace_config.tagging.repository import TagRepository
from cellar.domain.workspace_config.tagging.tag import Tag


@dataclass(frozen=True, kw_only=True)
class ListTagsQuery:
    workspace_id: uuid.UUID
    q: str | None = None
    created_by: uuid.UUID | None = None
    limit: int = 50


class ListTags:
    def __init__(self, uow: UnitOfWork, tag_repo: TagRepository) -> None:
        self._uow = uow
        self._tag_repo = tag_repo

    async def __call__(
        self, input: ListTagsQuery, auth: AuthContext | None = None
    ) -> Result[list[Tag], DomainError]:
        async with self._uow:
            tags = await self._tag_repo.search(
                input.workspace_id,
                q=input.q,
                created_by=input.created_by,
                limit=input.limit,
            )
        return Success(tags)
```

- [ ] **Step 4: Write `GetTagsForEntity`**

Create `src/cellar/application/workspace_config/tagging/get_tags_for_entity.py`:

```python
"""GetTagsForEntity — the tags currently applied to one entity."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError
from cellar.domain.workspace_config.tagging.repository import TagLinkRepositoryProvider
from cellar.domain.workspace_config.tagging.tag import Tag, TaggableEntityType


@dataclass(frozen=True, kw_only=True)
class GetTagsForEntityQuery:
    workspace_id: uuid.UUID
    entity_type: TaggableEntityType
    entity_id: uuid.UUID


class GetTagsForEntity:
    def __init__(
        self, uow: UnitOfWork, link_provider: TagLinkRepositoryProvider
    ) -> None:
        self._uow = uow
        self._link_provider = link_provider

    async def __call__(
        self, input: GetTagsForEntityQuery, auth: AuthContext | None = None
    ) -> Result[list[Tag], DomainError]:
        async with self._uow:
            link_repo = self._link_provider.for_type(input.entity_type)
            tags = await link_repo.find_tags_for_entity(
                input.workspace_id, input.entity_id
            )
        return Success(tags)
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/unit/application/workspace_config/tagging/ -v`
Expected: PASS (all tagging application unit tests).

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/application/workspace_config/tagging/list_tags.py \
        backend/src/cellar/application/workspace_config/tagging/get_tags_for_entity.py \
        backend/tests/unit/application/workspace_config/tagging/test_list_and_get.py
git commit -m "feat(tagging): ListTags + GetTagsForEntity queries"
```

---

## Task 5: DI wiring + dependency aliases

**Files:**
- Modify: `src/cellar/infrastructure/di/_workspace_config.py`
- Modify: `src/cellar/interface/dependencies/_workspace_config.py`

- [ ] **Step 1: Register the use cases in the DI container**

In `src/cellar/infrastructure/di/_workspace_config.py`, add these imports near the other application/infra imports at the top:

```python
from cellar.application.workspace_config.tagging.assign_tag import AssignTag
from cellar.application.workspace_config.tagging.get_tags_for_entity import GetTagsForEntity
from cellar.application.workspace_config.tagging.list_tags import ListTags
from cellar.application.workspace_config.tagging.set_entity_tags import SetEntityTags
from cellar.application.workspace_config.tagging.unassign_tag import UnassignTag
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_link_repository import (
    SQLAlchemyTagLinkRepositoryProvider,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_repository import (
    SQLAlchemyTagRepository,
)
```

Then, inside `register_workspace_config(container)`, add this block (after the existing vocabulary registrations):

```python
    # --- Tags ---
    def _tag_assign(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(
                uow,
                SQLAlchemyTagRepository(uow),
                SQLAlchemyTagLinkRepositoryProvider(uow),
                c[EventDispatcher],
            )

        return _f

    container.define(AssignTag, _tag_assign(AssignTag))
    container.define(UnassignTag, _tag_assign(UnassignTag))
    container.define(SetEntityTags, _tag_assign(SetEntityTags))

    def _list_tags(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListTags(uow, SQLAlchemyTagRepository(uow))

    container.define(ListTags, _list_tags)

    def _get_tags_for_entity(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetTagsForEntity(uow, SQLAlchemyTagLinkRepositoryProvider(uow))

    container.define(GetTagsForEntity, _get_tags_for_entity)
```

- [ ] **Step 2: Verify the DI module parses**

Run: `uv run python -c "import cellar.infrastructure.di._workspace_config"`
Expected: exit 0, no output (the new use-case / repo / provider imports + the `register_workspace_config` body parse cleanly). This module imports only application + infrastructure — no Sentinel env needed. Actual container resolution is exercised by the API tests in Task 7.

- [ ] **Step 3: Add the dependency aliases**

In `src/cellar/interface/dependencies/_workspace_config.py`, add the imports + aliases:

```python
from cellar.application.workspace_config.tagging.assign_tag import AssignTag
from cellar.application.workspace_config.tagging.get_tags_for_entity import GetTagsForEntity
from cellar.application.workspace_config.tagging.list_tags import ListTags
from cellar.application.workspace_config.tagging.set_entity_tags import SetEntityTags
from cellar.application.workspace_config.tagging.unassign_tag import UnassignTag
```

```python
AssignTagDep = Annotated[AssignTag, Depends(_get_use_case(AssignTag))]
UnassignTagDep = Annotated[UnassignTag, Depends(_get_use_case(UnassignTag))]
SetEntityTagsDep = Annotated[SetEntityTags, Depends(_get_use_case(SetEntityTags))]
ListTagsDep = Annotated[ListTags, Depends(_get_use_case(ListTags))]
GetTagsForEntityDep = Annotated[GetTagsForEntity, Depends(_get_use_case(GetTagsForEntity))]
```

(If `_get_use_case`, `Annotated`, or `Depends` aren't already imported in this file, add `from typing import Annotated`, `from fastapi import Depends`, and `from ._core import _get_use_case` — match the existing imports in the file.)

- [ ] **Step 4: Verify imports**

Run: `env SENTINEL_SERVICE_KEY=test SENTINEL_URL=https://sentinel.example.com SENTINEL_SERVICE_NAME=cellar TEMPORAL_DISABLED=1 uv run python -c "import cellar.interface.dependencies._workspace_config as m; print(m.AssignTagDep is not None)"`
Expected: prints `True`. (Interface imports transitively pull in the Sentinel SDK, which reads these env vars at import time — the same vars `tests/api/conftest.py` sets before importing cellar.)

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/di/_workspace_config.py \
        backend/src/cellar/interface/dependencies/_workspace_config.py
git commit -m "feat(tagging): DI wiring + route dependency aliases"
```

---

## Task 6: Routes (management + assignment) + registration

**Files:**
- Create: `src/cellar/interface/routes/tags.py`
- Modify: `src/cellar/interface/app.py`
- Modify: `backend/tests/api/conftest.py`

- [ ] **Step 1: Write the routes module**

Create `src/cellar/interface/routes/tags.py`:

```python
"""Tag management + per-entity assignment routes."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Response
from pydantic import BaseModel

from cellar.application.workspace_config.tagging.assign_tag import AssignTagCommand
from cellar.application.workspace_config.tagging.get_tags_for_entity import (
    GetTagsForEntityQuery,
)
from cellar.application.workspace_config.tagging.list_tags import ListTagsQuery
from cellar.application.workspace_config.tagging.set_entity_tags import (
    SetEntityTagsCommand,
    TagInput,
)
from cellar.application.workspace_config.tagging.unassign_tag import UnassignTagCommand
from cellar.domain.shared.errors import NotFoundError
from cellar.domain.workspace_config.tagging.tag import Tag, TaggableEntityType
from cellar.interface.dependencies import AuthDep
from cellar.interface.dependencies._workspace_config import (
    AssignTagDep,
    GetTagsForEntityDep,
    ListTagsDep,
    SetEntityTagsDep,
    UnassignTagDep,
)
from cellar.interface.error_handlers import result_to_response


class TagResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    key: str
    value: str | None
    created_by: uuid.UUID
    created_at: datetime

    @classmethod
    def from_domain(cls, tag: Tag) -> TagResponse:
        return cls(
            id=tag.id,
            workspace_id=tag.workspace_id,
            key=tag.key,
            value=tag.value,
            created_by=tag.created_by,
            created_at=tag.created_at,
        )


class AssignTagBody(BaseModel):
    key: str
    value: str | None = None


class TagItemBody(BaseModel):
    key: str
    value: str | None = None


class SetEntityTagsBody(BaseModel):
    tags: list[TagItemBody]


_ENTITY_COLLECTIONS: dict[str, TaggableEntityType] = {
    "molecules": TaggableEntityType.MOLECULE,
    "protocols": TaggableEntityType.PROTOCOL,
    "projects": TaggableEntityType.PROJECT,
    "collections": TaggableEntityType.COLLECTION,
}


def _resolve_entity_type(entity_collection: str) -> TaggableEntityType:
    entity_type = _ENTITY_COLLECTIONS.get(entity_collection)
    if entity_type is None:
        raise NotFoundError("Entity", entity_collection)
    return entity_type


# --- Management ---
router = APIRouter(prefix="/api/v1/tags", tags=["tags"])


@router.get("", response_model=list[TagResponse])
async def list_tags(
    auth: AuthDep,
    use_case: ListTagsDep,
    q: str | None = None,
    mine: bool = False,
    limit: int = 50,
) -> list[TagResponse]:
    query = ListTagsQuery(
        workspace_id=auth.workspace_id,
        q=q,
        created_by=auth.user_id if mine else None,
        limit=limit,
    )
    tags = result_to_response(await use_case(query, auth=auth))
    return [TagResponse.from_domain(t) for t in tags]


# --- Per-entity assignment (generic over entity collection) ---
assignment_router = APIRouter(prefix="/api/v1", tags=["tags"])


@assignment_router.get(
    "/{entity_collection}/{entity_id}/tags", response_model=list[TagResponse]
)
async def get_entity_tags(
    entity_collection: str,
    entity_id: uuid.UUID,
    auth: AuthDep,
    use_case: GetTagsForEntityDep,
) -> list[TagResponse]:
    query = GetTagsForEntityQuery(
        workspace_id=auth.workspace_id,
        entity_type=_resolve_entity_type(entity_collection),
        entity_id=entity_id,
    )
    tags = result_to_response(await use_case(query, auth=auth))
    return [TagResponse.from_domain(t) for t in tags]


@assignment_router.post(
    "/{entity_collection}/{entity_id}/tags",
    response_model=TagResponse,
    status_code=201,
)
async def assign_entity_tag(
    entity_collection: str,
    entity_id: uuid.UUID,
    body: AssignTagBody,
    auth: AuthDep,
    use_case: AssignTagDep,
) -> TagResponse:
    command = AssignTagCommand(
        workspace_id=auth.workspace_id,
        entity_type=_resolve_entity_type(entity_collection),
        entity_id=entity_id,
        key=body.key,
        value=body.value,
        assigned_by=auth.user_id,
    )
    tag = result_to_response(await use_case(command, auth=auth))
    return TagResponse.from_domain(tag)


@assignment_router.put(
    "/{entity_collection}/{entity_id}/tags", response_model=list[TagResponse]
)
async def set_entity_tags(
    entity_collection: str,
    entity_id: uuid.UUID,
    body: SetEntityTagsBody,
    auth: AuthDep,
    use_case: SetEntityTagsDep,
) -> list[TagResponse]:
    command = SetEntityTagsCommand(
        workspace_id=auth.workspace_id,
        entity_type=_resolve_entity_type(entity_collection),
        entity_id=entity_id,
        tags=tuple(TagInput(key=t.key, value=t.value) for t in body.tags),
        assigned_by=auth.user_id,
    )
    tags = result_to_response(await use_case(command, auth=auth))
    return [TagResponse.from_domain(t) for t in tags]


@assignment_router.delete(
    "/{entity_collection}/{entity_id}/tags/{tag_id}", status_code=204
)
async def unassign_entity_tag(
    entity_collection: str,
    entity_id: uuid.UUID,
    tag_id: uuid.UUID,
    auth: AuthDep,
    use_case: UnassignTagDep,
) -> Response:
    command = UnassignTagCommand(
        workspace_id=auth.workspace_id,
        entity_type=_resolve_entity_type(entity_collection),
        entity_id=entity_id,
        tag_id=tag_id,
    )
    result_to_response(await use_case(command, auth=auth))
    return Response(status_code=204)
```

> Verify `AuthDep` is exported from `cellar.interface.dependencies` (the agent confirmed `AuthDep` lives in `dependencies/_core.py`; if `from cellar.interface.dependencies import AuthDep` fails, import it from `cellar.interface.dependencies._core`).

- [ ] **Step 2: Register both routers in the production app**

In `src/cellar/interface/app.py`, add to the route imports block:

```python
from cellar.interface.routes.tags import assignment_router as tag_assignment_router
from cellar.interface.routes.tags import router as tags_router
```

and in the `app.include_router(...)` block:

```python
app.include_router(tags_router)
app.include_router(tag_assignment_router)
```

- [ ] **Step 3: Register both routers in the API test app**

In `backend/tests/api/conftest.py`, inside `_create_test_app`, add the imports alongside the other route imports and the two `app.include_router(...)` calls (so API tests can reach the endpoints):

```python
    from cellar.interface.routes.tags import assignment_router as tag_assignment_router
    from cellar.interface.routes.tags import router as tags_router
```

```python
    app.include_router(tags_router)
    app.include_router(tag_assignment_router)
```

- [ ] **Step 4: Verify the app builds with the new routes**

Run: `env SENTINEL_SERVICE_KEY=test SENTINEL_URL=https://sentinel.example.com SENTINEL_SERVICE_NAME=cellar TEMPORAL_DISABLED=1 uv run python -c "import cellar.interface.routes.tags as t; print(t.router.prefix, t.assignment_router.prefix, sorted(t._ENTITY_COLLECTIONS))"`
Expected: `/api/v1/tags /api/v1 ['collections', 'molecules', 'projects', 'protocols']`. (Sentinel env needed because the routes module imports interface dependencies.)

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/interface/routes/tags.py \
        backend/src/cellar/interface/app.py \
        backend/tests/api/conftest.py
git commit -m "feat(tagging): management + per-entity assignment routes"
```

---

## Task 7: API tests + `viewer_client` fixture

**Files:**
- Modify: `backend/tests/api/conftest.py` (add `viewer_client`)
- Test: `backend/tests/api/test_tags.py`

- [ ] **Step 1: Add a `viewer_client` fixture**

In `backend/tests/api/conftest.py`, add (mirroring the existing `editor_client` fixture):

```python
@pytest.fixture
async def viewer_client(
    database_url: str, _run_migrations: None, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> AsyncIterator[AsyncClient]:
    """Async HTTP client scoped to a viewer role (for 403 tests)."""
    viewer_auth = FakeAuth(role="viewer", workspace_id=workspace_id, user_id=user_id)
    app = _create_test_app(database_url, viewer_auth)
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    engine = app.state.container[AsyncEngine]
    await engine.dispose()
```

- [ ] **Step 2: Write the API tests**

Create `backend/tests/api/test_tags.py`:

```python
"""API tests for tagging endpoints (assignment uses collections — easy to create)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def _make_collection(client: AsyncClient, name: str) -> str:
    resp = await client.post("/api/v1/collections", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class TestAssignAndRead:
    async def test_assign_then_get(self, client: AsyncClient) -> None:
        cid = await _make_collection(client, "TagCol-1")
        resp = await client.post(
            f"/api/v1/collections/{cid}/tags", json={"key": "Project", "value": "Alpha"}
        )
        assert resp.status_code == 201, resp.text
        tag = resp.json()
        assert tag["key"] == "Project"
        assert tag["value"] == "Alpha"

        got = await client.get(f"/api/v1/collections/{cid}/tags")
        assert got.status_code == 200
        assert [t["key"] for t in got.json()] == ["Project"]

    async def test_assign_valueless(self, client: AsyncClient) -> None:
        cid = await _make_collection(client, "TagCol-2")
        resp = await client.post(f"/api/v1/collections/{cid}/tags", json={"key": "favorite"})
        assert resp.status_code == 201
        assert resp.json()["value"] is None

    async def test_set_reconciles(self, client: AsyncClient) -> None:
        cid = await _make_collection(client, "TagCol-3")
        await client.post(f"/api/v1/collections/{cid}/tags", json={"key": "a"})
        await client.post(f"/api/v1/collections/{cid}/tags", json={"key": "b"})
        resp = await client.put(
            f"/api/v1/collections/{cid}/tags",
            json={"tags": [{"key": "b"}, {"key": "c"}]},
        )
        assert resp.status_code == 200
        assert {t["key"] for t in resp.json()} == {"b", "c"}
        got = await client.get(f"/api/v1/collections/{cid}/tags")
        assert {t["key"] for t in got.json()} == {"b", "c"}

    async def test_unassign(self, client: AsyncClient) -> None:
        cid = await _make_collection(client, "TagCol-4")
        created = await client.post(f"/api/v1/collections/{cid}/tags", json={"key": "x"})
        tag_id = created.json()["id"]
        resp = await client.delete(f"/api/v1/collections/{cid}/tags/{tag_id}")
        assert resp.status_code == 204
        got = await client.get(f"/api/v1/collections/{cid}/tags")
        assert got.json() == []


class TestErrors:
    async def test_assign_to_missing_collection_404(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"/api/v1/collections/{uuid.uuid4()}/tags", json={"key": "x"}
        )
        assert resp.status_code == 404

    async def test_unknown_entity_collection_404(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"/api/v1/widgets/{uuid.uuid4()}/tags", json={"key": "x"}
        )
        assert resp.status_code == 404

    async def test_empty_key_422(self, client: AsyncClient) -> None:
        cid = await _make_collection(client, "TagCol-5")
        resp = await client.post(f"/api/v1/collections/{cid}/tags", json={"key": "   "})
        assert resp.status_code == 422


class TestListTags:
    async def test_list_and_search(self, client: AsyncClient) -> None:
        cid = await _make_collection(client, "TagCol-6")
        await client.post(f"/api/v1/collections/{cid}/tags", json={"key": "kinase"})
        await client.post(f"/api/v1/collections/{cid}/tags", json={"key": "solubility"})
        all_resp = await client.get("/api/v1/tags")
        assert all_resp.status_code == 200
        keys = {t["key"] for t in all_resp.json()}
        assert {"kinase", "solubility"} <= keys
        kin = await client.get("/api/v1/tags", params={"q": "kin"})
        assert {t["key"] for t in kin.json()} == {"kinase"}

    async def test_mine_filter(self, client: AsyncClient) -> None:
        cid = await _make_collection(client, "TagCol-7")
        await client.post(f"/api/v1/collections/{cid}/tags", json={"key": "mine-tag"})
        resp = await client.get("/api/v1/tags", params={"mine": "true"})
        assert resp.status_code == 200
        assert any(t["key"] == "mine-tag" for t in resp.json())


class TestAuth:
    async def test_viewer_cannot_assign_403(
        self, client: AsyncClient, viewer_client: AsyncClient
    ) -> None:
        cid = await _make_collection(client, "TagCol-8")  # admin creates the collection
        resp = await viewer_client.post(
            f"/api/v1/collections/{cid}/tags", json={"key": "x"}
        )
        assert resp.status_code == 403

    async def test_viewer_can_read(
        self, client: AsyncClient, viewer_client: AsyncClient
    ) -> None:
        cid = await _make_collection(client, "TagCol-9")
        await client.post(f"/api/v1/collections/{cid}/tags", json={"key": "readable"})
        resp = await viewer_client.get(f"/api/v1/collections/{cid}/tags")
        assert resp.status_code == 200
        assert [t["key"] for t in resp.json()] == ["readable"]
```

> Note: `client` (admin) and `viewer_client` share the same `workspace_id`/`user_id` fixtures, so a collection created by `client` is visible to `viewer_client`.

- [ ] **Step 3: Run the API tests**

Run (Docker up; up to 600000 ms): `uv run pytest tests/api/test_tags.py -v`
Expected: PASS (all classes).

- [ ] **Step 4: Run the whole tagging surface (regression)**

Run: `uv run pytest tests/unit/application/workspace_config/tagging tests/unit/domain/workspace_config tests/integration/test_tagging.py tests/integration/test_tagging_provider.py tests/api/test_tags.py -q`
Expected: PASS (domain unit + application unit + integration + API).

- [ ] **Step 5: Commit**

```bash
git add backend/tests/api/conftest.py backend/tests/api/test_tags.py
git commit -m "test(tagging): API tests for assignment + listing + auth"
```

---

## Phase 2 Done — Definition of Done

- [ ] `uv run pytest tests/unit/application/workspace_config/tagging -v` → pass.
- [ ] `uv run pytest tests/integration/test_tagging.py tests/integration/test_tagging_provider.py -v` → pass.
- [ ] `uv run pytest tests/api/test_tags.py -v` → pass.
- [ ] No regressions in the broader unit suite (`uv run pytest tests/unit -q`).

**Delivered:** Working tag API — assign/unassign/set/list/get behind `editor`-guarded mutations and workspace-scoped reads, audited via `TagAssigned`/`TagUnassigned` on the `Tag` aggregate, wired through DI and registered in both the production and test apps.

**Next (Phase 3):** the `tag` search criterion + `tags`/`tag_logic` params on the list endpoints, repoint the UI/CDD readers of `molecules.tags`, then migration 048 dropping the legacy column.
