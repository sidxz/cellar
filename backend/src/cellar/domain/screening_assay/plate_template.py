"""PlateTemplate entity — reusable plate layout definition."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from cellar.domain.screening_assay.enums import PlateFormat
from cellar.domain.shared.entity import Entity
from cellar.domain.shared.errors import ValidationError

# Sentinel value for distinguishing "not provided" from "explicitly None"
_UNSET = object()


class PlateTemplate(Entity):
    """A reusable plate layout template defining well assignments.

    Reference entity — describes default well assignments for a plate format.

    Invariants:
        - name cannot be empty
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        name: str,
        format: PlateFormat,
        template_map: dict[str, Any],
        description: str | None = None,
        created_by: uuid.UUID,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)

        if not name or not name.strip():
            raise ValidationError("PlateTemplate name must not be empty")

        self.workspace_id = workspace_id
        self.name = name.strip()
        self.format = format
        self.template_map = template_map
        self.description = description
        self.created_by = created_by

    # ------------------------------------------------------------------
    # Factory method
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        name: str,
        format: PlateFormat,
        template_map: dict[str, Any],
        description: str | None = None,
        created_by: uuid.UUID,
    ) -> PlateTemplate:
        return cls(
            workspace_id=workspace_id,
            name=name,
            format=format,
            template_map=template_map,
            description=description,
            created_by=created_by,
        )

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def update(
        self,
        *,
        name: str | None = None,
        format: PlateFormat | None = None,
        template_map: dict[str, Any] | None = None,
        description: str | None = _UNSET,  # type: ignore[assignment]
    ) -> None:
        """Update mutable fields. Pass ``None`` for description to clear it."""
        if name is not None:
            if not name.strip():
                raise ValidationError("PlateTemplate name must not be empty")
            self.name = name.strip()
        if format is not None:
            self.format = format
        if template_map is not None:
            self.template_map = template_map
        if description is not _UNSET:
            self.description = description
        self.updated_at = datetime.now(UTC)
