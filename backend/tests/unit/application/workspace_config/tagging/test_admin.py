"""Unit tests for admin tag use cases (rename / delete)."""

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
        repo = _tag_repo(find_by_id=tag, find_by_normalized=other)
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
        auth = fake_auth(role="editor")
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
