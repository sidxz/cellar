"""Tests for two-pass 3σ outlier detection in LmfitCurveFitter."""

from __future__ import annotations

import random

from returns.result import Success

from chem_vault.domain.screening_assay.curve_fitting import ConcentrationResponsePoint
from chem_vault.domain.screening_assay.dose_response_config import DoseResponseConfig
from chem_vault.domain.screening_assay.enums import CurveType
from chem_vault.infrastructure.lmfit.curve_fitter import LmfitCurveFitter


def _make_config() -> DoseResponseConfig:
    return DoseResponseConfig(
        curve_type=CurveType.IC50,
        x_readout_name="Concentration",
        y_readout_name="% Inhibition",
    )


def _generate_hill_data_with_outlier(
    ic50: float = 100.0,
    outlier_index: int = 3,
    outlier_value: float = 200.0,
    seed: int = 42,
) -> list[ConcentrationResponsePoint]:
    rng = random.Random(seed)
    concs = [10000.0 / (3**i) for i in range(10)]
    points = []
    for i, c in enumerate(concs):
        response = 100.0 / (1 + (c / ic50) ** 1.0)
        noise = rng.gauss(0, 2.0)
        if i == outlier_index:
            response = outlier_value
        points.append(ConcentrationResponsePoint(concentration=c, response=response + noise))
    return points


class TestTwoPassOutlierDetection:
    def setup_method(self):
        self.fitter = LmfitCurveFitter()

    def test_outlier_detected_and_excluded(self):
        points = _generate_hill_data_with_outlier(outlier_index=3, outlier_value=200.0)
        config = _make_config()
        result = self.fitter.fit(points, config)

        assert isinstance(result, Success)
        fitted = result.unwrap()
        assert len(fitted.excluded_points) >= 1
        outlier_reasons = [p.get("reason") for p in fitted.excluded_points]
        assert "auto_3sigma" in outlier_reasons

    def test_no_outliers_when_data_is_clean(self):
        rng = random.Random(42)
        concs = [10000.0 / (3**i) for i in range(10)]
        points = [
            ConcentrationResponsePoint(
                concentration=c,
                response=100.0 / (1 + (c / 100.0) ** 1.0) + rng.gauss(0, 1.0),
            )
            for c in concs
        ]
        config = _make_config()
        result = self.fitter.fit(points, config)

        assert isinstance(result, Success)
        fitted = result.unwrap()
        auto_outliers = [p for p in fitted.excluded_points if p.get("reason") == "auto_3sigma"]
        assert len(auto_outliers) == 0

    def test_outlier_improves_fit(self):
        points = _generate_hill_data_with_outlier(outlier_index=5, outlier_value=180.0)
        config = _make_config()
        result = self.fitter.fit(points, config)

        assert isinstance(result, Success)
        fitted = result.unwrap()
        assert fitted.r_squared > 0.9

    def test_no_outlier_detection_with_few_points(self):
        # 5 points — too few for meaningful outlier detection (threshold is 6)
        rng = random.Random(42)
        concs = [10000.0 / (3**i) for i in range(5)]
        points = [
            ConcentrationResponsePoint(concentration=c, response=100.0 / (1 + (c / 100.0)) + rng.gauss(0, 1.0))
            for c in concs
        ]
        # Add an outlier
        points[2] = ConcentrationResponsePoint(concentration=points[2].concentration, response=200.0)
        config = _make_config()
        result = self.fitter.fit(points, config)

        assert isinstance(result, Success)
        fitted = result.unwrap()
        # Should NOT have auto-excluded outliers (not enough points)
        auto_outliers = [p for p in fitted.excluded_points if p.get("reason") == "auto_3sigma"]
        assert len(auto_outliers) == 0
