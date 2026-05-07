"""Tests for PlateQualityCalculator — Z-prime computation."""

from __future__ import annotations

import pytest

from chem_vault.domain.screening_assay.plate_quality import (
    PlateQualityCalculator,
    PlateQualityResult,
)


class TestPlateQualityCalculator:
    def setup_method(self):
        self.calc = PlateQualityCalculator()

    def test_excellent_zprime(self):
        pos = [95.0, 96.0, 94.0, 95.5, 94.5, 96.5, 95.0, 95.5]
        neg = [5.0, 6.0, 4.0, 5.5, 4.5, 6.5, 5.0, 5.5]
        result = self.calc.compute(pos, neg)
        assert result.z_prime > 0.5
        assert result.classification == "excellent"

    def test_marginal_zprime(self):
        # SD ~7 per group, separation ~60 → Z' = 1 - (3*7 + 3*7)/60 ≈ 0.30
        pos = [80.0, 90.0, 72.0, 85.0, 78.0, 92.0, 74.0, 87.0]
        neg = [20.0, 28.0, 14.0, 24.0, 18.0, 30.0, 16.0, 26.0]
        result = self.calc.compute(pos, neg)
        assert 0.0 <= result.z_prime < 0.5
        assert result.classification == "marginal"

    def test_poor_zprime(self):
        pos = [50.0, 90.0, 30.0, 70.0, 40.0, 80.0, 20.0, 60.0]
        neg = [40.0, 80.0, 20.0, 60.0, 30.0, 70.0, 10.0, 50.0]
        result = self.calc.compute(pos, neg)
        assert result.z_prime < 0
        assert result.classification == "poor"

    def test_signal_to_background(self):
        """S/B is the higher mean over the lower mean — always >= 1
        regardless of which control sits higher (convention-agnostic)."""
        pos = [100.0, 100.0, 100.0, 100.0]
        neg = [10.0, 10.0, 10.0, 10.0]
        result = self.calc.compute(pos, neg)
        assert result.signal_to_background == pytest.approx(10.0)

    def test_signal_to_background_pos_below_neg(self):
        """Inverted convention (POS < NEG) still produces S/B >= 1."""
        pos = [10.0, 10.0, 10.0, 10.0]
        neg = [100.0, 100.0, 100.0, 100.0]
        result = self.calc.compute(pos, neg)
        assert result.signal_to_background == pytest.approx(10.0)

    def test_insufficient_controls(self):
        result = self.calc.compute([100.0], [10.0])
        assert result.z_prime == 0.0
        assert result.classification == "insufficient_data"

    def test_result_fields(self):
        pos = [95.0, 96.0, 94.0, 95.5]
        neg = [5.0, 6.0, 4.0, 5.5]
        result = self.calc.compute(pos, neg)
        assert isinstance(result, PlateQualityResult)
        assert result.positive_control_mean > 0
        assert result.positive_control_sd >= 0
        assert result.negative_control_mean > 0
        assert result.negative_control_sd >= 0
