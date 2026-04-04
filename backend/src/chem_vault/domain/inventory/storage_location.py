"""StorageLocation entity — hierarchical physical storage for lab infrastructure."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from chem_vault.domain.inventory.enums import VALID_PARENT_TYPES, StorageLocationType
from chem_vault.domain.inventory.events import StorageLocationCreated
from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.shared.value_objects import Barcode


class StorageLocation(AggregateRoot):
    """Physical storage organized hierarchically.

    Hierarchy: Site → Building → Room → Freezer/Refrigerator → Shelf → Rack → Box/Drawer

    Invariants:
        - parent_id must reference a location of a valid parent type
        - No circular references (enforced at repository/service level)
        - Capacity must be positive if set
        - Grid dimensions (rows/columns) must be positive if set
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        name: str,
        type: StorageLocationType,
        parent_id: uuid.UUID | None = None,
        parent_type: StorageLocationType | None = None,
        barcode: Barcode | None = None,
        temperature: str | None = None,
        rows: int | None = None,
        columns: int | None = None,
        capacity: int | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)

        if not name or not name.strip():
            raise ValidationError("StorageLocation name must not be empty")
        if capacity is not None and capacity <= 0:
            raise ValidationError("Capacity must be > 0")
        if rows is not None and rows <= 0:
            raise ValidationError("Rows must be > 0")
        if columns is not None and columns <= 0:
            raise ValidationError("Columns must be > 0")

        # Validate parent type compatibility
        self._validate_parent_type(type, parent_id, parent_type)

        self.workspace_id = workspace_id
        self.name = name.strip()
        self.type = type
        self.parent_id = parent_id
        self.parent_type = parent_type
        self.barcode = barcode
        self.temperature = temperature
        self.rows = rows
        self.columns = columns
        self.capacity = capacity

    @staticmethod
    def _validate_parent_type(
        loc_type: StorageLocationType,
        parent_id: uuid.UUID | None,
        parent_type: StorageLocationType | None,
    ) -> None:
        valid_parents = VALID_PARENT_TYPES.get(loc_type, set())

        if parent_id is None:
            if None not in valid_parents:
                raise ValidationError(
                    f"StorageLocation of type '{loc_type}' requires a parent"
                )
        else:
            if parent_type not in valid_parents:
                allowed = ", ".join(str(p) for p in valid_parents if p is not None)
                raise ValidationError(
                    f"StorageLocation of type '{loc_type}' cannot have parent of "
                    f"type '{parent_type}'. Allowed: {allowed}"
                )

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        name: str,
        type: StorageLocationType,
        parent_id: uuid.UUID | None = None,
        parent_type: StorageLocationType | None = None,
        barcode: Barcode | None = None,
        temperature: str | None = None,
        rows: int | None = None,
        columns: int | None = None,
        capacity: int | None = None,
    ) -> StorageLocation:
        loc = cls(
            workspace_id=workspace_id,
            name=name,
            type=type,
            parent_id=parent_id,
            parent_type=parent_type,
            barcode=barcode,
            temperature=temperature,
            rows=rows,
            columns=columns,
            capacity=capacity,
        )
        loc.register_event(
            StorageLocationCreated(
                aggregate_id=loc.id,
                aggregate_type="StorageLocation",
                workspace_id=workspace_id,
                name=name,
                location_type=type.value,
                parent_id=parent_id,
            )
        )
        return loc

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------

    def update(
        self,
        *,
        name: str | None = None,
        barcode: Barcode | None = ...,  # type: ignore[assignment]
        temperature: str | None = ...,  # type: ignore[assignment]
        rows: int | None = ...,  # type: ignore[assignment]
        columns: int | None = ...,  # type: ignore[assignment]
        capacity: int | None = ...,  # type: ignore[assignment]
    ) -> None:
        """Update mutable fields.

        Type and parent_id are NOT updatable (structural change).
        Uses sentinel ``...`` for optional nullable fields so callers can
        explicitly pass ``None`` to clear them.
        """
        if name is not None:
            if not name.strip():
                raise ValidationError("StorageLocation name must not be empty")
            self.name = name.strip()
        if barcode is not ...:
            self.barcode = barcode
        if temperature is not ...:
            self.temperature = temperature
        if rows is not ...:
            if rows is not None and rows <= 0:
                raise ValidationError("Rows must be > 0")
            self.rows = rows
        if columns is not ...:
            if columns is not None and columns <= 0:
                raise ValidationError("Columns must be > 0")
            self.columns = columns
        if capacity is not ...:
            if capacity is not None and capacity <= 0:
                raise ValidationError("Capacity must be > 0")
            self.capacity = capacity
        self.updated_at = datetime.now(UTC)
