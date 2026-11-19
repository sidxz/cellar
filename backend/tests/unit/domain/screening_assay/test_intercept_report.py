"""report_intercept: one curve intercept as every reader reports it."""

from __future__ import annotations

import math

import pytest

from cellar.domain.screening_assay.intercept_report import report_intercept
from cellar.domain.shared.aggregation_types import ValueQualifier
from tests.fixtures.intercept_report_cases import CASES, Case


@pytest.mark.parametrize("case", [c for c in CASES if c.stored], ids=lambda c: c.id)
def test_the_class_wins_at_both_ends_then_the_stored_qualifier_then_todays_rules(case: Case):
    low, high = case.doses or (None, None)

    value, qualifier = report_intercept(
        case.curve_class,
        case.qualifier,
        case.value,
        low,
        high,
        at_bound=case.at_bound,
        primary=case.primary,
    )

    assert (value, qualifier) == (case.expected[0], ValueQualifier(case.expected[1]))


def test_an_nd_intercepts_nan_reads_as_no_value():
    """The domain holds an nd intercept's value as NaN: never a number on any reader."""
    nd = (None, ValueQualifier.ND)
    assert report_intercept("full", "nd", math.nan, 0.01, 100.0, primary=True) == nd
    assert report_intercept("full", None, math.nan, 0.01, 100.0, primary=True) == nd
