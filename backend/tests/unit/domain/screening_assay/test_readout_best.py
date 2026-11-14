"""Which of a compound's values stands for it: the direction a readout is read in."""

from __future__ import annotations

import pytest

from cellar.domain.screening_assay.readout_best import BestDirection, best_direction, pick_best
from cellar.domain.shared.enums import Qualifier

EQ, GT = Qualifier.EQUAL, Qualifier.GREATER_THAN


@pytest.mark.parametrize(
    ("data_type", "measure", "expected"),
    [
        ("numeric", None, BestDirection.HIGH),
        ("dose_response", None, BestDirection.LOW),
        ("numeric", "tm", BestDirection.MAGNITUDE),
        ("numeric", "delta_tm", BestDirection.MAGNITUDE),
        ("numeric", "max_delta_tm", BestDirection.MAGNITUDE),
        ("numeric", "delta_tm_at_concentration", BestDirection.MAGNITUDE),
        ("numeric", "lowest_shift_concentration", BestDirection.LOW),
    ],
)
def test_best_direction(data_type, measure, expected):
    assert best_direction(data_type, measure) is expected


def test_magnitude_keeps_the_sign_of_the_largest_shift():
    # CC-014538's ΔTm: a -8.5 shift must not lose to +1.4.
    values = [(-8.5, EQ), (-7.8, EQ), (-6.3, EQ), (1.4, EQ)]
    assert pick_best(values, BestDirection.MAGNITUDE) == (-8.5, EQ)


def test_high_and_low():
    values = [(3.0, EQ), (50.0, GT), (6.25, EQ)]
    assert pick_best(values, BestDirection.HIGH) == (50.0, GT)
    assert pick_best(values, BestDirection.LOW) == (3.0, EQ)


def test_no_values():
    assert pick_best([], BestDirection.HIGH) is None


def test_best_of_min_max_matches_pick_best():
    from cellar.domain.screening_assay.readout_best import best_of_range

    assert best_of_range(-8.5, 1.4, BestDirection.MAGNITUDE) == -8.5
    assert best_of_range(-1.0, 4.0, BestDirection.MAGNITUDE) == 4.0
    assert best_of_range(-1.0, 4.0, BestDirection.HIGH) == 4.0
    assert best_of_range(-1.0, 4.0, BestDirection.LOW) == -1.0
    assert best_of_range(None, None, BestDirection.MAGNITUDE) is None
