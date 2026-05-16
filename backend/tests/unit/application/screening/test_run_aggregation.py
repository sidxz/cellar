"""Unit coverage for the shared run-aggregation module.

Mirrors the existing channel_resolution tests' style. The module is the
single source of truth for selection rules, intercept resolution, and
chemistry-honest aggregate stats — both the campaign resolver and the
search activity service consume it.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from cellar.application.screening.run_aggregation import (
    ResolvedRun,
    apply_selection_rule,
    compute_aggregate_stats,
    detect_disagreement,
    resolve_intercept,
)
from cellar.domain.screening_assay.aggregation_types import (
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from cellar.domain.shared.hit_criterion import InterceptKey


def _run(
    *,
    value: float | None = 0.5,
    qualifier: ValueQualifier = ValueQualifier.EQ,
    run_date: date = date(2026, 1, 1),
    run_approved: bool = True,
    curve_class: str | None = "active",
    intercept_values: list[dict] | None = None,
    r_squared: float | None = 0.95,
) -> ResolvedRun:
    return ResolvedRun(
        run_id=uuid.uuid4(),
        run_date=run_date,
        run_approved=run_approved,
        curve_id=uuid.uuid4(),
        value=value,
        qualifier=qualifier,
        unit="uM",
        z_prime=None,
        protocol_name="Test",
        protocol_version=1,
        readout_id=None,
        curve_class=curve_class,
        curve_top=100.0,
        curve_bottom=0.0,
        curve_hill_slope=-1.0,
        curve_r_squared=r_squared,
        curve_raw_data=[{"x": 0.001, "y": 0}, {"x": 100.0, "y": 100}],
        intercept_values=intercept_values
        or [
            {"spec": {"kind": "ic", "level": 50.0}, "value": value, "at_bound": False}
        ],
    )


# ---- resolve_intercept ----


def test_resolve_intercept_inactive_curve_returns_nd():
    run = _run(curve_class="inactive")
    value, q = resolve_intercept(run, None)
    assert value is None
    assert q is ValueQualifier.ND


def test_resolve_intercept_at_bound_returns_gt_max_dose():
    run = _run(
        intercept_values=[
            {"spec": {"kind": "ic", "level": 50.0}, "value": 99.0, "at_bound": True}
        ]
    )
    value, q = resolve_intercept(run, None)
    assert value == 100.0  # max dose from raw_data
    assert q is ValueQualifier.GT


def test_resolve_intercept_keyed_picks_matching_intercept():
    run = _run(
        intercept_values=[
            {"spec": {"kind": "ec", "level": 50.0}, "value": 1.0, "at_bound": False},
            {"spec": {"kind": "ec", "level": 90.0}, "value": 5.0, "at_bound": False},
        ]
    )
    value, q = resolve_intercept(run, InterceptKey(kind="ec", level=90.0))
    assert value == 5.0
    assert q is ValueQualifier.EQ


def test_resolve_intercept_missing_intercept_returns_nd():
    run = _run(intercept_values=[{"spec": {"kind": "ic", "level": 50.0}, "value": 1.0}])
    value, q = resolve_intercept(run, InterceptKey(kind="ec", level=90.0))
    assert value is None
    assert q is ValueQualifier.ND


# ---- apply_selection_rule ----


def test_latest_approved_run_picks_max_run_date_among_eq():
    runs = [
        _run(value=0.10, run_date=date(2026, 1, 1)),
        _run(value=0.20, run_date=date(2026, 4, 1)),  # newest
        _run(value=0.05, run_date=date(2026, 3, 1)),
    ]
    out = apply_selection_rule(
        runs, SelectionRule.LATEST_APPROVED_RUN, QualifierHandling.EXCLUDE_QUALIFIED, None
    )
    assert out.value == 0.20
    assert out.qualifier is ValueQualifier.EQ
    assert len(out.contributing_run_ids) == 1
    assert out.representative_run is not None
    assert out.representative_run.run_date == date(2026, 4, 1)
    # contributing_run_ids points to the single picked run
    assert out.contributing_run_ids[0] == out.representative_run.run_id


def test_latest_approved_run_skips_inactive_under_exclude_qualified():
    """Latest is the latest *EQ* run when EXCLUDE_QUALIFIED."""
    runs = [
        _run(value=0.10, run_date=date(2026, 1, 1)),
        _run(value=0.20, run_date=date(2026, 2, 1)),
        _run(value=None, curve_class="inactive", run_date=date(2026, 4, 1)),
    ]
    out = apply_selection_rule(
        runs, SelectionRule.LATEST_APPROVED_RUN, QualifierHandling.EXCLUDE_QUALIFIED, None
    )
    assert out.value == 0.20  # the most recent EQ run, not the most recent overall


def test_all_inactive_returns_nd():
    runs = [_run(value=None, curve_class="inactive") for _ in range(3)]
    out = apply_selection_rule(
        runs, SelectionRule.LATEST_APPROVED_RUN, QualifierHandling.EXCLUDE_QUALIFIED, None
    )
    assert out.value is None
    assert out.qualifier is ValueQualifier.ND


def test_geometric_mean_log_space_average_of_eq_only():
    runs = [
        _run(value=0.10),
        _run(value=1.0),
        _run(value=10.0),
        _run(value=None, curve_class="inactive"),  # dropped
    ]
    out = apply_selection_rule(
        runs, SelectionRule.GEOMETRIC_MEAN, QualifierHandling.EXCLUDE_QUALIFIED, None
    )
    assert out.value == pytest.approx(1.0, rel=1e-6)
    assert out.qualifier is ValueQualifier.EQ
    # The Inactive run is NOT a contributor (only 3 EQ runs are)
    assert len(out.contributing_run_ids) == 3
    assert out.representative_run is not None
    # representative is the latest EQ run, not the inactive one
    assert out.representative_run.curve_class == "active"


def test_mean_across_runs_arithmetic_average_of_eq_only():
    runs = [_run(value=1.0), _run(value=2.0), _run(value=3.0)]
    out = apply_selection_rule(
        runs, SelectionRule.MEAN_ACROSS_RUNS, QualifierHandling.EXCLUDE_QUALIFIED, None
    )
    assert out.value == pytest.approx(2.0)
    assert len(out.contributing_run_ids) == 3
    assert out.qualifier is ValueQualifier.EQ
    # representative_run is for snapshot — should be one of the input runs
    assert out.representative_run is not None


def test_best_r_squared_picks_highest_r2_curve():
    runs = [
        _run(value=0.10, r_squared=0.92),
        _run(value=0.50, r_squared=0.99),  # winner
        _run(value=0.30, r_squared=0.85),
    ]
    out = apply_selection_rule(
        runs, SelectionRule.BEST_R_SQUARED, QualifierHandling.EXCLUDE_QUALIFIED, None
    )
    assert out.value == 0.50


def test_best_r_squared_handles_zero_r2_distinct_from_none():
    """r²=0.0 is a legal value (flat trace); must not tie with r²=None."""
    runs = [
        _run(value=0.10, r_squared=0.0),     # legal but bad fit
        _run(value=0.20, r_squared=None),    # not yet fit / unknown
        _run(value=0.30, r_squared=0.85),    # winner
    ]
    out = apply_selection_rule(
        runs, SelectionRule.BEST_R_SQUARED, QualifierHandling.EXCLUDE_QUALIFIED, None
    )
    assert out.value == 0.30
    # And: zero beats None when those are the only two
    runs2 = [
        _run(value=0.10, r_squared=0.0),
        _run(value=0.20, r_squared=None),
    ]
    out2 = apply_selection_rule(
        runs2, SelectionRule.BEST_R_SQUARED, QualifierHandling.EXCLUDE_QUALIFIED, None
    )
    assert out2.value == 0.10  # the r²=0.0 wins; None sorts to -inf


def test_manual_pick_returns_nd_in_search_context():
    runs = [_run(value=0.5)]
    out = apply_selection_rule(
        runs, SelectionRule.MANUAL_PICK, QualifierHandling.EXCLUDE_QUALIFIED, None
    )
    assert out.value is None
    assert out.qualifier is ValueQualifier.ND


def test_empty_run_list_returns_nd():
    out = apply_selection_rule(
        [], SelectionRule.LATEST_APPROVED_RUN, QualifierHandling.EXCLUDE_QUALIFIED, None
    )
    assert out.value is None
    assert out.qualifier is ValueQualifier.ND


# ---- compute_aggregate_stats ----


def test_aggregate_stats_eq_runs_compute_geometric_mean_and_fold_range():
    runs = [_run(value=0.10), _run(value=0.40), _run(value=1.60)]
    stats = compute_aggregate_stats(runs, None)
    assert stats.geometric_mean == pytest.approx(0.4, rel=1e-3)
    assert stats.fold_range == pytest.approx(16.0)
    # log10 values: -1, -0.398, 0.204; mean ~ -0.398; SD ~ 0.602
    assert stats.log_value_mean == pytest.approx(-0.398, abs=0.01)
    assert stats.log_value_sd == pytest.approx(0.602, abs=0.01)


def test_aggregate_stats_single_eq_run_returns_zero_spread():
    stats = compute_aggregate_stats([_run(value=0.5)], None)
    assert stats.geometric_mean == pytest.approx(0.5)
    assert stats.fold_range == pytest.approx(1.0)
    assert stats.log_value_sd == pytest.approx(0.0)


def test_aggregate_stats_no_eq_runs_all_none():
    runs = [_run(value=None, curve_class="inactive")]
    stats = compute_aggregate_stats(runs, None)
    assert stats.geometric_mean is None
    assert stats.fold_range is None
    assert stats.log_value_mean is None
    assert stats.log_value_sd is None


# ---- detect_disagreement ----


def test_disagreement_log_range_above_threshold():
    runs = [_run(value=0.10), _run(value=0.20), _run(value=2.0)]
    # log10 range = log10(2.0) - log10(0.1) = 1.30 > 1.0
    assert detect_disagreement(runs, None) is True


def test_no_disagreement_when_log_range_within_threshold():
    runs = [_run(value=0.10), _run(value=0.20), _run(value=0.99)]
    # log10 range = log10(0.99) - log10(0.1) ≈ 0.996
    assert detect_disagreement(runs, None) is False


def test_disagreement_when_mixed_inactive_and_active():
    runs = [_run(value=0.10), _run(value=None, curve_class="inactive")]
    assert detect_disagreement(runs, None) is True


def test_no_disagreement_with_single_run():
    assert detect_disagreement([_run(value=0.5)], None) is False
