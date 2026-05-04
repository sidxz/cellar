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
    row: str
    column: int
    well_type: str
    batch_id: uuid.UUID | None = None
    molecule_id: uuid.UUID | None = None
    molecule_name: str | None = None
    concentration_value: float | None = None
    concentration_unit: str | None = None


@dataclass(frozen=True)
class PlateMapData:
    plate_id: uuid.UUID
    plate_number: int
    wells: list[WellMapEntry] = field(default_factory=list)


@dataclass(frozen=True)
class PlateMapResult:
    run_id: uuid.UUID
    plates: list[PlateMapData]


@runtime_checkable
class PlateMapReader(Protocol):
    """Application-layer protocol for plate map read-model queries."""

    async def get_plate_map(
        self, workspace_id: uuid.UUID, run_id: uuid.UUID
    ) -> PlateMapResult | None: ...
