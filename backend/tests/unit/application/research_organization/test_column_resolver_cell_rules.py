"""ColumnResolver's cell rules on dose-response columns: selection, QC, intercepts,
the snapshot and source pin of each cell, and the D1 reported-endpoint fallback.

Each cell is resolved from what the column query returns for one molecule: its
curves plus its well-less endpoints (``_resolve``).
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import date

import pytest

from cellar.application.research_organization.column_resolution import (
    Candidate,
    ColumnResolver,
)
from cellar.application.screening.curve_snapshot import build_aggregate_curve_snapshot
from cellar.application.screening.run_aggregation import (
    ResolvedRun,
    _dose_range_from_raw,
    resolve_intercept,
)
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import CampaignMeasurement
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from cellar.domain.shared.hit_criterion import HitCriterion, InterceptKey


def _resolve(
    channel: CampaignChannel,
    curves: list[ResolvedRun],
    endpoints: list[ResolvedRun] = (),  # type: ignore[assignment]
) -> CampaignMeasurement:
    """One cell: ``curves`` and well-less ``endpoints`` as the column query returns them."""
    mol, result_id = uuid.uuid4(), uuid.uuid4()
    candidates = [
        Candidate(
            run=r, molecule_id=mol, batch_id=None, well_id=None, dose=None, replicate_count=None
        )
        for r in [*curves, *endpoints]
    ]
    return ColumnResolver().resolve_column(
        channel=channel,
        molecule_ids=[mol],
        candidates={mol: candidates},
        result_id_by_molecule={mol: result_id},
    )[mol]


def _channel(
    rule: SelectionRule,
    *,
    qc: dict | None = None,
    qualifier_handling: QualifierHandling | None = None,
    intercept_key: InterceptKey | None = None,
    source_kind: ChannelSourceKind = ChannelSourceKind.DOSE_RESPONSE_CURVE,
) -> CampaignChannel:
    return CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="L",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=source_kind,
        selection_rule=rule,
        qualifier_handling=qualifier_handling or QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
        qc_filter=qc,
        intercept_key=intercept_key,
    )


def _candidate(
    value: float,
    run_date: date | None = None,
    *,
    qualifier: ValueQualifier = ValueQualifier.EQ,
    approved: bool = True,
    intercept_values: list[dict] | None = None,
) -> ResolvedRun:
    return ResolvedRun(
        value=value,
        qualifier=qualifier,
        unit="nM",
        run_id=uuid.uuid4(),
        run_date=run_date,
        run_approved=approved,
        protocol_name="X",
        protocol_version=1,
        curve_id=uuid.uuid4(),
        readout_id=None,
        intercept_values=intercept_values,
    )


def _iv(kind: str, level: float, value: float) -> dict:
    """JSONB-shaped intercept_values row, mirroring the persisted shape."""
    return {"spec": {"kind": kind, "level": level}, "value": value}


def test_latest_run_picks_highest_run_date():
    ch = _channel(SelectionRule.LATEST_RUN)
    candidates = [
        _candidate(10.0, run_date=date(2026, 5, 1)),
        _candidate(20.0, run_date=date(2026, 4, 1)),
    ]
    m = _resolve(ch, candidates)
    assert m.value == 10.0  # the May date


def test_mean_across_runs_averages():
    ch = _channel(SelectionRule.MEAN_ACROSS_RUNS)
    candidates = [_candidate(10.0), _candidate(20.0)]
    m = _resolve(ch, candidates)
    assert m.value == 15.0


def test_geometric_mean_logspace():
    ch = _channel(SelectionRule.GEOMETRIC_MEAN)
    candidates = [_candidate(10.0), _candidate(1000.0)]
    m = _resolve(ch, candidates)
    assert m.value == pytest.approx(100.0)  # sqrt(10 * 1000)


def test_no_candidates_yields_nd():
    ch = _channel(SelectionRule.LATEST_RUN)
    m = _resolve(ch, [])
    assert m.value is None
    assert m.value_qualifier == ValueQualifier.ND
    # Nothing was resolved, so the cell carries no provenance and the funnel
    # keeps reading it as untested rather than as a miss.
    assert not m.is_tested_nd


def test_old_columns_stored_min_z_prime_is_ignored():
    """A column saved before min-Z' was removed still says min_z_prime: runs
    are not dropped for it."""
    ch = _channel(SelectionRule.LATEST_RUN, qc={"min_z_prime": 0.5})
    candidates = [_candidate(99.0, run_date=date(2026, 5, 1))]
    assert _resolve(ch, candidates).value == 99.0


def test_require_approved_still_drops_unapproved_run():
    ch = _channel(SelectionRule.LATEST_RUN, qc={"min_z_prime": 0.5, "require_approved": True})
    candidates = [_candidate(99.0, run_date=date(2026, 5, 1), approved=False)]
    assert _resolve(ch, candidates).value_qualifier == ValueQualifier.ND


def test_intercept_key_resolves_secondary_intercept_value():
    """A channel that surfaces EC90 yields EC90's value as the cell value,
    not the curve's primary (EC50) value."""
    ch = _channel(
        SelectionRule.LATEST_RUN,
        intercept_key=InterceptKey(kind="ec", level=90.0),
    )
    candidates = [
        _candidate(
            2.0,
            run_date=date(2026, 5, 1),
            intercept_values=[_iv("ec", 50.0, 2.0), _iv("ec", 90.0, 80.0)],
        )
    ]
    m = _resolve(ch, candidates)
    assert m.value == 80.0  # the channel IS for EC90 — its value IS EC90


