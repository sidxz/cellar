"""Tests for the DoseResponseConfig dict <-> VO helper."""

from __future__ import annotations

import pytest

from cellar.application.screening._dose_response_config_serde import (
    deserialize_dose_response_config,
    serialize_dose_response_config,
)
from cellar.domain.screening_assay.dose_response_config import (
    DEFAULT_FULL_R2_MIN,
    DEFAULT_INACTIVE_THRESHOLD,
    DEFAULT_OUTLIER_SIGMA,
    DoseResponseConfig,
)
from cellar.domain.screening_assay.enums import (
    CurveType,
    HillSlopeConstraint,
    NormalizationScope,
)
from cellar.domain.shared.errors import ValidationError


def _full_dict() -> dict:
    return {
        "curve_type": "ic50",
        "x_readout_name": "concentration",
        "y_readout_name": "% inhibition",
        "hill_slope_constraint": "positive_only",
        "activity_threshold": 30.0,
        "normalization_scope": "per_run",
        "top_constraint_min": 85.0,
        "top_constraint_max": 110.0,
        "bottom_constraint_min": -10.0,
        "bottom_constraint_max": 10.0,
        "hill_slope_min": 0.9,
        "hill_slope_max": 1.1,
        "outlier_sigma": 2.5,
        "inactive_threshold": 25.0,
        "full_r2_min": 0.85,
        "full_top_min": 80.0,
        "full_bottom_max": 20.0,
        "partial_r2_min": 0.55,
    }


class TestDeserialize:
    def test_minimal_dict_uses_defaults(self):
        cfg = deserialize_dose_response_config(
            {"curve_type": "ic50", "y_readout_name": "raw AU"}
        )
        assert cfg.curve_type == CurveType.IC50
        assert cfg.y_readout_name == "raw AU"
        assert cfg.x_readout_name is None
        assert cfg.hill_slope_constraint == HillSlopeConstraint.UNCONSTRAINED
        assert cfg.normalization_scope == NormalizationScope.PER_PLATE
        assert cfg.outlier_sigma == DEFAULT_OUTLIER_SIGMA
        assert cfg.inactive_threshold == DEFAULT_INACTIVE_THRESHOLD
        assert cfg.full_r2_min == DEFAULT_FULL_R2_MIN

    def test_full_dict_round_trips_through_serialize(self):
        original = _full_dict()
        cfg = deserialize_dose_response_config(original)
        round_tripped = serialize_dose_response_config(cfg)
        assert round_tripped["curve_type"] == "ic50"
        assert round_tripped["hill_slope_constraint"] == "positive_only"
        assert round_tripped["top_constraint_min"] == 85.0
        # Re-deserializing should be identity.
        again = deserialize_dose_response_config(round_tripped)
        assert again == cfg

    def test_invalid_dict_raises_validation_error(self):
        bad = {
            "curve_type": "ic50",
            "y_readout_name": "y",
            "top_constraint": 50.0,
            "top_constraint_min": 30.0,
        }
        with pytest.raises(ValidationError, match="top_constraint"):
            deserialize_dose_response_config(bad)


class TestSerialize:
    def test_enum_values_emitted_as_strings(self):
        cfg = DoseResponseConfig(
            curve_type=CurveType.EC50,
            y_readout_name="response",
            hill_slope_constraint=HillSlopeConstraint.POSITIVE_ONLY,
            normalization_scope=NormalizationScope.PER_RUN,
        )
        out = serialize_dose_response_config(cfg)
        assert out["curve_type"] == "ec50"
        assert out["hill_slope_constraint"] == "positive_only"
        assert out["normalization_scope"] == "per_run"
