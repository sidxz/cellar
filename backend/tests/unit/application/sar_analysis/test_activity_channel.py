from __future__ import annotations

import uuid

from cellar.application.sar_analysis.activity_channel import (
    ActivityChannelSpec,
    activity_value_snapshot,
    channel_hash,
    pick_scalar,
)
from cellar.domain.screening_assay.activity_types import ActivityValue, RunSummary
from cellar.domain.shared.aggregation_types import QualifierHandling, SelectionRule
from cellar.domain.shared.hit_criterion import InterceptKey


def _spec(**over) -> ActivityChannelSpec:
    base = dict(
        column="drc:" + str(uuid.uuid4()),
        source="dr_curve",
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.EXCLUDE_QUALIFIED,
        intercept_key=None,
        run_scopes=None,
        protocol_id=None,
        label="EGFR · IC50",
    )
    base.update(over)
    return ActivityChannelSpec(**base)


def test_pick_scalar_primary_returns_value_when_no_intercept_key():
    av = ActivityValue(value=0.5, qualifier=None, unit="uM", source="dose_response")
    assert pick_scalar(av, None) == 0.5


def test_pick_scalar_intercept_matches_by_kind_and_level():
    av = ActivityValue(
        value=0.5,
        qualifier=None,
        unit="uM",
        source="dose_response",
        intercept_values=[
            {"spec": {"kind": "ic", "level": 50.0}, "value": 0.5},
            {"spec": {"kind": "ic", "level": 90.0}, "value": 3.2},
        ],
    )
    assert pick_scalar(av, InterceptKey(kind="ic", level=90.0)) == 3.2


def test_pick_scalar_intercept_miss_returns_none():
    av = ActivityValue(
        value=0.5, qualifier=None, unit="uM", source="dose_response",
        intercept_values=[{"spec": {"kind": "ic", "level": 50.0}, "value": 0.5}],
    )
    assert pick_scalar(av, InterceptKey(kind="ec", level=50.0)) is None


def test_pick_scalar_primary_none_value():
    av = ActivityValue(value=None, qualifier="nd", unit="uM", source="dose_response")
    assert pick_scalar(av, None) is None


def test_channel_hash_ignores_label():
    a = _spec(label="EGFR · IC50")
    b = _spec(column=a.column, label="totally different label")
    assert channel_hash(a) == channel_hash(b)


def test_channel_hash_changes_on_intercept_key():
    a = _spec(intercept_key=None)
    b = _spec(column=a.column, intercept_key=InterceptKey(kind="ic", level=90.0))
    assert channel_hash(a) != channel_hash(b)


def test_channel_hash_changes_on_selection_rule():
    a = _spec(selection_rule=SelectionRule.LATEST_APPROVED_RUN)
    b = _spec(column=a.column, selection_rule=SelectionRule.GEOMETRIC_MEAN)
    assert channel_hash(a) != channel_hash(b)


def test_to_spec_dict_round_trips():
    a = _spec(intercept_key=InterceptKey(kind="ec", level=50.0), run_scopes={"drc:x": {"mode": "latest"}})
    d = a.to_spec_dict()
    back = ActivityChannelSpec.from_spec_dict(d)
    assert back.column == a.column
    assert back.intercept_key == a.intercept_key
    assert back.selection_rule == a.selection_rule
    assert back.run_scopes == a.run_scopes
    assert channel_hash(back) == channel_hash(a)


def test_resolved_run_scopes_parses_wire_to_runscope():
    a = _spec(run_scopes={"drc:x": {"mode": "latest"}})
    rs = a.resolved_run_scopes()
    assert rs is not None
    assert rs["drc:x"].last_n_count == 1


def test_snapshot_is_json_safe_even_with_uuid_and_date_fields():
    import datetime
    import json

    av = ActivityValue(
        value=0.5, qualifier=None, unit="uM", source="dose_response",
        runs=[RunSummary(
            run_id=uuid.uuid4(),
            run_date=datetime.date(2026, 6, 1),
            curve_id=uuid.uuid4(),
            curve_class="active",
            r_squared=0.99,
            intercept_values=[],
        )],
    )
    snap = activity_value_snapshot(av)
    # Round-trips through JSON without raising (UUID -> str, date -> isoformat).
    assert json.dumps(snap)
    assert snap["value"] == 0.5
    assert isinstance(snap["runs"][0]["run_id"], str)
    assert snap["runs"][0]["run_date"] == "2026-06-01"
