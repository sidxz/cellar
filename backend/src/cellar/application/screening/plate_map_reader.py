"""Read-model protocol for plate map queries.

The concrete implementation lives in
``infrastructure.persistence.sqlalchemy.screening_assay.plate_map_reader``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class WellMapEntry:
    well_id: uuid.UUID
    position: str  # e.g. "A1" — row + column with no zero-padding
    row: str
    column: int
    well_type: str
    batch_id: uuid.UUID | None = None
    batch_number: str | None = None
    molecule_id: uuid.UUID | None = None
    molecule_name: str | None = None
    # Custom-type identifiers (synonyms / common names) for the molecule.
    synonyms: tuple[str, ...] = ()
    # SMILES for the molecule, used by the well tooltip to render a
    # structure thumbnail. Sourced once per molecule, not per well.
    smiles: str | None = None
    # Dose value in the protocol's dose_unit. Unit not carried per-well.
    dose: float | None = None


@dataclass(frozen=True)
class PlateMapSummary:
    total_wells: int
    sample_wells: int
    control_wells: int
    compounds: int
    concentrations_per_compound: int
    replicates: int


@dataclass(frozen=True)
class PlateMapData:
    plate_id: uuid.UUID
    plate_number: int
    format: str
    wells: list[WellMapEntry] = field(default_factory=list)
    summary: PlateMapSummary | None = None
    # Physical inventory plate this run plate was run on — all None when unlinked.
    registered_plate_id: uuid.UUID | None = None
    registered_plate_barcode: str | None = None
    registered_plate_label: str | None = None


@dataclass(frozen=True)
class PlateMapResult:
    run_id: uuid.UUID
    # The owning protocol's dose_unit — caller resolves it once and propagates
    # to UI consumers (plate map, readout-data table, dose-response chart).
    dose_unit: str
    plates: list[PlateMapData]


@runtime_checkable
class PlateMapReader(Protocol):
    """Application-layer protocol for plate map read-model queries."""

    async def get_plate_map(
        self, workspace_id: uuid.UUID, run_id: uuid.UUID
    ) -> PlateMapResult | None: ...