def test_intercept_key_none_keeps_legacy_primary_behavior():
    """No channel-level intercept_key → cell value is the primary fitted value."""
    ch = _channel(SelectionRule.LATEST_RUN)
    candidates = [
        _candidate(
            2.0,
            run_date=date(2026, 5, 1),
            intercept_values=[_iv("ec", 50.0, 2.0), _iv("ec", 90.0, 80.0)],
        )
    ]
    m = _resolve(ch, candidates)
    assert m.value == 2.0


def test_intercept_key_missing_match_yields_no_value():
    """Channel targets EC90 but the curve only has EC50 → cell value None."""
    ch = _channel(
        SelectionRule.LATEST_RUN,
        intercept_key=InterceptKey(kind="ec", level=90.0),
    )
    candidates = [
        _candidate(
            2.0,
            run_date=date(2026, 5, 1),
            intercept_values=[_iv("ec", 50.0, 2.0)],  # no EC90 row
        )
    ]
    m = _resolve(ch, candidates)
    assert m.value is None


def test_intercept_key_aggregates_under_mean_selection():
    """MEAN_ACROSS_RUNS on a channel keyed to EC90 averages the EC90 values."""
    ch = _channel(
        SelectionRule.MEAN_ACROSS_RUNS,
        intercept_key=InterceptKey(kind="ec", level=90.0),
    )
    # EC90 values 80 and 100 average to 90.
    candidates = [
        _candidate(2.0, intercept_values=[_iv("ec", 50.0, 2.0), _iv("ec", 90.0, 80.0)]),
        _candidate(4.0, intercept_values=[_iv("ec", 50.0, 4.0), _iv("ec", 90.0, 100.0)]),
    ]
    m = _resolve(ch, candidates)
    assert m.value == 90.0  # mean of the EC90 values


def test_qualifier_handling_excludes_qualified():
    ch = _channel(
        SelectionRule.MEAN_ACROSS_RUNS,
        qualifier_handling=QualifierHandling.EXCLUDE_QUALIFIED,
    )
    candidates = [
        _candidate(10.0, qualifier=ValueQualifier.EQ),
        _candidate(99.0, qualifier=ValueQualifier.GT),  # excluded
    ]
    m = _resolve(ch, candidates)
    assert m.value == 10.0  # GT 99.0 was excluded before averaging


# ---------------------------------------------------------------------------
# DR display honesty — Inactive curves emit ND, at_bound emits "> max_dose"
# ---------------------------------------------------------------------------


