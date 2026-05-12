"""Tests for the plate-map summary helper (Bug 2)."""

from __future__ import annotations

import uuid

from cellar.application.screening.plate_map_reader import WellMapEntry
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.plate_map_reader import (
    _summarize,
)


def _well(
    *,
    well_type: str = "sample",
    molecule_id: uuid.UUID | None = None,
    concentration: float | None = None,
    row: str = "A",
    column: int = 1,
) -> WellMapEntry:
    return WellMapEntry(
        well_id=uuid.uuid4(),
        position=f"{row}{column}",
        row=row,
        column=column,
        well_type=well_type,
        batch_id=uuid.uuid4() if molecule_id else None,
        batch_number="B-1" if molecule_id else None,
        molecule_id=molecule_id,
        molecule_name="Mol" if molecule_id else None,
        dose=concentration,
    )


def test_summary_zero_wells():
    s = _summarize([])
    assert s.total_wells == 0
    assert s.sample_wells == 0
    assert s.control_wells == 0
    assert s.compounds == 0
    assert s.concentrations_per_compound == 0
    assert s.replicates == 0


def test_summary_counts_samples_and_controls():
    wells = [
        _well(well_type="sample", molecule_id=uuid.UUID(int=1), concentration=10.0),
        _well(well_type="positive_control"),
        _well(well_type="negative_control"),
        _well(well_type="blank"),
    ]
    s = _summarize(wells)
    assert s.total_wells == 4
    assert s.sample_wells == 1
    assert s.control_wells == 3


def test_summary_compound_concentration_replicate_counts():
    m1 = uuid.UUID(int=1)
    m2 = uuid.UUID(int=2)
    # m1: 3 concs (1, 10, 100), 2 replicates each
    # m2: 2 concs (5, 50),       1 replicate each
    wells = [
        _well(molecule_id=m1, concentration=1.0),
        _well(molecule_id=m1, concentration=1.0),
        _well(molecule_id=m1, concentration=10.0),
        _well(molecule_id=m1, concentration=10.0),
        _well(molecule_id=m1, concentration=100.0),
        _well(molecule_id=m1, concentration=100.0),
        _well(molecule_id=m2, concentration=5.0),
        _well(molecule_id=m2, concentration=50.0),
    ]
    s = _summarize(wells)
    assert s.compounds == 2
    # max distinct concentrations across compounds
    assert s.concentrations_per_compound == 3
    # max replicate count across (compound, conc) pairs
    assert s.replicates == 2


def test_summary_ignores_sample_wells_without_molecule():
    """Unresolved batch refs leave molecule_id=None — those wells must not
    be counted as a compound."""
    wells = [
        _well(well_type="sample", molecule_id=None, concentration=10.0),
        _well(well_type="sample", molecule_id=uuid.UUID(int=1), concentration=10.0),
    ]
    s = _summarize(wells)
    assert s.compounds == 1
