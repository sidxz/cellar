"""Unit tests for the PlateGroup aggregate."""

from __future__ import annotations

import uuid

import pytest

from cellar.domain.inventory.events import (
    PlateGroupCreated,
    PlateGroupMoved,
    PlateGroupUpdated,
)
from cellar.domain.inventory.plate_group import PlateGroup
from cellar.domain.shared.errors import ValidationError

WS = uuid.uuid4()
ORG = uuid.uuid4()
USER = uuid.uuid4()


def _group(**overrides) -> PlateGroup:
    kwargs = dict(
        workspace_id=WS,
        owner_org_id=ORG,
        name="Vendor Library A",
        created_by=USER,
    )
    kwargs.update(overrides)
    return PlateGroup.create(**kwargs)


class TestCreate:
    def test_create_emits_event_and_strips_name(self) -> None:
        g = _group(name="  Vendor Library A  ")
        assert g.name == "Vendor Library A"
        assert g.workspace_id == WS
        assert g.owner_org_id == ORG
        assert g.parent_group_id is None
        assert g.group_type is None
        assert g.version == 1
        events = g.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], PlateGroupCreated)
        assert events[0].name == "Vendor Library A"
        assert events[0].owner_org_id == ORG

    def test_create_with_parent_and_type(self) -> None:
        parent_id = uuid.uuid4()
        g = _group(parent_group_id=parent_id, group_type="vendor", description="desc")
        assert g.parent_group_id == parent_id
        assert g.group_type == "vendor"
        assert g.description == "desc"

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _group(name="   ")

    def test_overlong_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _group(name="x" * 301)

    def test_overlong_group_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _group(group_type="x" * 101)


class TestUpdate:
    def test_update_fields_and_event(self) -> None:
        g = _group()
        g.clear_events()
        g.update(name="Renamed", group_type="screening", description=None)
        assert g.name == "Renamed"
        assert g.group_type == "screening"
        assert g.description is None
        events = g.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], PlateGroupUpdated)

    def test_update_untouched_fields_keep_values(self) -> None:
        g = _group(group_type="vendor", description="keep me")
        g.clear_events()
        g.update(name="Renamed")
        assert g.group_type == "vendor"
        assert g.description == "keep me"

    def test_update_empty_name_rejected(self) -> None:
        g = _group()
        with pytest.raises(ValidationError):
            g.update(name="  ")


class TestMove:
    def test_move_to_new_parent_emits_event(self) -> None:
        g = _group()
        g.clear_events()
        new_parent = uuid.uuid4()
        g.move_to(new_parent)
        assert g.parent_group_id == new_parent
        events = g.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], PlateGroupMoved)
        assert events[0].old_parent_group_id is None
        assert events[0].new_parent_group_id == new_parent

    def test_move_to_root(self) -> None:
        g = _group(parent_group_id=uuid.uuid4())
        g.clear_events()
        g.move_to(None)
        assert g.parent_group_id is None

    def test_move_to_self_rejected(self) -> None:
        g = _group()
        with pytest.raises(ValidationError):
            g.move_to(g.id)