def _dr_candidate(
    value: float,
    *,
    run_date: date | None = None,
    curve_class: str | None = "full",
    intercept_values: list[dict] | None = None,
    raw_data: list[dict] | None = None,
) -> ResolvedRun:
    """ResolvedRun with the curve-shape fields the new resolver reads."""
    return ResolvedRun(
        value=value,
        qualifier=ValueQualifier.EQ,
        unit="uM",
        run_id=uuid.uuid4(),
        run_date=run_date,
        run_approved=True,
        protocol_name="X",
        protocol_version=1,
        curve_id=uuid.uuid4(),
        readout_id=None,
        curve_class=curve_class,
        curve_top=100.0,
        curve_bottom=0.0,
        curve_hill_slope=-1.0,
        curve_r_squared=0.9,
        curve_raw_data=raw_data,
        intercept_values=intercept_values,
    )


def _top_dose(raw_data):
    return _dose_range_from_raw(raw_data)[1]


class TestDoseRangeFromRaw:
    def test_picks_largest_positive_concentration(self):
        assert (
            _top_dose(
                [
                    {"concentration": 0.1, "response": 5},
                    {"concentration": 50.0, "response": 90},
                    {"concentration": 1.0, "response": 40},
                ]
            )
            == 50.0
        )

    def test_accepts_x_y_shape_too(self):
        assert _top_dose([{"x": 0.5, "y": 10}, {"x": 25, "y": 80}]) == 25.0

    def test_ignores_non_positive_and_non_finite(self):
        import math as _math

        assert (
            _top_dose(
                [
                    {"concentration": -1, "response": 5},
                    {"concentration": 0, "response": 5},
                    {"concentration": _math.nan, "response": 5},
                    {"concentration": 7, "response": 5},
                ]
            )
            == 7.0
        )

    def test_returns_none_on_empty(self):
        assert _top_dose(None) is None
        assert _top_dose([]) is None


class TestResolveIntercept:
    def test_inactive_class_yields_nd_regardless_of_value(self):
        c = _dr_candidate(0.013, curve_class="inactive")
        value, qualifier = resolve_intercept(c, None)
        assert value is None
        assert qualifier == ValueQualifier.ND

    def test_inactive_class_yields_nd_even_with_keyed_intercept(self):
        c = _dr_candidate(
            0.013,
            curve_class="inactive",
            intercept_values=[_iv("ec", 90, 0.005)],
        )
        value, qualifier = resolve_intercept(c, InterceptKey(kind="ec", level=90.0))
        assert value is None
        assert qualifier == ValueQualifier.ND

    def test_keyed_intercept_at_bound_with_max_dose(self):
        c = _dr_candidate(
            5.0,
            curve_class="partial",
            intercept_values=[
                {"spec": {"kind": "ec", "level": 50}, "value": 5.0, "at_bound": False},
                {"spec": {"kind": "ec", "level": 90}, "value": 1e-9, "at_bound": True},
            ],
            raw_data=[
                {"concentration": 0.1, "response": 10},
                {"concentration": 50.0, "response": 35},
            ],
        )
        value, qualifier = resolve_intercept(c, InterceptKey(kind="ec", level=90.0))
        assert value == 50.0  # >max_dose
        assert qualifier == ValueQualifier.GT

    def test_keyed_intercept_at_bound_with_no_raw_data_yields_nd(self):
        c = _dr_candidate(
            5.0,
            curve_class="partial",
            intercept_values=[
                {"spec": {"kind": "ec", "level": 90}, "value": 1e-9, "at_bound": True},
            ],
            raw_data=None,
        )
        value, qualifier = resolve_intercept(c, InterceptKey(kind="ec", level=90.0))
        assert value is None
        assert qualifier == ValueQualifier.ND

    def test_keyed_intercept_healthy_returns_value_eq(self):
        c = _dr_candidate(
            5.0,
            curve_class="full",
            intercept_values=[
                {"spec": {"kind": "ec", "level": 50}, "value": 5.0, "at_bound": False},
            ],
        )
        value, qualifier = resolve_intercept(c, InterceptKey(kind="ec", level=50.0))
        assert value == 5.0
        assert qualifier == ValueQualifier.EQ

    def test_keyed_intercept_missing_match_yields_nd(self):
        c = _dr_candidate(
            5.0,
            curve_class="full",
            intercept_values=[
                {"spec": {"kind": "ec", "level": 50}, "value": 5.0, "at_bound": False},
            ],
        )
        # Legacy curve without an EC90 intercept; protocol added it later.
        value, qualifier = resolve_intercept(c, InterceptKey(kind="ec", level=90.0))
        assert value is None
        assert qualifier == ValueQualifier.ND

    def test_primary_intercept_at_bound_uses_intercept_values_zero(self):
        c = _dr_candidate(
            1e-9,
            curve_class="partial",
            intercept_values=[
                {"spec": {"kind": "ec", "level": 50}, "value": 1e-9, "at_bound": True},
            ],
            raw_data=[{"concentration": 100.0, "response": 30}],
        )
        value, qualifier = resolve_intercept(c, None)
        assert value == 100.0
        assert qualifier == ValueQualifier.GT

    def test_primary_legacy_no_intercept_values_returns_c_value(self):
        # Pre-033 curves that never had intercept_values persisted.
        c = _dr_candidate(7.5, curve_class="full", intercept_values=None)
        value, qualifier = resolve_intercept(c, None)
        assert value == 7.5
        assert qualifier == ValueQualifier.EQ


