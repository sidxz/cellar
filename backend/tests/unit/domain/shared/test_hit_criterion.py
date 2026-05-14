"""Unit tests for HitCriterion + InterceptKey value objects."""

from __future__ import annotations

import pytest

from cellar.domain.shared.errors import ValidationError
from cellar.domain.shared.hit_criterion import HitCriterion, InterceptKey


class TestInterceptKey:
    def test_construct_with_kind_and_level(self) -> None:
        key = InterceptKey(kind="ec", level=50.0)
        assert key.kind == "ec"
        assert key.level == 50.0

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
    def test_intercept_key_defaults_to_none(self) -> None:
        crit = HitCriterion(readout_name="Resazurin", operator="lt", value=10.0)
        assert crit.intercept_key is None

    def test_intercept_key_can_be_set_explicitly(self) -> None:
        key = InterceptKey(kind="ec", level=90.0)
        crit = HitCriterion(
            readout_name="Resazurin",
            operator="lt",
            value=10.0,
            intercept_key=key,
        )
        assert crit.intercept_key == key

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
