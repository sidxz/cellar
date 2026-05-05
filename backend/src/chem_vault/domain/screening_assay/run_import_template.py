"""RunImportTemplate — reusable column mapping for long-format run imports.

Workspace-scoped, NOT per-protocol. Captures the column→role map plus
default concentration unit. Readout-definition mappings remain per-protocol
and are not stored on the template (per plan locked decision #5).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from chem_vault.domain.shared.entity import Entity
from chem_vault.domain.shared.errors import ValidationError

_UNSET: Any = object()


class RunImportTemplate(Entity):
    """A saved column mapping for run-file imports.

    column_mapping shape:

        {
            "well": "Well",
            "plate_name": "Plate Name",
            "concentration": "Concentration",
            "batch_ref": "LGCY BATCH NAME",
            "scientist": "Scientist",
            "readout_headers": ["Raw Data"]
        }
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        name: str,
        description: str | None = None,
        column_mapping: dict[str, Any],
        concentration_unit: str = "uM",
        created_by: uuid.UUID,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)
        self._validate_name(name)
        self._validate_mapping(column_mapping)

        self.workspace_id = workspace_id
        self.name = name.strip()
        self.description = description
        self.column_mapping = column_mapping
        self.concentration_unit = concentration_unit
        self.created_by = created_by

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        name: str,
        column_mapping: dict[str, Any],
        concentration_unit: str = "uM",
        description: str | None = None,
        created_by: uuid.UUID,
    ) -> RunImportTemplate:
        return cls(
            workspace_id=workspace_id,
            name=name,
            description=description,
            column_mapping=column_mapping,
            concentration_unit=concentration_unit,
            created_by=created_by,
        )

    def update(
        self,
        *,
        name: str | None = None,
        description: Any = _UNSET,
        column_mapping: dict[str, Any] | None = None,
        concentration_unit: str | None = None,
    ) -> None:
        if name is not None:
            self._validate_name(name)
            self.name = name.strip()
        if description is not _UNSET:
            self.description = description
        if column_mapping is not None:
            self._validate_mapping(column_mapping)
            self.column_mapping = column_mapping
        if concentration_unit is not None:
            self.concentration_unit = concentration_unit
        self.updated_at = datetime.now(UTC)

    @staticmethod
    def _validate_name(name: str) -> None:
        if not name or not name.strip():
            raise ValidationError("RunImportTemplate name must not be empty")

    @staticmethod
    def _validate_mapping(mapping: dict[str, Any]) -> None:
        if "well" not in mapping or not mapping["well"]:
            raise ValidationError("column_mapping must declare a 'well' header")
