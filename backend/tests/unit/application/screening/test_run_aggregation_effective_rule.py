"""effective_rule — the rule a column really uses, decided per column, never per cell."""

import pytest

from cellar.application.screening.run_aggregation import effective_rule
from cellar.domain.shared.aggregation_types import SelectionRule


def test_geomean_on_percent_column_is_arithmetic_mean():
    rule = effective_rule(SelectionRule.GEOMETRIC_MEAN, unit="%", single_point=True)
    assert rule == SelectionRule.MEAN_ACROSS_RUNS


def test_geomean_on_unitless_column_is_arithmetic_mean():
    rule = effective_rule(SelectionRule.GEOMETRIC_MEAN, unit=None, single_point=True)
    assert rule == SelectionRule.MEAN_ACROSS_RUNS


def test_geomean_on_concentration_column_is_kept():
    rule = effective_rule(SelectionRule.GEOMETRIC_MEAN, unit="µg/mL", single_point=True)
    assert rule == SelectionRule.GEOMETRIC_MEAN


def test_best_fit_on_single_point_is_latest_run():
    rule = effective_rule(SelectionRule.BEST_R_SQUARED, unit="%", single_point=True)
    assert rule == SelectionRule.LATEST_RUN


@pytest.mark.parametrize("rule", list(SelectionRule))
def test_dose_response_columns_keep_every_rule(rule):
    assert effective_rule(rule, unit="nM", single_point=False) == rule
