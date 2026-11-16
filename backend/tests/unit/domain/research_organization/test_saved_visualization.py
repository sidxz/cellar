"""Tests for the SavedVisualization aggregate and its config envelope."""

import uuid

import pytest

from cellar.domain.research_organization.enums import SearchVisibility
from cellar.domain.research_organization.events import (
    SavedVisualizationCreated,
    SavedVisualizationDeleted,
    SavedVisualizationUpdated,
)
from cellar.domain.research_organization.saved_visualization import (
    SavedVisualization,
    validate_view_config,
)
from cellar.domain.shared.errors import StaleEditError, ValidationError

WS = uuid.uuid4()
OWNER = uuid.uuid4()
PROTOCOL = uuid.uuid4()


def _panel(n: int = 1, **extra: object) -> dict:
    return {"id": f"panel-{n}", "type": "scatter", "x": "well_order", **extra}


def _config(**overrides: object) -> dict:
    return {
        "config_version": 1,
        "panels": [_panel()],
        "filters": [
            {"id": "f1", "kind": "range", "key": "rd:X:raw", "min": 0, "max": 50},
            {"id": "f2", "kind": "category", "key": "well_type", "values": ["sample"]},
        ],
        "labels": {"rd:X:raw": "Signal"},
        **overrides,
    }


def _view(**overrides: object) -> SavedVisualization:
    kwargs: dict = {
        "workspace_id": WS,
        "name": "Old",
        "source": {"kind": "protocol", "protocol_id": str(PROTOCOL), "run_ids": None},
        "protocol_ids": [PROTOCOL],
        "level": "wells",
        "config": _config(),
        "created_by": OWNER,
        **overrides,
    }
    return SavedVisualization.create(**kwargs)


class TestCreate:
    def test_strips_name_and_registers_one_created_event(self) -> None:
        view = _view(name="  Plate QC  ")
        assert view.name == "Plate QC"
        assert view.protocol_ids == (PROTOCOL,)
        events = view.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], SavedVisualizationCreated)
        assert events[0].name == "Plate QC"
        assert events[0].visibility == "private"
        assert events[0].aggregate_type == "SavedVisualization"

    def test_blank_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _view(name="  ")

    def test_long_name_and_description_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _view(name="x" * 256)
        with pytest.raises(ValidationError):
            _view(description="x" * 2001)

    def test_project_visibility_needs_project(self) -> None:
        with pytest.raises(ValidationError):
            _view(visibility=SearchVisibility.PROJECT)


class TestConfig:
    def test_unknown_panel_keys_survive_round_trip(self) -> None:
        cfg = _config(panels=[_panel(logX=True, overlay={"kind": "band", "sd": 3})])
        assert validate_view_config(cfg) == cfg

    def test_more_than_four_panels_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_view_config(_config(panels=[_panel(n) for n in range(5)]))

    def test_rows_filter_rejected(self) -> None:
        cfg = _config(filters=[{"id": "f", "kind": "rows", "rowIds": ["r1"]}])
        with pytest.raises(ValidationError, match="Selections"):
            validate_view_config(cfg)

    def test_newer_version_rejected(self) -> None:
        with pytest.raises(ValidationError, match="newer version"):
            validate_view_config(_config(config_version=2))

    def test_unknown_top_level_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_view_config(_config(selection=["r1"]))

    def test_oversized_config_rejected_naming_the_limit(self) -> None:
        values = [f"compound-{i:05d}" for i in range(5000)]  # ~85 KB compact
        cfg = _config(
            filters=[{"id": "f", "kind": "category", "key": "compound", "values": values}]
        )
        with pytest.raises(ValidationError, match="64 KB") as exc:
            validate_view_config(cfg)
        assert "too large to save" in exc.value.message


class TestUpdate:
    def test_stale_version_raises_and_changes_nothing(self) -> None:
        view = _view()
        view.version = 2
        view.clear_events()
        with pytest.raises(StaleEditError):
            view.update(expected_version=1, name="New")
        assert view.name == "Old"
        assert view.collect_events() == []

    def test_rename_records_old_and_new(self) -> None:
        view = _view()
        view.clear_events()
        view.update(expected_version=1, name="New")
        [event] = view.collect_events()
        assert isinstance(event, SavedVisualizationUpdated)
        assert event.audit_changes() == [("name", "Old", "New")]

    def test_config_and_source_changes_are_named_without_values(self) -> None:
        view = _view()
        view.clear_events()
        other = uuid.uuid4()
        view.update(
            expected_version=1,
            source={"kind": "run", "run_id": str(uuid.uuid4())},
            protocol_ids=[other],
            config=_config(panels=[]),
        )
        [event] = view.collect_events()
        assert event.audit_changes() == [("source", None, None), ("config", None, None)]
        assert view.protocol_ids == (other,)

    def test_unchanged_update_registers_nothing(self) -> None:
        view = _view()
        view.clear_events()
        view.update(expected_version=1, name="Old", level="wells", config=_config())
        assert view.collect_events() == []

    def test_invalid_update_changes_nothing(self) -> None:
        view = _view()
        with pytest.raises(ValidationError):
            view.update(expected_version=1, name="New", visibility=SearchVisibility.PROJECT)
        assert view.name == "Old"


class TestPermissions:
    def test_only_owner_or_admin_edits(self) -> None:
        view = _view()
        assert view.can_be_edited_by(OWNER, is_admin=False)
        assert not view.can_be_edited_by(uuid.uuid4(), is_admin=False)
        assert view.can_be_edited_by(uuid.uuid4(), is_admin=True)

    def test_visibility(self) -> None:
        private = _view()
        assert private.is_visible_to(OWNER, is_admin=False, is_member=False)
        assert not private.is_visible_to(uuid.uuid4(), is_admin=True, is_member=True)
        shared = _view(visibility=SearchVisibility.PROJECT, project_id=uuid.uuid4())
        other = uuid.uuid4()
        assert shared.is_visible_to(other, is_admin=False, is_member=True)
        assert not shared.is_visible_to(other, is_admin=False, is_member=False)
        assert shared.is_visible_to(other, is_admin=True, is_member=False)


def test_mark_deleted_registers_deleted_with_name() -> None:
    view = _view()
    view.clear_events()
    view.mark_deleted()
    [event] = view.collect_events()
    assert isinstance(event, SavedVisualizationDeleted)
    assert event.name == "Old"
