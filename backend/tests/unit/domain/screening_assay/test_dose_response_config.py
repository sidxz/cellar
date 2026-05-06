"""Tests for DoseResponseConfig value object."""

import pytest

from chem_vault.domain.screening_assay.dose_response_config import DoseResponseConfig
from chem_vault.domain.screening_assay.enums import (
    CurveType,
    HillSlopeConstraint,
    NormalizationScope,
)
from chem_vault.domain.shared.errors import ValidationError


class TestDoseResponseConfig:
    """DoseResponseConfig value object invariants."""

    def test_valid_config(self):
        cfg = DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="concentration",
            y_readout_name="% inhibition",
        )
        assert cfg.curve_type == CurveType.IC50
        assert cfg.x_readout_name == "concentration"
        assert cfg.y_readout_name == "% inhibition"
        assert cfg.hill_slope_constraint == HillSlopeConstraint.UNCONSTRAINED
        assert cfg.normalization_scope == NormalizationScope.PER_PLATE
        assert cfg.activity_threshold is None
        assert cfg.top_constraint is None
        assert cfg.bottom_constraint is None

    def test_full_config(self):
        cfg = DoseResponseConfig(
            curve_type=CurveType.EC50,
            x_readout_name="conc",
            y_readout_name="response",
            hill_slope_constraint=HillSlopeConstraint.POSITIVE_ONLY,
            activity_threshold=30.0,
            normalization_scope=NormalizationScope.PER_RUN,
            top_constraint=100.0,
            bottom_constraint=0.0,
        )
        assert cfg.hill_slope_constraint == HillSlopeConstraint.POSITIVE_ONLY
        assert cfg.activity_threshold == 30.0
        assert cfg.normalization_scope == NormalizationScope.PER_RUN
        assert cfg.top_constraint == 100.0
        assert cfg.bottom_constraint == 0.0

    def test_frozen(self):
        cfg = DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="conc",
            y_readout_name="response",
        )
        with pytest.raises(AttributeError):
            cfg.curve_type = CurveType.EC50  # type: ignore[misc]

    def test_empty_x_readout_name_raises(self):
        with pytest.raises(ValidationError, match="x_readout_name"):
            DoseResponseConfig(
                curve_type=CurveType.IC50,
                x_readout_name="",
                y_readout_name="response",
            )

    def test_empty_y_readout_name_raises(self):
        with pytest.raises(ValidationError, match="y_readout_name"):
            DoseResponseConfig(
                curve_type=CurveType.IC50,
                x_readout_name="conc",
                y_readout_name="  ",
            )

    def test_same_x_y_names_raises(self):
        with pytest.raises(ValidationError, match="must be different"):
            DoseResponseConfig(
                curve_type=CurveType.IC50,
                x_readout_name="conc",
                y_readout_name="conc",
            )

    def test_activity_threshold_below_zero_raises(self):
        with pytest.raises(ValidationError, match="activity_threshold"):
            DoseResponseConfig(
                curve_type=CurveType.IC50,
                x_readout_name="conc",
                y_readout_name="response",
                activity_threshold=-1.0,
            )

    def test_activity_threshold_above_100_raises(self):
        with pytest.raises(ValidationError, match="activity_threshold"):
            DoseResponseConfig(
                curve_type=CurveType.IC50,
                x_readout_name="conc",
                y_readout_name="response",
                activity_threshold=101.0,
            )

    def test_top_not_greater_than_bottom_raises(self):
        with pytest.raises(ValidationError, match="top_constraint"):
            DoseResponseConfig(
                curve_type=CurveType.IC50,
                x_readout_name="conc",
                y_readout_name="response",
                top_constraint=50.0,
                bottom_constraint=50.0,
            )

    def test_x_readout_name_none_is_valid(self):
        """None x_readout_name means 'use the well's concentration as X'."""
        cfg = DoseResponseConfig(
            curve_type=CurveType.IC50,
            y_readout_name="response",
        )
        assert cfg.x_readout_name is None

    def test_x_readout_name_none_does_not_collide_with_y(self):
        cfg = DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name=None,
            y_readout_name="response",
        )
        assert cfg.x_readout_name is None

    def test_equality(self):
        cfg1 = DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="conc",
            y_readout_name="response",
        )
        cfg2 = DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="conc",
            y_readout_name="response",
        )
        assert cfg1 == cfg2
