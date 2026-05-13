"""Tests for curve fitting domain types."""

from __future__ import annotations

from cellar.domain.screening_assay.curve_fitting import (
    ConcentrationResponsePoint,
    FittedCurveResult,
)
from cellar.domain.screening_assay.enums import CurveClass


def test_concentration_response_point_defaults():
    pt = ConcentrationResponsePoint(concentration=1.0, response=50.0)
    assert pt.concentration == 1.0
    assert pt.response == 50.0
    assert pt.is_excluded is False


def test_concentration_response_point_excluded():
    pt = ConcentrationResponsePoint(concentration=1.0, response=50.0, is_excluded=True)
    assert pt.is_excluded is True


def test_fitted_curve_result_fields():
    result = FittedCurveResult(
        fitted_value=33.0,
        hill_slope=-1.1,
        top=100.0,
        bottom=1.5,
        r_squared=0.992,
        confidence_interval_low=25.0,
        confidence_interval_high=42.0,
        curve_class=CurveClass.FULL,
        num_points=10,
        raw_data=[{"concentration": 1.0, "response": 50.0}],
        excluded_points=[],
    )
    assert result.fitted_value == 33.0
    assert result.curve_class == CurveClass.FULL
    assert result.num_points == 10
