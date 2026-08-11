"""Read-model protocol for cross-aggregate plate queries.

The concrete implementation lives in
``infrastructure.persistence.sqlalchemy.inventory.plate_read_model_reader``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class MoleculePlateEntry:
    """Denormalized DTO for molecule → plates lookup."""

    plate_id: uuid.UUID
    barcode: str
    plate_label: str
    well_position: str
    concentration_value: float | None
    concentration_unit: str | None
    plate_type: str
    status: str
    storage_location_name: str | None


@runtime_checkable
class PlateReadModelService(Protocol):
    """Application-layer protocol for cross-aggregate plate queries."""

    async def find_plates_for_molecule(
        self,
        workspace_id: uuid.UUID,
        molecule_id: uuid.UUID,
        excluded_org_ids: set[uuid.UUID] | None = None,
    ) -> list[MoleculePlateEntry]: ...
