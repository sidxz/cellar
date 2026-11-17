"""Tests for the SavedVisualization aggregate and its config envelope."""

import re
import uuid
from pathlib import Path
from typing import get_args

import pytest

from cellar.domain.research_organization.enums import SearchVisibility
from cellar.domain.research_organization.events import (
    SavedVisualizationCreated,
    SavedVisualizationDeleted,
    SavedVisualizationUpdated,
)
from cellar.domain.research_organization.saved_visualization import (
    VIEW_CONFIG_VERSION,
    SavedVisualization,
    ViewPanel,
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

    def test_a_private_view_keeps_no_project(self) -> None:
        assert _view(project_id=uuid.uuid4()).project_id is None
        project = uuid.uuid4()
        shared = _view(visibility=SearchVisibility.PROJECT, project_id=project)
        shared.clear_events()
        shared.update(expected_version=1, visibility=SearchVisibility.PRIVATE)
        assert shared.project_id is None
        [event] = shared.collect_events()
        assert ("project_id", str(project), None) in event.audit_changes()


# The workbench's own definition of a plot's settings.
FRONTEND_CONFIG_SCHEMA = (
    Path(__file__).resolve().parents[5]
    / "frontend/src/features/visualization/lib/config-schema.ts"
)
SUBSTRUCTURE = {"id": "sub-1", "kind": "substructure", "query": "c1ccccc1", "queryKind": "smiles"}
RGROUPS = {"id": "rg1", "kind": "rgroups", "coreSmiles": "c1ccccc1[*:1]", "name": "Core A"}
CLUSTERS = {"id": "clusters", "kind": "clusters", "threshold": 0.4}


def _series(*members: dict) -> dict:
    return {"id": "series", "kind": "series", "members": list(members)}


class TestConfig:
    def test_unknown_panel_keys_survive_round_trip(self) -> None:
        overlays = {"bands": True, "limits": {"mode": "entered", "lower": 10, "upper": 90}}
        cfg = _config(panels=[_panel(logX=True, overlays=overlays)])
        assert validate_view_config(cfg) == cfg

    def test_panel_types_are_the_workbenchs(self) -> None:
        text = FRONTEND_CONFIG_SCHEMA.read_text()
        panel_schema = text[text.index("export const panelSchema") :]
        enum = re.search(r"type: z\.enum\(\[([^\]]*)\]\)", panel_schema)
        assert enum is not None, "panelSchema's type enum not found"
        workbench = set(re.findall(r'"([^"]+)"', enum.group(1)))
        assert workbench == set(get_args(ViewPanel.model_fields["type"].annotation))

    def test_rgroup_matrix_panel_accepted(self) -> None:
        cfg = _config(panels=[_panel(type="rgroup-matrix", category="chem:rg1:R1")])
        assert validate_view_config(cfg) == cfg

    def test_substructure_filter_saved_as_its_query(self) -> None:
        cfg = _config(filters=[SUBSTRUCTURE])
        assert validate_view_config(cfg) == cfg

    def test_substructure_matches_never_saved(self) -> None:
        cfg = _config(filters=[SUBSTRUCTURE | {"moleculeIds": ["m1"]}])
        with pytest.raises(ValidationError, match="moleculeIds"):
            validate_view_config(cfg)

    def test_substructure_filter_needs_a_query(self) -> None:
        with pytest.raises(ValidationError, match="query"):
            validate_view_config(_config(filters=[SUBSTRUCTURE | {"query": ""}]))

    def test_more_than_four_panels_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_view_config(_config(panels=[_panel(n) for n in range(5)]))

    def test_rows_filter_rejected(self) -> None:
        cfg = _config(filters=[{"id": "f", "kind": "rows", "rowIds": ["r1"]}])
        with pytest.raises(ValidationError, match="Selections"):
            validate_view_config(cfg)

    def test_newer_version_rejected(self) -> None:
        with pytest.raises(ValidationError, match="newer version"):
            validate_view_config(_config(config_version=VIEW_CONFIG_VERSION + 1))

    def test_derived_column_specs_saved(self) -> None:
        series = _series(
            {"name": "Series A", "rgroupsId": "rg1"}, {"name": "B", "scaffold": "c1ccncc1"}
        )
        cfg = _config(config_version=2, derived=[RGROUPS, CLUSTERS, series])
        assert validate_view_config(cfg) == cfg

    def test_nine_series_members_rejected(self) -> None:
        members = [{"name": f"S{n}", "scaffold": "c1ccccc1"} for n in range(9)]
        with pytest.raises(ValidationError, match="members"):
            validate_view_config(_config(config_version=2, derived=[_series(*members)]))

    def test_unknown_derived_kind_rejected(self) -> None:
        with pytest.raises(ValidationError, match="derived"):
            validate_view_config(_config(config_version=2, derived=[{"id": "x", "kind": "pca"}]))

    @pytest.mark.parametrize(
        "member",
        [{"name": "A"}, {"name": "A", "scaffold": "c1ccccc1", "rgroupsId": "rg1"}],
        ids=["neither", "both"],
    )
    def test_series_member_has_exactly_one_source(self, member: dict) -> None:
        with pytest.raises(ValidationError, match="scaffold"):
            validate_view_config(_config(config_version=2, derived=[_series(member)]))

    @pytest.mark.parametrize(
        "spec",
        [
            RGROUPS | {"coreSmiles": "C" * 2001},
            CLUSTERS | {"threshold": 0.01},
            CLUSTERS | {"threshold": 0.96},
            _series({"name": "x" * 61, "scaffold": "c1ccccc1"}),
            RGROUPS | {"moleculeIds": ["m1"]},
        ],
        ids=["long-core", "threshold-low", "threshold-high", "long-name", "data"],
    )
    def test_out_of_bounds_derived_spec_rejected(self, spec: dict) -> None:
        with pytest.raises(ValidationError, match="derived"):
            validate_view_config(_config(config_version=2, derived=[spec]))

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


def test_creation_and_deletion_are_audited_with_name_visibility_and_project() -> None:
    project = uuid.uuid4()
    private = _view()
    shared = _view(visibility=SearchVisibility.PROJECT, project_id=project)
    shared.clear_events()
    shared.mark_deleted()

    [created] = private.collect_events()
    [deleted] = shared.collect_events()

    assert created.audit_changes() == [("name", None, "Old"), ("visibility", None, "private")]
    assert deleted.audit_changes() == [
        ("name", "Old", None),
        ("visibility", "project", None),
        ("project_id", str(project), None),
    ]
