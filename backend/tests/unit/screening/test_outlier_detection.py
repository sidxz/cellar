"""Tests for 3σ outlier *suggestion* detection in LmfitCurveFitter.

Post-redesign: the fitter no longer silently removes outliers + refits.
It detects candidates on the first-pass fit and returns them as
``OutlierSuggestion`` entries; the use-case layer persists them as
``ExcludedPointDetail(source=AUTO_3SIGMA, excluded=False)`` so the FE
can render them as yellow-halo "suggested" markers for the chemist to
explicitly accept or reject.
"""

from __future__ import annotations

import random

from returns.result import Success

from cellar.domain.screening_assay.curve_fitting import ConcentrationResponsePoint
from cellar.domain.screening_assay.dose_response_config import DoseResponseConfig
from cellar.domain.screening_assay.enums import CurveType
from cellar.infrastructure.lmfit.curve_fitter import LmfitCurveFitter


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


class TestOutlierSuggestionDetection:
    def setup_method(self):
        self.fitter = LmfitCurveFitter()

    def test_outlier_detected_and_suggested(self):
        points = _generate_hill_data_with_outlier(outlier_index=3, outlier_value=200.0)
        config = _make_config()
        result = self.fitter.fit(points, config)

        assert isinstance(result, Success)
        fitted = result.unwrap()
        # Suggestion present, naming the offending input position.
        assert len(fitted.outlier_suggestions) >= 1
        idxs = {s.idx for s in fitted.outlier_suggestions}
        assert 3 in idxs
        # No silent exclusion.
        auto_excluded = [
            p for p in fitted.excluded_points if p.get("reason") == "auto_3sigma"
        ]
        assert auto_excluded == []
        # Point still contributed to the fit.
        assert fitted.num_points == len(points)

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
        assert fitted.outlier_suggestions == ()
        auto_outliers = [p for p in fitted.excluded_points if p.get("reason") == "auto_3sigma"]
        assert len(auto_outliers) == 0

    def test_outlier_present_returns_full_fit_with_suggestion(self):
        """Post-redesign, the fitter does NOT do a second-pass refit on a
        clean subset — it returns the full-data fit + the suggestion.
        The chemist is expected to accept the suggestion (which triggers a
        refit on commit) if they agree."""
        points = _generate_hill_data_with_outlier(outlier_index=5, outlier_value=180.0)
        config = _make_config()
        result = self.fitter.fit(points, config)

        assert isinstance(result, Success)
        fitted = result.unwrap()
        # The outlier was flagged as a suggestion …
        assert any(s.idx == 5 for s in fitted.outlier_suggestions)
        # … but stays in the fit until a chemist confirms (no silent removal).
        assert fitted.num_points == len(points)

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
        # Too few points → no detection at all (neither suggestions nor exclusions).
        assert fitted.outlier_suggestions == ()
        auto_outliers = [p for p in fitted.excluded_points if p.get("reason") == "auto_3sigma"]
        assert len(auto_outliers) == 0
