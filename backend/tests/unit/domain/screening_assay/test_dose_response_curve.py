"""Tests for DoseResponseCurve entity."""

import uuid

import pytest

from chem_vault.domain.screening_assay.dose_response_curve import DoseResponseCurve
from chem_vault.domain.screening_assay.enums import CurveClass, CurveType
from chem_vault.domain.shared.errors import ValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_curve(**kwargs) -> DoseResponseCurve:
    defaults = dict(
        workspace_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
        batch_id=uuid.uuid4(),
        protocol_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        curve_type=CurveType.IC50,
        fitted_value=5.2,
        fitted_unit="nM",
        hill_slope=-1.0,
        top=100.0,
        bottom=0.0,
        r_squared=0.98,
        num_points=8,
        raw_data=[{"conc": 0.1, "response": 95.0}, {"conc": 100.0, "response": 5.0}],
    )
    defaults.update(kwargs)
    return DoseResponseCurve(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDoseResponseCurve:
    def test_create_with_all_fields(self) -> None:
        curve = _make_curve(
            curve_class=CurveClass.FULL,
            confidence_interval_low=3.1,
            confidence_interval_high=7.8,
            excluded_points=[{"conc": 50.0, "response": -5.0}],
        )

        assert curve.curve_type == CurveType.IC50
        assert curve.fitted_value == 5.2
        assert curve.fitted_unit == "nM"
        assert curve.hill_slope == -1.0
        assert curve.top == 100.0
        assert curve.bottom == 0.0
        assert curve.r_squared == 0.98
        assert curve.num_points == 8
        assert curve.curve_class == CurveClass.FULL
        assert curve.confidence_interval_low == 3.1
        assert curve.confidence_interval_high == 7.8
        assert len(curve.raw_data) == 2
        assert len(curve.excluded_points) == 1

    def test_num_points_zero_raises(self) -> None:
        with pytest.raises(ValidationError, match="num_points must be >= 1"):
            _make_curve(num_points=0)

    def test_num_points_negative_raises(self) -> None:
        with pytest.raises(ValidationError, match="num_points must be >= 1"):
            _make_curve(num_points=-1)

    def test_r_squared_below_zero_raises(self) -> None:
        with pytest.raises(ValidationError, match="r_squared must be in"):
            _make_curve(r_squared=-0.01)

    def test_r_squared_above_one_raises(self) -> None:
        with pytest.raises(ValidationError, match="r_squared must be in"):
            _make_curve(r_squared=1.01)

    def test_r_squared_zero_ok(self) -> None:
        curve = _make_curve(r_squared=0.0)
        assert curve.r_squared == 0.0

    def test_r_squared_one_ok(self) -> None:
        curve = _make_curve(r_squared=1.0)
        assert curve.r_squared == 1.0

    def test_num_points_one_ok(self) -> None:
        curve = _make_curve(num_points=1)
        assert curve.num_points == 1

    def test_raw_data_defaults_to_empty_list(self) -> None:
        curve = _make_curve(raw_data=None)
        assert curve.raw_data == []

    def test_excluded_points_none_by_default(self) -> None:
        curve = _make_curve()
        assert curve.excluded_points is None

    def test_all_curve_types(self) -> None:
        for ct in CurveType:
            curve = _make_curve(curve_type=ct)
            assert curve.curve_type == ct

    def test_all_curve_classes(self) -> None:
        for cc in CurveClass:
            curve = _make_curve(curve_class=cc)
            assert curve.curve_class == cc
