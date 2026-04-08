"""ImportTemplate entity — reusable column mapping for plate data imports."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from chem_vault.domain.shared.entity import Entity
from chem_vault.domain.shared.errors import ValidationError

_UNSET = object()


class ImportTemplate(Entity):
    """A saved column mapping for plate data imports.

    Simple CRUD entity — no versioning, no events.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        name: str,
        description: str | None = None,
        column_mappings: dict[str, Any],
        default_protocol_id: uuid.UUID | None = None,
        created_by: uuid.UUID,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)

        if not name or not name.strip():
            raise ValidationError("ImportTemplate name must not be empty")

        self.workspace_id = workspace_id
        self.name = name.strip()
        self.description = description
        self.column_mappings = column_mappings
        self.default_protocol_id = default_protocol_id
        self.created_by = created_by

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        name: str,
        column_mappings: dict[str, Any],
        description: str | None = None,
        default_protocol_id: uuid.UUID | None = None,
        created_by: uuid.UUID,
    ) -> ImportTemplate:
        return cls(
            workspace_id=workspace_id,
            name=name,
            column_mappings=column_mappings,
            description=description,
            default_protocol_id=default_protocol_id,
            created_by=created_by,
        )

    def update(
        self,
        *,
        name: str | None = None,
        column_mappings: dict[str, Any] | None = None,
        description: str | None = _UNSET,  # type: ignore[assignment]
        default_protocol_id: uuid.UUID | None = _UNSET,  # type: ignore[assignment]
    ) -> None:
        if name is not None:
            if not name.strip():
                raise ValidationError("ImportTemplate name must not be empty")
            self.name = name.strip()
        if column_mappings is not None:
            self.column_mappings = column_mappings
        if description is not _UNSET:
            self.description = description
        if default_protocol_id is not _UNSET:
            self.default_protocol_id = default_protocol_id
        self.updated_at = datetime.now(UTC)
