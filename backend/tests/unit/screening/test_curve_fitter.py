"""Tests for LmfitCurveFitter — 4PL Hill equation fitting."""

from __future__ import annotations

import random

import pytest
from returns.result import Failure, Success

from chem_vault.domain.screening_assay.curve_fitting import ConcentrationResponsePoint
from chem_vault.domain.screening_assay.dose_response_config import DoseResponseConfig
from chem_vault.domain.screening_assay.enums import (
    CurveClass,
    CurveType,
    HillSlopeConstraint,
)
from chem_vault.infrastructure.lmfit.curve_fitter import LmfitCurveFitter


def _generate_hill_data(
    ic50: float = 100.0,
    hill_slope: float = -1.0,
    top: float = 100.0,
    bottom: float = 0.0,
    n_points: int = 10,
    noise_pct: float = 0.02,
    seed: int = 42,
) -> list[ConcentrationResponsePoint]:
    """Generate synthetic 4PL dose-response data with optional noise."""
    rng = random.Random(seed)
    concs = [10000.0 / (3**i) for i in range(n_points)]
    points = []
    for c in concs:
        response = bottom + (top - bottom) / (1 + (c / ic50) ** abs(hill_slope))
        noise = rng.gauss(0, (top - bottom) * noise_pct)
        points.append(ConcentrationResponsePoint(concentration=c, response=response + noise))
    return points


def _make_config(
    curve_type: CurveType = CurveType.IC50,
    hill_constraint: HillSlopeConstraint = HillSlopeConstraint.UNCONSTRAINED,
    top_constraint: float | None = None,
    bottom_constraint: float | None = None,
) -> DoseResponseConfig:
    return DoseResponseConfig(
        curve_type=curve_type,
        x_readout_name="Concentration",
        y_readout_name="% Inhibition",
        hill_slope_constraint=hill_constraint,
        top_constraint=top_constraint,
        bottom_constraint=bottom_constraint,
    )


class TestLmfitCurveFitter:
    def setup_method(self):
        self.fitter = LmfitCurveFitter()

    def test_fit_full_curve(self):
        points = _generate_hill_data(ic50=100.0, hill_slope=-1.0, top=100.0, bottom=0.0)
        config = _make_config()
        result = self.fitter.fit(points, config)
        assert isinstance(result, Success)
        fitted = result.unwrap()
        assert abs(fitted.fitted_value - 100.0) < 20.0
        assert fitted.r_squared > 0.95
        assert fitted.curve_class == CurveClass.FULL
        assert fitted.num_points == 10
        assert len(fitted.raw_data) == 10
        assert len(fitted.excluded_points) == 0

    def test_fit_partial_curve(self):
        points = _generate_hill_data(ic50=100.0, top=60.0, bottom=5.0)
        config = _make_config()
        result = self.fitter.fit(points, config)
        assert isinstance(result, Success)
        fitted = result.unwrap()
        assert fitted.curve_class == CurveClass.PARTIAL

    def test_fit_inactive(self):
        points = [
            ConcentrationResponsePoint(concentration=10000.0 / (3**i), response=5.0 + random.Random(i).gauss(0, 2))
            for i in range(10)
        ]
        config = _make_config()
        result = self.fitter.fit(points, config)
        assert isinstance(result, Success)
        fitted = result.unwrap()
        assert fitted.curve_class == CurveClass.INACTIVE

    def test_fit_with_excluded_points(self):
        points = _generate_hill_data(ic50=100.0)
        points[0] = ConcentrationResponsePoint(
            concentration=points[0].concentration, response=points[0].response, is_excluded=True,
        )
        points[1] = ConcentrationResponsePoint(
            concentration=points[1].concentration, response=points[1].response, is_excluded=True,
        )
        config = _make_config()
        result = self.fitter.fit(points, config)
        assert isinstance(result, Success)
        fitted = result.unwrap()
        assert fitted.num_points == 8
        assert len(fitted.excluded_points) == 2

    def test_fit_too_few_points(self):
        points = _generate_hill_data(n_points=3)
        config = _make_config()
        result = self.fitter.fit(points, config)
        assert isinstance(result, Failure)
        assert "at least 4" in str(result.failure()).lower()

    def test_fit_with_hill_slope_constraint_negative(self):
        points = _generate_hill_data(ic50=100.0, hill_slope=-1.0)
        config = _make_config(hill_constraint=HillSlopeConstraint.NEGATIVE_ONLY)
        result = self.fitter.fit(points, config)
        assert isinstance(result, Success)
        assert result.unwrap().hill_slope < 0

    def test_fit_with_fixed_top(self):
        points = _generate_hill_data(ic50=100.0, top=100.0)
        config = _make_config(top_constraint=100.0)
        result = self.fitter.fit(points, config)
        assert isinstance(result, Success)
        assert abs(result.unwrap().top - 100.0) < 1.0

    def test_confidence_intervals(self):
        points = _generate_hill_data(ic50=100.0)
        config = _make_config()
        result = self.fitter.fit(points, config)
        assert isinstance(result, Success)
        fitted = result.unwrap()
        assert fitted.confidence_interval_low < fitted.fitted_value
        assert fitted.confidence_interval_high > fitted.fitted_value

    def test_raw_data_format(self):
        points = _generate_hill_data(ic50=100.0, n_points=8)
        config = _make_config()
        result = self.fitter.fit(points, config)
        assert isinstance(result, Success)
        fitted = result.unwrap()
        for pt in fitted.raw_data:
            assert "concentration" in pt
            assert "response" in pt