def test_latest_run_inactive_pick_emits_nd():
    ch = _channel(SelectionRule.LATEST_RUN)
    candidates = [
        _dr_candidate(
            0.013,
            run_date=date(2026, 5, 1),
            curve_class="inactive",
            intercept_values=[{"spec": {"kind": "ec", "level": 50}, "value": 0.013}],
        ),
    ]
    m = _resolve(ch, candidates)
    assert m.value is None
    assert m.value_qualifier == ValueQualifier.ND
    # The curve WAS fitted; it just yielded no readable value. Refresh/recompute
    # must keep that provenance or the stage funnel demotes the row back to
    # untested — see CampaignMeasurement.is_tested_nd.
    assert m.source_curve_id == candidates[0].curve_id
    assert m.source_run_id == candidates[0].run_id
    assert m.curve_snapshot is not None
    assert m.is_tested_nd


def test_manual_pick_nd_carries_no_provenance():
    """MANUAL_PICK's ND means "no chemist has picked yet" — still untested."""
    ch = _channel(SelectionRule.MANUAL_PICK)
    candidates = [_dr_candidate(5.0, run_date=date(2026, 5, 1))]
    m = _resolve(ch, candidates)
    assert m.value_qualifier == ValueQualifier.ND
    assert m.source_curve_id is None
    assert m.curve_snapshot is None
    assert not m.is_tested_nd


def test_latest_run_at_bound_pick_emits_gt_max_dose():
    ch = _channel(
        SelectionRule.LATEST_RUN,
        intercept_key=InterceptKey(kind="ec", level=90.0),
    )
    candidates = [
        _dr_candidate(
            5.0,
            run_date=date(2026, 5, 1),
            curve_class="partial",
            intercept_values=[
                {"spec": {"kind": "ec", "level": 90}, "value": 1e-9, "at_bound": True},
            ],
            raw_data=[
                {"concentration": 0.1, "response": 10},
                {"concentration": 50.0, "response": 35},
            ],
        ),
    ]
    m = _resolve(ch, candidates)
    assert m.value == 50.0
    assert m.value_qualifier == ValueQualifier.GT


