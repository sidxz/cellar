"""Unit tests for AssignTag and UnassignTag use cases."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

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
        provider = make_link_provider()
        uc = UnassignTag(FakeUnitOfWork(), repo, provider, AsyncMock())

        cmd = UnassignTagCommand(
            workspace_id=auth.workspace_id,
            entity_type=TaggableEntityType.MOLECULE,
            entity_id=uuid.uuid4(),
            tag_id=uuid.uuid4(),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        provider.link_repo.remove.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_viewer_denied(self) -> None:
        auth = fake_auth(role="viewer")
        tag = make_tag(auth.workspace_id, "env", "prod", auth.user_id)
        uc = UnassignTag(
            FakeUnitOfWork(),
            make_tag_repo(get_or_create=tag, find_by_id=tag),
            make_link_provider(),
            AsyncMock(),
        )
        cmd = UnassignTagCommand(
            workspace_id=auth.workspace_id,
            entity_type=TaggableEntityType.MOLECULE,
            entity_id=uuid.uuid4(),
            tag_id=tag.id,
        )
        with pytest.raises(AuthorizationError):
            await uc(cmd, auth=auth)
