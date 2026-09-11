"""Unit tests for HitCriterion + InterceptKey value objects."""

from __future__ import annotations

import pytest

from cellar.domain.shared.errors import ValidationError
from cellar.domain.shared.hit_criterion import HitCriterion, InterceptKey, compare


class TestInterceptKey:

    def test_is_frozen(self) -> None:
        key = InterceptKey(kind="ec", level=50.0)
        with pytest.raises(Exception):
            key.kind = "ic"  # type: ignore[misc]

    def test_value_equality(self) -> None:
        assert InterceptKey(kind="ec", level=90.0) == InterceptKey(kind="ec", level=90.0)
        assert InterceptKey(kind="ec", level=50.0) != InterceptKey(kind="ic", level=50.0)
        assert InterceptKey(kind="ec", level=50.0) != InterceptKey(kind="ec", level=90.0)

    @pytest.mark.parametrize("kind", ["ec", "ic"])
    def test_accepts_valid_kinds(self, kind: str) -> None:
        InterceptKey(kind=kind, level=50.0)  # no raise

    @pytest.mark.parametrize("bad_kind", ["EC", "ec50", "", "kd", "potency"])
    def test_rejects_invalid_kind(self, bad_kind: str) -> None:
        with pytest.raises(ValidationError):
            InterceptKey(kind=bad_kind, level=50.0)

    @pytest.mark.parametrize("bad_level", [0, 0.0, 100, 100.0, -10, 150])
    def test_rejects_out_of_range_level(self, bad_level: float) -> None:
        with pytest.raises(ValidationError):
            InterceptKey(kind="ec", level=bad_level)

    def test_to_dict_round_trip(self) -> None:
        key = InterceptKey(kind="ic", level=90.0)
        assert key.to_dict() == {"kind": "ic", "level": 90.0}
        assert InterceptKey.from_dict({"kind": "ic", "level": 90.0}) == key


class TestHitCriterionInterceptKey:


    def test_to_dict_emits_intercept_key_when_set(self) -> None:
        crit = HitCriterion(
            readout_name="Resazurin",
            operator="lt",
            value=10.0,
            intercept_key=InterceptKey(kind="ec", level=90.0),
        )
        d = crit.to_dict()
        assert d == {
            "readout_name": "Resazurin",
            "operator": "lt",
            "value": 10.0,
            "intercept_key": {"kind": "ec", "level": 90.0},
        }

    def test_to_dict_omits_intercept_key_when_none(self) -> None:
        crit = HitCriterion(readout_name="Resazurin", operator="lt", value=10.0)
        d = crit.to_dict()
        assert "intercept_key" not in d
        assert d == {"readout_name": "Resazurin", "operator": "lt", "value": 10.0}

    def test_from_dict_reads_intercept_key(self) -> None:
        crit = HitCriterion.from_dict(
            {
                "readout_name": "Resazurin",
                "operator": "lt",
                "value": 10.0,
                "intercept_key": {"kind": "ec", "level": 90.0},
            }
        )
        assert crit.intercept_key == InterceptKey(kind="ec", level=90.0)

    def test_from_dict_legacy_row_has_none_intercept_key(self) -> None:
        crit = HitCriterion.from_dict(
            {"readout_name": "IC50", "operator": "lt", "value": 1000.0}
        )
        assert crit.intercept_key is None

    def test_full_round_trip_preserves_intercept_key(self) -> None:
        original = HitCriterion(
            readout_name="Resazurin",
            operator="between",
            value=[10.0, 100.0],
            intercept_key=InterceptKey(kind="ic", level=50.0),
        )
        restored = HitCriterion.from_dict(original.to_dict())
        assert restored == original


class TestCompare:
    """`compare()` is the one shared numeric-comparison implementation used
    by both HitCriterion.is_met and StageCriterion.is_met."""

    def test_lt(self) -> None:
        assert compare("lt", 5.0, 10.0) is True
        assert compare("lt", 10.0, 10.0) is False
        assert compare("lt", 15.0, 10.0) is False

    def test_lte_boundary_equality(self) -> None:
        assert compare("lte", 5.0, 10.0) is True
        assert compare("lte", 10.0, 10.0) is True
        assert compare("lte", 15.0, 10.0) is False

    def test_gt(self) -> None:
        assert compare("gt", 15.0, 10.0) is True
        assert compare("gt", 10.0, 10.0) is False
        assert compare("gt", 5.0, 10.0) is False

    def test_gte_boundary_equality(self) -> None:
        assert compare("gte", 15.0, 10.0) is True
        assert compare("gte", 10.0, 10.0) is True
        assert compare("gte", 5.0, 10.0) is False

    def test_between_boundary_equality(self) -> None:
        assert compare("between", 10.0, [10.0, 20.0]) is True
        assert compare("between", 20.0, [10.0, 20.0]) is True
        assert compare("between", 15.0, [10.0, 20.0]) is True
        assert compare("between", 9.9, [10.0, 20.0]) is False
        assert compare("between", 20.1, [10.0, 20.0]) is False

    def test_unsupported_operator_raises(self) -> None:
        with pytest.raises(ValidationError):
            compare("in", 5.0, 10.0)
        with pytest.raises(ValidationError):
            compare("bogus", 5.0, 10.0)

    def test_is_met_returns_none_for_in_operator(self) -> None:
        crit = HitCriterion(readout_name="Purity", operator="in", value=["A", "B"])
        assert crit.is_met(5.0) is None

    def test_is_met_delegates_to_compare(self) -> None:
        crit = HitCriterion(readout_name="IC50", operator="lt", value=10.0)
        assert crit.is_met(5.0) is True
        assert crit.is_met(15.0) is False