def test_mean_across_runs_drops_inactive_from_aggregate():
    ch = _channel(SelectionRule.MEAN_ACROSS_RUNS)
    candidates = [
        _dr_candidate(
            10.0,
            curve_class="full",
            intercept_values=[{"spec": {"kind": "ec", "level": 50}, "value": 10.0}],
        ),
        _dr_candidate(
            20.0,
            curve_class="full",
            intercept_values=[{"spec": {"kind": "ec", "level": 50}, "value": 20.0}],
        ),
        # Inactive scalar must NOT pollute the mean.
        _dr_candidate(
            0.5,
            curve_class="inactive",
            intercept_values=[{"spec": {"kind": "ec", "level": 50}, "value": 0.5}],
        ),
    ]
    m = _resolve(ch, candidates)
    assert m.value == 15.0  # mean of the healthy pair only


_DOSES_TO_500 = [
    {"concentration": 0.5, "response": 2},
    {"concentration": 500.0, "response": 4},
]


def test_latest_run_inactive_curve_reads_above_its_top_dose():
    """Parity with the run tab: an inactive curve's potency is "> top dose" —
    a value a hit criterion reads as censored ("IC50 < 50" is a miss)."""
    ch = _channel(SelectionRule.LATEST_RUN)
    candidates = [
        _dr_candidate(
            0.013,
            run_date=date(2026, 5, 1),
            curve_class="inactive",
            intercept_values=[_iv("ec", 50, 0.013)],
            raw_data=_DOSES_TO_500,
        ),
    ]
    m = _resolve(ch, candidates)
    assert (m.value, m.value_qualifier) == (500.0, ValueQualifier.GT)
    assert m.source_curve_id == candidates[0].curve_id
    ic50_below_50 = HitCriterion(readout_name="IC50", operator="lt", value=50.0)
    assert ic50_below_50.is_met(m.value, m.value_qualifier) is False


def test_mean_across_runs_all_inactive_reads_the_bound_on_the_latest_snapshot():
    ch = _channel(SelectionRule.MEAN_ACROSS_RUNS)
    candidates = [
        _dr_candidate(
            10.0,
            run_date=date(2026, 1, 1),
            curve_class="inactive",
            intercept_values=[_iv("ec", 50, 10.0)],
            raw_data=_DOSES_TO_500,
        ),
        _dr_candidate(
            20.0,
            run_date=date(2026, 5, 1),
            curve_class="inactive",
            intercept_values=[_iv("ec", 50, 20.0)],
            raw_data=_DOSES_TO_500,
        ),
    ]
    m = _resolve(ch, candidates)
    assert (m.value, m.value_qualifier) == (500.0, ValueQualifier.GT)
    # No exact value was averaged, so no aggregate marker: the latest curve's own shape.
    assert m.curve_snapshot is not None
    assert "aggregate" not in m.curve_snapshot
    assert m.curve_snapshot["fitted_value"] == 20.0


def test_mean_across_runs_all_inactive_emits_nd():
    ch = _channel(SelectionRule.MEAN_ACROSS_RUNS)
    candidates = [
        _dr_candidate(
            10.0,
            curve_class="inactive",
            intercept_values=[{"spec": {"kind": "ec", "level": 50}, "value": 10.0}],
        ),
        _dr_candidate(
            20.0,
            curve_class="inactive",
            intercept_values=[{"spec": {"kind": "ec", "level": 50}, "value": 20.0}],
        ),
    ]
    m = _resolve(ch, candidates)
    assert m.value is None
    assert m.value_qualifier == ValueQualifier.ND
    # An aggregate has no single run to point at, so the ND cell pins no ids —
    # matching the value-carrying aggregate path and the import path. The
    # representative curve's snapshot is still what marks the cell as tested.
    assert m.source_curve_id is None
    assert m.source_run_id is None
    assert m.curve_snapshot is not None
    assert m.is_tested_nd


# ---------------------------------------------------------------------------
# Aggregate-mode curve_snapshot — overlay + marker shape
# ---------------------------------------------------------------------------


