"""Tests for the Tag aggregate."""

import uuid
from datetime import UTC, datetime

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

    def test_rename_bumps_updated_at(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        past = datetime(2020, 1, 1, tzinfo=UTC)
        tag = Tag(
            workspace_id=ws_id,
            name=TagName(key="old"),
            created_by=user_id,
            updated_at=past,
        )
        tag.rename(TagName(key="new"))
        assert tag.updated_at > past

    def test_rename_to_same_name_is_noop(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        tag = Tag.create(
            workspace_id=ws_id, name=TagName(key="x", value="y"), created_by=user_id
        )
        tag.clear_events()
        tag.rename(TagName(key="x", value="y"))
        assert tag.collect_events() == []
