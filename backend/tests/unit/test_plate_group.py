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


class TestMetadataFields:
    def test_create_with_all_metadata(self) -> None:
        loc = uuid.uuid4()
        g = _group(
            state=" Solubilized ",
            storage_location_id=loc,
            initial_volume_ul=55.0,
            initial_concentration_mm=10.0,
            compound_count=17606,
            scientist="  Jane Doe ",
        )
        assert g.state == "Solubilized"
        assert g.storage_location_id == loc
        assert g.initial_volume_ul == 55.0
        assert g.initial_concentration_mm == 10.0
        assert g.compound_count == 17606
        assert g.scientist == "Jane Doe"

    def test_metadata_defaults_to_none(self) -> None:
        g = _group()
        assert g.state is None
        assert g.storage_location_id is None
        assert g.initial_volume_ul is None
        assert g.initial_concentration_mm is None
        assert g.compound_count is None
        assert g.scientist is None

    def test_blank_state_and_scientist_normalize_to_none(self) -> None:
        g = _group(state="   ", scientist="")
        assert g.state is None
        assert g.scientist is None

    @pytest.mark.parametrize(
        "field, value",
        [
            ("initial_volume_ul", -0.5),
            ("initial_concentration_mm", -1.0),
            ("compound_count", -1),
        ],
    )
    def test_negative_measurements_rejected(self, field: str, value: float) -> None:
        with pytest.raises(ValidationError):
            _group(**{field: value})

    def test_state_and_scientist_length_limits(self) -> None:
        with pytest.raises(ValidationError):
            _group(state="x" * 51)
        with pytest.raises(ValidationError):
            _group(scientist="x" * 201)

    def test_update_sentinel_leaves_untouched_and_none_clears(self) -> None:
        g = _group(state="Dry", scientist="Jane Doe", compound_count=3)
        g.update(state="Retired")
        assert g.state == "Retired"
        assert g.scientist == "Jane Doe"  # untouched (sentinel)
        assert g.compound_count == 3
        g.update(scientist=None, compound_count=None)
        assert g.scientist is None
        assert g.compound_count is None
        assert g.state == "Retired"
        events = g.collect_events()
        assert isinstance(events[-1], PlateGroupUpdated)