class TestBuildAggregateCurveSnapshot:
    """Pure-function tests on build_aggregate_curve_snapshot."""

    def test_aggregate_snapshot_carries_additional_curves_and_marker(self):
        """MEAN mode resolver produces a snapshot with additional_curves + aggregate."""
        candidates = [
            _dr_candidate(
                4.0,
                run_date=date(2026, 1, 1),
                intercept_values=[{"spec": {"kind": "ec", "level": 50}, "value": 4.0}],
            ),
            _dr_candidate(
                8.0,
                run_date=date(2026, 3, 1),
                intercept_values=[{"spec": {"kind": "ec", "level": 50}, "value": 8.0}],
            ),
            _dr_candidate(
                12.0,
                run_date=date(2026, 4, 1),  # rep — latest
                intercept_values=[{"spec": {"kind": "ec", "level": 50}, "value": 12.0}],
            ),
        ]
        snap = build_aggregate_curve_snapshot(
            candidates, aggregate_value=8.0, aggregate_label="mean"
        )
        assert snap is not None
        # Top-level snapshot is from the latest candidate (rep).
        assert snap["fitted_value"] == 12.0
        # 2 additional curves (non-rep), sorted desc by date.
        assert len(snap["additional_curves"]) == 2
        assert snap["additional_curves"][0]["fitted_value"] == 8.0  # March
        assert snap["additional_curves"][1]["fitted_value"] == 4.0  # January
        # Each additional carries run_date + run_id strings.
        assert snap["additional_curves"][0]["run_date"] == "2026-03-01"
        assert snap["additional_curves"][1]["run_date"] == "2026-01-01"
        assert isinstance(snap["additional_curves"][0]["run_id"], str)
        assert isinstance(snap["additional_curves"][1]["run_id"], str)
        # Aggregate marker.
        assert snap["aggregate"]["marker_x"] == 8.0
        assert snap["aggregate"]["marker_label"] == "mean"
        assert snap["aggregate"]["unit"] == "uM"  # _dr_candidate's seed unit

    def test_aggregate_snapshot_single_candidate_has_empty_additional_curves(self):
        """One candidate -> additional_curves is empty list, not None."""
        candidates = [
            _dr_candidate(5.0, run_date=date(2026, 1, 1)),
        ]
        snap = build_aggregate_curve_snapshot(
            candidates, aggregate_value=5.0, aggregate_label="mean"
        )
        assert snap is not None
        assert snap["additional_curves"] == []
        assert snap["aggregate"]["marker_x"] == 5.0
        assert snap["aggregate"]["marker_label"] == "mean"

    def test_aggregate_snapshot_returns_none_for_readout_data_source(self):
        """No curve shape on candidates -> overall snapshot is None.

        Matches existing _build_curve_snapshot behavior: when the rep's
        snapshot returns None, we return None too (no snapshot at all,
        same as today — FE renders "—" in the curve column).
        """
        # Build a candidate WITHOUT curve_top/bottom/hill_slope (the fields
        # _build_curve_snapshot guards on) — that's the readout_data shape.
        candidates = [
            ResolvedRun(
                value=5.0,
                qualifier=ValueQualifier.EQ,
                unit="nM",
                run_id=uuid.uuid4(),
                run_date=date(2026, 1, 1),
                run_approved=True,
                protocol_name="X",
                protocol_version=1,
                curve_id=None,
                readout_id=uuid.uuid4(),
                # No curve_top/bottom/hill_slope -> _build_curve_snapshot returns None.
            )
        ]
        snap = build_aggregate_curve_snapshot(
            candidates, aggregate_value=5.0, aggregate_label="mean"
        )
        assert snap is None

    def test_aggregate_snapshot_empty_candidates_returns_none(self):
        """Defensive: zero candidates -> None."""
        assert (
            build_aggregate_curve_snapshot([], aggregate_value=5.0, aggregate_label="mean") is None
        )

    def test_aggregate_snapshot_skips_additional_curves_without_shape(self):
        """If a non-rep contributor lacks curve shape (mixed source kinds —
        unlikely but defensible), the helper drops it from additional_curves
        rather than raising."""
        rep_with_shape = _dr_candidate(12.0, run_date=date(2026, 4, 1))
        # A "non-rep" candidate that ISN'T a DR curve — no curve shape.
        non_rep_without_shape = ResolvedRun(
            value=4.0,
            qualifier=ValueQualifier.EQ,
            unit="uM",
            run_id=uuid.uuid4(),
            run_date=date(2026, 1, 1),
            run_approved=True,
            protocol_name="X",
            protocol_version=1,
            curve_id=None,
            readout_id=uuid.uuid4(),
        )
        snap = build_aggregate_curve_snapshot(
            [non_rep_without_shape, rep_with_shape],
            aggregate_value=8.0,
            aggregate_label="mean",
        )
        assert snap is not None
        # Rep has shape so the overall snapshot is built; the shapeless
        # non-rep is silently dropped from the overlay list.
        assert snap["fitted_value"] == 12.0
        assert snap["additional_curves"] == []


