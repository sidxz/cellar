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
