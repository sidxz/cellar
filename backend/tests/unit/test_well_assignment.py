"""Unit tests for the WellAssignment value object."""

import uuid

import pytest

from cellar.domain.inventory.well_assignment import WellAssignment
from cellar.domain.shared.enums import ConcentrationUnit, WellType
from cellar.domain.shared.errors import ValidationError
from cellar.domain.shared.value_objects import Concentration


class TestFromDict:
    def test_full_entry(self):
        bid = uuid.uuid4()
        wa = WellAssignment.from_dict(
            {
                "batch_id": str(bid),
                "concentration_value": 10.0,
                "concentration_unit": "uM",
                "well_type": "positive_control",
            }
        )
        assert wa.batch_id == bid
        assert wa.concentration == Concentration(value=10.0, unit=ConcentrationUnit.UM)
        assert wa.well_type == WellType.POSITIVE_CONTROL

    def test_defaults_role_to_sample(self):
        wa = WellAssignment.from_dict({"batch_id": str(uuid.uuid4())})
        assert wa.well_type == WellType.SAMPLE

    def test_empty_well(self):
        wa = WellAssignment.from_dict({})
        assert wa.batch_id is None
        assert wa.concentration is None
        assert wa.well_type == WellType.SAMPLE

    def test_zero_concentration_is_none(self):
        # Concentration requires > 0; a 0 value means "no concentration".
        wa = WellAssignment.from_dict({"concentration_value": 0, "concentration_unit": "mM"})
        assert wa.concentration is None

    def test_missing_unit_is_none(self):
        wa = WellAssignment.from_dict({"concentration_value": 5.0})
        assert wa.concentration is None

    def test_preserves_cdd_unresolved(self):
        wa = WellAssignment.from_dict({"batch_id": None, "cdd_batch_id_unresolved": 12345})
        assert wa.batch_id is None
        assert wa.cdd_batch_id_unresolved == 12345

    def test_rejects_invalid_unit(self):
        with pytest.raises(ValidationError, match="unit"):
            WellAssignment.from_dict({"concentration_value": 1.0, "concentration_unit": "molar"})

    def test_rejects_invalid_role(self):
        with pytest.raises(ValidationError, match="well_type"):
            WellAssignment.from_dict({"well_type": "bogus"})

    def test_rejects_non_uuid_batch(self):
        with pytest.raises(ValidationError, match="batch_id"):
            WellAssignment.from_dict({"batch_id": "CC-000001-001"})


class TestToDict:
    def test_round_trip(self):
        bid = uuid.uuid4()
        original = {
            "batch_id": str(bid),
            "concentration_value": 2.5,
            "concentration_unit": "nM",
            "well_type": "negative_control",
        }
        assert WellAssignment.from_dict(original).to_dict() == original

    def test_empty_well_flat_keys(self):
        assert WellAssignment().to_dict() == {
            "batch_id": None,
            "concentration_value": None,
            "concentration_unit": None,
            "well_type": "sample",
        }

    def test_cdd_unresolved_round_trips(self):
        wa = WellAssignment.from_dict({"cdd_batch_id_unresolved": 999})
        assert wa.to_dict()["cdd_batch_id_unresolved"] == 999


class TestValueSemantics:
    def test_is_hashable(self):
        # Frozen VOs are hashable — usable as set members / dict values.
        wa = WellAssignment(batch_id=uuid.uuid4())
        assert isinstance(hash(wa), int)

    def test_equality_by_value(self):
        bid = uuid.uuid4()
        assert WellAssignment(batch_id=bid) == WellAssignment(batch_id=bid)