def test_resolver_mean_mode_writes_aggregate_snapshot_on_measurement():
    """End-to-end: ColumnResolver under MEAN_ACROSS_RUNS produces a
    CampaignMeasurement whose curve_snapshot carries the additional_curves
    overlay + aggregate marker, not just the latest curve."""
    ch = _channel(SelectionRule.MEAN_ACROSS_RUNS)
    candidates = [
        _dr_candidate(
            10.0,
            run_date=date(2026, 1, 1),
            intercept_values=[{"spec": {"kind": "ec", "level": 50}, "value": 10.0}],
        ),
        _dr_candidate(
            20.0,
            run_date=date(2026, 5, 1),  # latest -> rep
            intercept_values=[{"spec": {"kind": "ec", "level": 50}, "value": 20.0}],
        ),
    ]
    m = _resolve(ch, candidates)
    assert m.value == 15.0
    assert m.curve_snapshot is not None
    # The top-level snapshot is the latest curve (May).
    assert m.curve_snapshot["fitted_value"] == 20.0
    # The January curve is overlayed as additional.
    assert len(m.curve_snapshot["additional_curves"]) == 1
    assert m.curve_snapshot["additional_curves"][0]["fitted_value"] == 10.0
    assert m.curve_snapshot["additional_curves"][0]["run_date"] == "2026-01-01"
    # Aggregate marker = cell value.
    assert m.curve_snapshot["aggregate"]["marker_x"] == 15.0
    assert m.curve_snapshot["aggregate"]["marker_label"] == "mean"


def test_resolver_geometric_mean_mode_writes_gmean_aggregate_snapshot():
    """GEOMETRIC_MEAN cells get marker_label='gmean' (not 'mean')."""
    ch = _channel(SelectionRule.GEOMETRIC_MEAN)
    candidates = [
        _dr_candidate(
            10.0,
            run_date=date(2026, 1, 1),
            intercept_values=[{"spec": {"kind": "ec", "level": 50}, "value": 10.0}],
        ),
        _dr_candidate(
            1000.0,
            run_date=date(2026, 5, 1),
            intercept_values=[{"spec": {"kind": "ec", "level": 50}, "value": 1000.0}],
        ),
    ]
    m = _resolve(ch, candidates)
    assert m.value == pytest.approx(100.0)
    assert m.curve_snapshot is not None
    assert m.curve_snapshot["aggregate"]["marker_label"] == "gmean"
    assert m.curve_snapshot["aggregate"]["marker_x"] == pytest.approx(100.0)


def test_resolver_latest_mode_snapshot_has_no_aggregate_fields():
    """Non-aggregate cells keep the legacy snapshot shape — no additional_curves,
    no aggregate field (FE chart adapter distinguishes single-curve from
    overlay rendering by these key's presence)."""
    ch = _channel(SelectionRule.LATEST_RUN)
    candidates = [
        _dr_candidate(
            10.0,
            run_date=date(2026, 1, 1),
            intercept_values=[{"spec": {"kind": "ec", "level": 50}, "value": 10.0}],
        ),
        _dr_candidate(
            20.0,
            run_date=date(2026, 5, 1),
            intercept_values=[{"spec": {"kind": "ec", "level": 50}, "value": 20.0}],
        ),
    ]
    m = _resolve(ch, candidates)
    assert m.curve_snapshot is not None
    # Latest cell's snapshot is the legacy single-curve shape.
    assert "additional_curves" not in m.curve_snapshot
    assert "aggregate" not in m.curve_snapshot
    assert m.curve_snapshot["fitted_value"] == 20.0


