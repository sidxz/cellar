"""Integration test: RegisteredPlate well_map ↔ JSONB round-trip with roles."""

from __future__ import annotations

import uuid

import pytest

from cellar.domain.inventory.enums import PlateType
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.inventory.well_assignment import WellAssignment
from cellar.domain.shared.enums import ConcentrationUnit, PlateFormat, WellType
from cellar.domain.shared.value_objects import Barcode, Concentration
from cellar.infrastructure.persistence.sqlalchemy.inventory.registered_plate_repository import (
    SQLAlchemyRegisteredPlateRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


@pytest.mark.integration
async def test_well_map_round_trips_through_jsonb(session_factory) -> None:
    """A roled, concentrated well map survives save → reload via the JSONB column."""
    workspace_id = uuid.uuid4()
    batch_id = uuid.uuid4()

    # Write a plate with a sample well (batch + concentration) and a control well.
    uow_write = AsyncUnitOfWork(session_factory)
    async with uow_write:
        repo = SQLAlchemyRegisteredPlateRepository(uow_write)
        plate = RegisteredPlate.register(
            workspace_id=workspace_id,
            barcode=Barcode(value=f"PLT-RT-{uuid.uuid4().hex[:8]}"),
            plate_label="Round Trip",
            format=PlateFormat.F96,
            plate_type=PlateType.ASSAY,
            registered_by=uuid.uuid4(),
        )
        plate.map_wells(
            {
                "A1": WellAssignment(
                    well_type=WellType.SAMPLE,
                    batch_id=batch_id,
                    concentration=Concentration(value=10.0, unit=ConcentrationUnit.UM),
                ),
                "H12": WellAssignment(well_type=WellType.POSITIVE_CONTROL),
            }
        )
        plate_id = plate.id
        await repo.save(plate)
        await uow_write.commit()

    # Reload from a fresh unit of work — forces a real DB read, not a tracked instance.
    uow_read = AsyncUnitOfWork(session_factory)
    async with uow_read:
        repo = SQLAlchemyRegisteredPlateRepository(uow_read)
        loaded = await repo.find_by_id_in_workspace(workspace_id, plate_id)

    assert loaded is not None
    a1 = loaded.well_map["A1"]
    assert a1.well_type == WellType.SAMPLE
    assert a1.batch_id == batch_id
    assert a1.concentration == Concentration(value=10.0, unit=ConcentrationUnit.UM)

    h12 = loaded.well_map["H12"]
    assert h12.well_type == WellType.POSITIVE_CONTROL
    assert h12.batch_id is None
    assert h12.concentration is None
