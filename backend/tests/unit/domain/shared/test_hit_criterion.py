"""Unit tests for HitCriterion + InterceptKey value objects."""

from __future__ import annotations

import pytest

from cellar.domain.shared.aggregation_types import ValueQualifier
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


class TestCompareCensored:
    """A censored value passes only when every value it could be meets the
    criterion. ">50" is somewhere above 50, "<5" somewhere below 5."""

    @pytest.mark.parametrize(
        ("operator", "value", "qualifier", "target", "expected"),
        [
            # ">50": an inactive at a 50 uM top dose.
            ("lt", 50.0, ValueQualifier.GT, 60.0, False),
            ("lte", 50.0, ValueQualifier.GT, 50.0, False),
            ("gt", 50.0, ValueQualifier.GT, 10.0, True),
            ("gt", 50.0, ValueQualifier.GT, 50.0, True),
            ("gte", 50.0, ValueQualifier.GT, 50.0, True),
            ("gt", 50.0, ValueQualifier.GT, 60.0, False),
            ("between", 50.0, ValueQualifier.GT, [10.0, 100.0], False),
            # "<5": potent past the bottom dose.
            ("lt", 5.0, ValueQualifier.LT, 10.0, True),
            ("lt", 5.0, ValueQualifier.LT, 5.0, True),
            ("lte", 5.0, ValueQualifier.LT, 5.0, True),
            ("lt", 5.0, ValueQualifier.LT, 1.0, False),
            ("gt", 5.0, ValueQualifier.LT, 1.0, False),
            ("between", 5.0, ValueQualifier.LT, [0.0, 10.0], False),
        ],
    )
    def test_censored(self, operator, value, qualifier, target, expected) -> None:
        assert compare(operator, value, target, qualifier) is expected

    def test_is_met_passes_qualifier_through(self) -> None:
        crit = HitCriterion(readout_name="IC50", operator="lt", value=60.0)
        assert crit.is_met(50.0, ValueQualifier.GT) is False
