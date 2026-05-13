"""Unit tests for RegisteredPlate aggregate root."""

import uuid

import pytest

from cellar.domain.inventory.enums import PlateStatus, PlateType
from cellar.domain.inventory.events import (
    PlateDisposed,
    PlateMoved,
    PlateRegistered,
    PlateStatusChanged,
    PlateWellsMapped,
)
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.screening_assay.enums import PlateFormat
from cellar.domain.shared.errors import ValidationError
from cellar.domain.shared.value_objects import Barcode


def _make_plate(**overrides):
    defaults = dict(
        workspace_id=uuid.uuid4(),
        barcode=Barcode(value="PLT-001"),
        plate_label="Test Plate",
        format=PlateFormat.F96,
        plate_type=PlateType.MOTHER,
        registered_by=uuid.uuid4(),
    )
    defaults.update(overrides)
    return RegisteredPlate.register(**defaults)


class TestRegister:
    def test_creates_with_defaults(self):
        plate = _make_plate()
        assert plate.status == PlateStatus.REGISTERED
        assert plate.well_map == {}
        assert plate.version == 1

    def test_emits_plate_registered_event(self):
        plate = _make_plate()
        events = plate.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], PlateRegistered)
        assert events[0].barcode == "PLT-001"

    def test_rejects_empty_label(self):
        with pytest.raises(ValidationError, match="label"):
            _make_plate(plate_label="")

    def test_rejects_whitespace_label(self):
        with pytest.raises(ValidationError, match="label"):
            _make_plate(plate_label="   ")


class TestMapWells:
    def test_sets_well_map(self):
        plate = _make_plate()
        batch_id = uuid.uuid4()
        well_map = {"A1": {"batch_id": str(batch_id), "concentration_value": 10.0, "concentration_unit": "mM"}}
        plate.map_wells(well_map)
        assert plate.well_map == well_map

    def test_emits_wells_mapped_event(self):
        plate = _make_plate()
        batch_id = uuid.uuid4()
        well_map = {"A1": {"batch_id": str(batch_id), "concentration_value": 10.0, "concentration_unit": "mM"}}
        plate.clear_events()
        plate.map_wells(well_map)
        events = plate.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], PlateWellsMapped)
        assert events[0].well_count == 1

    def test_rejects_invalid_position_for_format(self):
        plate = _make_plate(format=PlateFormat.F96)
        with pytest.raises(ValidationError, match="position"):
            plate.map_wells({"P24": {"batch_id": str(uuid.uuid4()), "concentration_value": 1.0, "concentration_unit": "mM"}})

    def test_accepts_valid_positions_for_384(self):
        plate = _make_plate(format=PlateFormat.F384)
        batch_id = uuid.uuid4()
        plate.map_wells({"P24": {"batch_id": str(batch_id), "concentration_value": 1.0, "concentration_unit": "mM"}})
        assert "P24" in plate.well_map


class TestStatusTransitions:
    def test_register_to_stored(self):
        plate = _make_plate()
        plate.clear_events()
        plate.transition_status(PlateStatus.STORED)
        assert plate.status == PlateStatus.STORED
        events = plate.collect_events()
        assert isinstance(events[0], PlateStatusChanged)
        assert events[0].new_status == "stored"

    def test_stored_to_in_use(self):
        plate = _make_plate()
        plate.transition_status(PlateStatus.STORED)
        plate.transition_status(PlateStatus.IN_USE)
        assert plate.status == PlateStatus.IN_USE

    def test_rejects_invalid_transition(self):
        plate = _make_plate()
        with pytest.raises(ValidationError, match="transition"):
            plate.transition_status(PlateStatus.DEPLETED)

    def test_disposed_is_terminal(self):
        plate = _make_plate()
        plate.transition_status(PlateStatus.DISPOSED)
        with pytest.raises(ValidationError, match="transition"):
            plate.transition_status(PlateStatus.STORED)


class TestDispose:
    def test_dispose_from_registered(self):
        plate = _make_plate()
        plate.clear_events()
        plate.dispose()
        assert plate.status == PlateStatus.DISPOSED
        events = plate.collect_events()
        assert any(isinstance(e, PlateDisposed) for e in events)


class TestMove:
    def test_move_to_new_location(self):
        old_loc = uuid.uuid4()
        new_loc = uuid.uuid4()
        plate = _make_plate(storage_location_id=old_loc)
        plate.clear_events()
        plate.move(new_loc)
        assert plate.storage_location_id == new_loc
        events = plate.collect_events()
        assert isinstance(events[0], PlateMoved)
        assert events[0].old_location_id == old_loc
        assert events[0].new_location_id == new_loc


class TestFormatImmutability:
    def test_cannot_change_format_with_mapped_wells(self):
        plate = _make_plate(format=PlateFormat.F96)
        plate.map_wells({"A1": {"batch_id": str(uuid.uuid4()), "concentration_value": 1.0, "concentration_unit": "mM"}})
        with pytest.raises(ValidationError, match="format"):
            plate.update(format=PlateFormat.F384)
