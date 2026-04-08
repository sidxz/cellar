"""RegisteredPlate aggregate root — a physical microplate in the inventory."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from chem_vault.domain.inventory.enums import (
    VALID_PLATE_TRANSITIONS,
    PlateStatus,
    PlateType,
)
from chem_vault.domain.inventory.events import (
    PlateDisposed,
    PlateMoved,
    PlateRegistered,
    PlateStatusChanged,
    PlateWellsMapped,
)
from chem_vault.domain.screening_assay.enums import PlateFormat
from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.shared.value_objects import Barcode

# ---------------------------------------------------------------------------
# Well position validation helpers
# ---------------------------------------------------------------------------

# Maps format -> (max_row_letter_or_letters, max_col_int)
# Rows are alphabetical: A=1, B=2, ... Z=26, AA=27, AB=28, ...
_FORMAT_BOUNDS: dict[PlateFormat, tuple[str, int]] = {
    PlateFormat.F6: ("B", 3),
    PlateFormat.F12: ("C", 4),
    PlateFormat.F24: ("D", 6),
    PlateFormat.F48: ("F", 8),
    PlateFormat.F96: ("H", 12),
    PlateFormat.F384: ("P", 24),
    PlateFormat.F1536: ("AF", 48),
}

_WELL_RE = re.compile(r"^([A-Z]{1,2})(\d+)$")


def _row_to_int(row: str) -> int:
    """Convert row letters to a 1-based integer (A=1, Z=26, AA=27, AF=32)."""
    result = 0
    for ch in row:
        result = result * 26 + (ord(ch) - ord("A") + 1)
    return result


def _validate_well_position(position: str, fmt: PlateFormat) -> None:
    """Raise ValidationError if *position* is out of bounds for *fmt*."""
    m = _WELL_RE.match(position)
    if not m:
        raise ValidationError(f"Invalid well position '{position}': expected format like A1, P24, AF48")
    row_str, col_str = m.group(1), m.group(2)
    max_row, max_col = _FORMAT_BOUNDS[fmt]
    if _row_to_int(row_str) > _row_to_int(max_row):
        raise ValidationError(
            f"Invalid well position '{position}': row '{row_str}' exceeds max row '{max_row}' for {fmt}-well plate"
        )
    if int(col_str) > max_col or int(col_str) < 1:
        raise ValidationError(
            f"Invalid well position '{position}': column {col_str} out of range [1, {max_col}] for {fmt}-well plate"
        )


# ---------------------------------------------------------------------------
# Aggregate root
# ---------------------------------------------------------------------------


class RegisteredPlate(AggregateRoot):
    """A physical microplate registered in the inventory.

    Invariants:
        - plate_label is non-empty (after stripping whitespace)
        - status transitions follow VALID_PLATE_TRANSITIONS
        - well positions must be within bounds for the declared format
        - format cannot be changed once wells are mapped
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        barcode: Barcode,
        plate_label: str,
        format: PlateFormat,
        plate_type: PlateType,
        registered_by: uuid.UUID,
        status: PlateStatus = PlateStatus.REGISTERED,
        well_map: dict[str, Any] | None = None,
        storage_location_id: uuid.UUID | None = None,
        parent_plate_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        template_id: uuid.UUID | None = None,
        notes: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)

        if not plate_label or not plate_label.strip():
            raise ValidationError("plate_label (label) must not be empty")

        self.workspace_id = workspace_id
        self.barcode = barcode
        self.plate_label = plate_label.strip()
        self.format = format
        self.plate_type = plate_type
        self.registered_by = registered_by
        self.status = status
        self.well_map: dict[str, Any] = well_map if well_map is not None else {}
        self.storage_location_id = storage_location_id
        self.parent_plate_id = parent_plate_id
        self.project_id = project_id
        self.template_id = template_id
        self.notes = notes

    # ------------------------------------------------------------------
    # Factory method
    # ------------------------------------------------------------------

    @classmethod
    def register(
        cls,
        *,
        workspace_id: uuid.UUID,
        barcode: Barcode,
        plate_label: str,
        format: PlateFormat,
        plate_type: PlateType,
        registered_by: uuid.UUID,
        storage_location_id: uuid.UUID | None = None,
        parent_plate_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        template_id: uuid.UUID | None = None,
        notes: str | None = None,
    ) -> RegisteredPlate:
        """Register a new physical plate in the inventory."""
        plate = cls(
            workspace_id=workspace_id,
            barcode=barcode,
            plate_label=plate_label,
            format=format,
            plate_type=plate_type,
            registered_by=registered_by,
            storage_location_id=storage_location_id,
            parent_plate_id=parent_plate_id,
            project_id=project_id,
            template_id=template_id,
            notes=notes,
        )
        plate.register_event(
            PlateRegistered(
                aggregate_id=plate.id,
                aggregate_type="RegisteredPlate",
                barcode=barcode.value,
                format=format.value,
                plate_type=plate_type.value,
                registered_by=registered_by,
            )
        )
        return plate

    # ------------------------------------------------------------------
    # Well mapping
    # ------------------------------------------------------------------

    def map_wells(self, well_map: dict[str, Any]) -> None:
        """Assign batch/concentration data to individual wells.

        *well_map* is keyed by position string (e.g. "A1") and each value is a
        dict with at minimum ``batch_id``, ``concentration_value``, and
        ``concentration_unit``.
        """
        for position in well_map:
            _validate_well_position(position, self.format)

        self.well_map = dict(well_map)
        self.updated_at = datetime.now(UTC)

        batch_ids: list[uuid.UUID] = []
        for well_data in well_map.values():
            raw = well_data.get("batch_id")
            if raw:
                try:
                    batch_ids.append(uuid.UUID(str(raw)))
                except (ValueError, AttributeError):
                    pass

        self.register_event(
            PlateWellsMapped(
                aggregate_id=self.id,
                aggregate_type="RegisteredPlate",
                well_count=len(well_map),
                batch_ids=batch_ids,
            )
        )

    # ------------------------------------------------------------------
    # Status transitions
    # ------------------------------------------------------------------

    def transition_status(self, new_status: PlateStatus) -> None:
        """Move to *new_status* if the transition is valid."""
        allowed = VALID_PLATE_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValidationError(
                f"Invalid plate status transition from '{self.status}' to '{new_status}'"
            )
        old_status = self.status
        self.status = new_status
        self.updated_at = datetime.now(UTC)
        self.register_event(
            PlateStatusChanged(
                aggregate_id=self.id,
                aggregate_type="RegisteredPlate",
                old_status=old_status.value,
                new_status=new_status.value,
            )
        )

    def dispose(self) -> None:
        """Convenience method — transitions to DISPOSED and emits PlateDisposed."""
        self.transition_status(PlateStatus.DISPOSED)
        self.register_event(
            PlateDisposed(
                aggregate_id=self.id,
                aggregate_type="RegisteredPlate",
                barcode=self.barcode.value,
            )
        )

    # ------------------------------------------------------------------
    # Move
    # ------------------------------------------------------------------

    def move(self, new_location_id: uuid.UUID | None) -> None:
        """Update storage location and emit PlateMoved."""
        old_location_id = self.storage_location_id
        self.storage_location_id = new_location_id
        self.updated_at = datetime.now(UTC)
        self.register_event(
            PlateMoved(
                aggregate_id=self.id,
                aggregate_type="RegisteredPlate",
                old_location_id=old_location_id,
                new_location_id=new_location_id,
            )
        )

    # ------------------------------------------------------------------
    # Derive (copy to child plate)
    # ------------------------------------------------------------------

    def derive(
        self,
        *,
        barcode: Barcode,
        plate_label: str,
        plate_type: PlateType,
        registered_by: uuid.UUID,
        storage_location_id: uuid.UUID | None = None,
    ) -> RegisteredPlate:
        """Create a child plate derived from this one, copying the well map."""
        child = RegisteredPlate.register(
            workspace_id=self.workspace_id,
            barcode=barcode,
            plate_label=plate_label,
            format=self.format,
            plate_type=plate_type,
            registered_by=registered_by,
            parent_plate_id=self.id,
            storage_location_id=storage_location_id,
        )
        if self.well_map:
            child.map_wells(dict(self.well_map))
        return child

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------

    def update(
        self,
        *,
        plate_label: str | None = None,
        format: PlateFormat | None = ...,  # type: ignore[assignment]
        plate_type: PlateType | None = None,
        project_id: uuid.UUID | None = ...,  # type: ignore[assignment]
        storage_location_id: uuid.UUID | None = ...,  # type: ignore[assignment]
        template_id: uuid.UUID | None = ...,  # type: ignore[assignment]
        notes: str | None = ...,  # type: ignore[assignment]
        custom_fields: dict[str, Any] | None = ...,  # type: ignore[assignment]
    ) -> None:
        """Update mutable fields. Uses sentinel ``...`` for optional nullable fields."""
        if format is not ...:
            if format is not None and self.well_map:
                raise ValidationError(
                    "Cannot change plate format once wells have been mapped"
                )
            if format is not None:
                self.format = format
        if plate_label is not None:
            if not plate_label.strip():
                raise ValidationError("plate_label (label) must not be empty")
            self.plate_label = plate_label.strip()
        if plate_type is not None:
            self.plate_type = plate_type
        if project_id is not ...:
            self.project_id = project_id
        if storage_location_id is not ...:
            self.storage_location_id = storage_location_id
        if template_id is not ...:
            self.template_id = template_id
        if notes is not ...:
            self.notes = notes
        if custom_fields is not ...:
            self.custom_fields = custom_fields
        self.updated_at = datetime.now(UTC)
