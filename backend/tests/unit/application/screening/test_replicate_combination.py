"""combine_replicates — one run's replicate wells become one (value, qualifier)."""

import pytest

from cellar.application.screening.run_aggregation import combine_replicates
from cellar.domain.screening_assay.activity_types import ReplicateStats
from cellar.domain.shared.aggregation_types import ValueQualifier


def _stats(**kw) -> ReplicateStats:
    base = dict(
        eq_count=0,
        eq_mean=None,
        eq_median=None,
        eq_min=None,
        eq_max=None,
        eq_geomean=None,
        gt_count=0,
        gt_max_bound=None,
        lt_count=0,
        lt_min_bound=None,
    )
    base.update(kw)
    return ReplicateStats(**base)


EQ_10_12_14 = dict(
    eq_count=3, eq_mean=12.0, eq_median=12.0, eq_min=10.0, eq_max=14.0, eq_geomean=11.9
)


@pytest.mark.parametrize(
    ("aggregation", "expected"),
    [("mean", 12.0), ("none", 12.0), ("median", 12.0), ("min", 10.0), ("max", 14.0)],
)
def test_unqualified_replicates_follow_the_readout_aggregation(aggregation, expected):
    assert combine_replicates(_stats(**EQ_10_12_14), aggregation, unit="%") == (
        expected,
        ValueQualifier.EQ,
    )


def test_median_is_a_real_median():
    stats = _stats(
        eq_count=3, eq_mean=40.0, eq_median=10.0, eq_min=5.0, eq_max=105.0, eq_geomean=17.0
    )
    assert combine_replicates(stats, "median", unit="%") == (10.0, ValueQualifier.EQ)


def test_geomean_replicates_on_concentration_unit():
    assert combine_replicates(_stats(**EQ_10_12_14), "geometric_mean", unit="µM") == (
        11.9,
        ValueQualifier.EQ,
    )


def test_geomean_replicates_on_percent_use_arithmetic_mean():
    assert combine_replicates(_stats(**EQ_10_12_14), "geometric_mean", unit="%") == (
        12.0,
        ValueQualifier.EQ,
    )


def test_mixed_qualified_and_unqualified_uses_unqualified_only():
    # 10, 12, >50 → the ">50" replicate is ignored
    stats = _stats(
        eq_count=2,
        eq_mean=11.0,
        eq_median=11.0,
        eq_min=10.0,
        eq_max=12.0,
        eq_geomean=10.95,
        gt_count=1,
        gt_max_bound=50.0,
    )
    assert combine_replicates(stats, "mean", unit="µM") == (11.0, ValueQualifier.EQ)


def test_all_greater_than_takes_the_largest_bound():
    stats = _stats(gt_count=2, gt_max_bound=50.0)  # >25, >50
    assert combine_replicates(stats, "mean", unit="µM") == (50.0, ValueQualifier.GT)


def test_all_less_than_takes_the_smallest_bound():
    stats = _stats(lt_count=2, lt_min_bound=0.1)  # <0.1, <0.2
    assert combine_replicates(stats, "mean", unit="µM") == (0.1, ValueQualifier.LT)


def test_mixed_greater_and_less_than_is_nd():
    stats = _stats(gt_count=1, gt_max_bound=50.0, lt_count=1, lt_min_bound=0.1)
    assert combine_replicates(stats, "mean", unit="µM") == (None, ValueQualifier.ND)


def test_no_values_is_nd():
    assert combine_replicates(_stats(), "mean", unit="%") == (None, ValueQualifier.ND)
