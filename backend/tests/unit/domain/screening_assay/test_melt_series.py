"""Descriptive concentration-series values from a temperature window's ΔTm."""

from __future__ import annotations

import uuid

import pytest

from cellar.domain.screening_assay.melt_series import (
    SeriesPoint,
    SeriesValue,
    series_points,
    series_values,
)
from cellar.domain.screening_assay.melt_window import (
    MeltMeasure,
    MeltReadoutConfig,
    PositionWindowResult,
    WindowResult,
)
from cellar.domain.shared.enums import Qualifier
from cellar.domain.shared.errors import ValidationError

A = uuid.UUID(int=1)
B = uuid.UUID(int=2)


def _cfg(measure: MeltMeasure, **over) -> MeltReadoutConfig:
    return MeltReadoutConfig(
        window="Main", measure=measure, channel_key="ratio", low=50.0, high=85.0, **over
    )


def _pts(batch: uuid.UUID, by_dose: dict[float | None, list[float]]) -> list[SeriesPoint]:
    return [SeriesPoint(batch, dose, d) for dose, ds in by_dose.items() for d in ds]


MAX = _cfg(MeltMeasure.MAX_DELTA_TM)


def test_max_delta_tm_means_per_concentration_keeps_sign():
    pts = _pts(A, {6.25: [-1.0, -3.0], 25.0: [-8.6], 50.0: [-8.0]})
    assert series_values(MAX, pts) == [SeriesValue(A, -8.6, Qualifier.EQUAL, 25.0)]


def test_max_delta_tm_tie_prefers_higher_concentration():
    pts = _pts(A, {10.0: [3.0], 20.0: [-3.0]})
    assert series_values(MAX, pts) == [SeriesValue(A, -3.0, Qualifier.EQUAL, 20.0)]


def test_max_delta_tm_groups_missing_concentration():
    pts = _pts(A, {None: [1.0, 3.0], 10.0: [1.5]})
    assert series_values(MAX, pts) == [SeriesValue(A, 2.0, Qualifier.EQUAL, None)]


def test_max_delta_tm_treats_dose_zero_as_no_concentration():
    pts = _pts(A, {None: [1.0], 0.0: [3.0], 10.0: [1.5]})
    assert series_values(MAX, pts) == [SeriesValue(A, 2.0, Qualifier.EQUAL, None)]


LOWEST = _cfg(MeltMeasure.LOWEST_SHIFT_CONCENTRATION, threshold=2.0)


def test_lowest_shift_concentration_strict_outside():
    pts = _pts(A, {6.25: [-2.0], 12.5: [-2.1], 25.0: [-5.0]})
    assert series_values(LOWEST, pts) == [SeriesValue(A, 12.5, Qualifier.EQUAL, 12.5)]


def test_lowest_shift_concentration_uses_the_mean_at_each_concentration():
    # 6.25 has one point outside but its mean (-1.5) is inside.
    pts = _pts(A, {6.25: [-2.5, -0.5], 12.5: [2.5]})
    assert series_values(LOWEST, pts) == [SeriesValue(A, 12.5, Qualifier.EQUAL, 12.5)]


def test_lowest_shift_concentration_not_reached_is_censored():
    pts = _pts(A, {6.25: [-0.5], 50.0: [1.9]})
    assert series_values(LOWEST, pts) == [SeriesValue(A, 50.0, Qualifier.GREATER_THAN, 50.0)]


def test_lowest_shift_ignores_zero_and_missing_doses():
    assert series_values(LOWEST, _pts(A, {None: [-9.0], 0.0: [-9.0]})) == []


AT_50 = _cfg(MeltMeasure.DELTA_TM_AT_CONCENTRATION, concentration=50.0)


def test_delta_tm_at_concentration_matches_within_tolerance():
    pts = _pts(A, {50.00000001: [-8.0], 50.0: [-8.2], 25.0: [-1.0]})
    [v] = series_values(AT_50, pts)
    assert v.batch_id == A and v.value == pytest.approx(-8.1)
    assert v.qualifier is Qualifier.EQUAL and v.concentration == 50.0


def test_delta_tm_at_concentration_not_tested_gives_nothing():
    assert series_values(AT_50, _pts(A, {25.0: [-1.0]})) == []


def test_two_batches_two_values_sorted_by_batch():
    pts = _pts(B, {10.0: [4.0]}) + _pts(A, {10.0: [-3.0]})
    assert [v.batch_id for v in series_values(MAX, pts)] == [A, B]


def test_per_position_measure_is_refused():
    with pytest.raises(ValidationError):
        series_values(_cfg(MeltMeasure.DELTA_TM), _pts(A, {10.0: [1.0]}))


def test_series_points_keep_positions_with_a_shift_and_a_batch():
    ref, sample, no_batch, no_shift = (uuid.uuid4() for _ in range(4))
    result = WindowResult(
        low=50.0,
        high=85.0,
        reference_tm=71.3,
        reference_count=1,
        positions=(
            PositionWindowResult(ref, 71.3, None, ()),
            PositionWindowResult(sample, 62.7, -8.6, ()),
            PositionWindowResult(no_batch, 70.0, -1.3, ()),
            PositionWindowResult(no_shift, None, None, ()),
        ),
        flags=(),
    )
    wells = {ref: (None, None), sample: (A, 25.0), no_batch: (None, 10.0), no_shift: (A, 50.0)}
    assert series_points(result, wells) == [SeriesPoint(A, 25.0, -8.6)]
