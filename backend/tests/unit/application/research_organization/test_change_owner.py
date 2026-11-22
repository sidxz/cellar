"""Changing who owns a collection or project: an admin or the creator, to an enabled Duar org."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.change_owner import (
    ChangeCollectionOwner,
    ChangeProjectOwner,
)
from cellar.application.shared.change_owner import ChangeOwnerCommand
from cellar.domain.research_organization.collection import Collection
from cellar.domain.research_organization.events import CollectionOwnerChanged
from cellar.domain.research_organization.project import Project
from cellar.domain.shared.errors import AuthorizationError, NotFoundError, ValidationError
from tests.fakes.fake_auth import FakeAuth
from tests.unit.application.research_organization._helpers import FakeUnitOfWork

NEW_ORG = uuid.uuid4()
DISABLED_ORG = uuid.uuid4()


@dataclass(frozen=True)
class _Org:
    id: uuid.UUID
    enabled: bool = True


class _Directory:
    async def list_orgs(self) -> list[_Org]:
        return [_Org(NEW_ORG), _Org(DISABLED_ORG, enabled=False)]


def _uc(cls, entity):
    uow = FakeUnitOfWork()
    repo = AsyncMock()

    async def _find(ws, eid):
        if entity is not None and entity.id == eid:
            uow.track(entity)
            return entity
        return None

    repo.find_by_id_in_workspace = AsyncMock(side_effect=_find)
    dispatcher = AsyncMock()
    return cls(uow, repo, dispatcher, _Directory()), repo, dispatcher


def _collection(auth: FakeAuth, creator: uuid.UUID | None = None) -> Collection:
    c = Collection.create(
        workspace_id=auth.workspace_id,
        name="Leads",
        created_by=creator or auth.user_id,
        created_by_org_id=uuid.uuid4(),
    )
    c.clear_events()
    return c


def _cmd(auth: FakeAuth, entity_id: uuid.UUID, org: uuid.UUID = NEW_ORG) -> ChangeOwnerCommand:
    return ChangeOwnerCommand(
        workspace_id=auth.workspace_id, entity_id=entity_id, owner_org_id=org
    )


@pytest.mark.asyncio
async def test_creator_changes_owner() -> None:
    auth = FakeAuth(role="editor")
    coll = _collection(auth)
    uc, repo, dispatcher = _uc(ChangeCollectionOwner, coll)
    result = await uc(_cmd(auth, coll.id), auth=auth)
    assert isinstance(result, Success)
    assert result.unwrap().owner_org_id == NEW_ORG
    repo.save.assert_awaited_once()
    (events,) = dispatcher.dispatch_all.await_args.args
    assert [type(e) for e in events] == [CollectionOwnerChanged]


@pytest.mark.asyncio
async def test_admin_changes_owner() -> None:
    auth = FakeAuth(role="admin")
    coll = _collection(auth, creator=uuid.uuid4())
    uc, _, _ = _uc(ChangeCollectionOwner, coll)
    assert isinstance(await uc(_cmd(auth, coll.id), auth=auth), Success)


@pytest.mark.asyncio
async def test_other_editor_refused() -> None:
    auth = FakeAuth(role="editor")
    coll = _collection(auth, creator=uuid.uuid4())
    uc, repo, _ = _uc(ChangeCollectionOwner, coll)
    with pytest.raises(AuthorizationError):
        await uc(_cmd(auth, coll.id), auth=auth)
    repo.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_org_refused() -> None:
    auth = FakeAuth(role="editor")
    coll = _collection(auth)
    uc, repo, _ = _uc(ChangeCollectionOwner, coll)
    result = await uc(_cmd(auth, coll.id, DISABLED_ORG), auth=auth)
    assert isinstance(result, Failure) and isinstance(result.failure(), ValidationError)
    repo.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_collection_not_found() -> None:
    auth = FakeAuth(role="editor")
    uc, _, _ = _uc(ChangeCollectionOwner, None)
    result = await uc(_cmd(auth, uuid.uuid4()), auth=auth)
    assert isinstance(result, Failure) and isinstance(result.failure(), NotFoundError)


@pytest.mark.asyncio
async def test_archived_project_is_a_validation_failure() -> None:
    auth = FakeAuth(role="editor")
    project = Project.create(workspace_id=auth.workspace_id, name="TB", created_by=auth.user_id)
    project.archive(archived_by=auth.user_id)
    project.clear_events()
    uc, _, _ = _uc(ChangeProjectOwner, project)
    result = await uc(_cmd(auth, project.id), auth=auth)
    assert isinstance(result, Failure) and isinstance(result.failure(), ValidationError)