# ---------------------------------------------------------------------------
# D1 — reported-endpoint fallback on dose-response channels
# ---------------------------------------------------------------------------


def _endpoint_candidate(
    value: float,
    *,
    qualifier: ValueQualifier = ValueQualifier.EQ,
    approved: bool = True,
) -> ResolvedRun:
    """A raw readout_data row — the shape a summary-imported reported IC50 takes."""
    return ResolvedRun(
        value=value,
        qualifier=qualifier,
        unit="uM",
        run_id=uuid.uuid4(),
        run_date=date(2026, 3, 1),
        run_approved=approved,
        protocol_name="X",
        protocol_version=1,
        curve_id=None,
        readout_id=uuid.uuid4(),
    )


def test_dr_channel_with_no_curves_falls_back_to_reported_endpoint():
    ch = _channel(SelectionRule.LATEST_RUN)
    endpoint = _endpoint_candidate(32.0, qualifier=ValueQualifier.GT)
    m = _resolve(ch, [], endpoints=[endpoint])
    assert m.value == 32.0
    assert m.value_qualifier is ValueQualifier.GT
    assert m.source_readout_id == endpoint.readout_id
    assert m.source_curve_id is None


def test_dr_channel_endpoint_wins_when_the_only_curve_fails_qc():
    ch = _channel(SelectionRule.LATEST_RUN, qc={"require_approved": True})
    endpoint = _endpoint_candidate(7.5)
    m = _resolve(ch, [_candidate(1.0, approved=False)], endpoints=[endpoint])
    assert m.value == 7.5
    assert m.source_readout_id == endpoint.readout_id


def test_dr_channel_qc_surviving_inactive_curve_beats_an_endpoint():
    """A curve of any class that survives QC wins — an inactive one still
    resolves ND rather than letting the reported endpoint through."""
    ch = _channel(SelectionRule.LATEST_RUN)
    m = _resolve(
        ch,
        [_dr_candidate(0.013, run_date=date(2026, 1, 1), curve_class="inactive")],
        endpoints=[_endpoint_candidate(7.5)],
    )
    assert m.value is None
    assert m.value_qualifier is ValueQualifier.ND
    assert m.source_readout_id is None


def test_dr_channel_endpoint_fills_only_its_primary_intercept_channel():
    """A reported IC50 carries no curve, so the channel's intercept key can't be
    resolved off one: it matches the readout's primary intercept or it is ND.
    An IC90 channel stays untested (no curve behind it), not a miss."""
    endpoint = replace(
        _endpoint_candidate(12.0),
        intercept_values=[{"spec": {"kind": "ic", "level": 50.0}, "value": 12.0}],
    )

    def resolve(key: InterceptKey) -> CampaignMeasurement:
        return _resolve(_channel(SelectionRule.LATEST_RUN, intercept_key=key), [], [endpoint])

    ic50 = resolve(InterceptKey(kind="ic", level=50.0))
    assert ic50.value == 12.0
    assert ic50.value_qualifier is ValueQualifier.EQ

    ic90 = resolve(InterceptKey(kind="ic", level=90.0))
    assert ic90.value is None
    assert ic90.value_qualifier is ValueQualifier.ND
    assert ic90.source_curve_id is None
    assert ic90.curve_snapshot is None


def test_resolved_cell_is_not_tested():
    """Resolution never sets a QC verdict, even from an unapproved run."""
    run = replace(_dr_candidate(0.013, run_date=date(2026, 1, 1)), run_approved=False)
    assert _resolve(_channel(SelectionRule.LATEST_RUN), [run]).qc_verdict is None
