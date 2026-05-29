"""CollectionImportTemplate — reusable column mapping for collection CSV imports.

Workspace-scoped. Stores which CSV header maps to which role
(registration_number / external_id / smiles / inchi_key / name / notes).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from cellar.domain.shared.entity import Entity
from cellar.domain.shared.errors import ValidationError

_UNSET: Any = object()

_IDENTIFIER_ROLES = frozenset(
    {"registration_number", "external_id", "inchi_key", "smiles", "name"}
)


class CollectionImportTemplate(Entity):
    """Saved column mapping for bulk-adding molecules to a collection."""

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        name: str,
        description: str | None = None,
        column_mapping: dict[str, str],
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
        self.created_by = created_by

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        name: str,
        column_mapping: dict[str, str],
        description: str | None = None,
        created_by: uuid.UUID,
    ) -> CollectionImportTemplate:
        return cls(
            workspace_id=workspace_id,
            name=name,
            description=description,
            column_mapping=column_mapping,
            created_by=created_by,
        )

    def update(
        self,
        *,
        name: str | None = None,
        description: Any = _UNSET,
        column_mapping: dict[str, str] | None = None,
    ) -> None:
        if name is not None:
            self._validate_name(name)
            self.name = name.strip()
        if description is not _UNSET:
            self.description = description
        if column_mapping is not None:
            self._validate_mapping(column_mapping)
            self.column_mapping = column_mapping
        self.updated_at = datetime.now(UTC)

    @staticmethod
    def _validate_name(name: str) -> None:
        if not name or not name.strip():
            raise ValidationError("CollectionImportTemplate name must not be empty")

    @staticmethod
    def _validate_mapping(mapping: dict[str, str]) -> None:
        if not any(role in mapping and mapping[role] for role in _IDENTIFIER_ROLES):
            raise ValidationError(
                "column_mapping must declare at least one identifier role "
                "(registration_number, external_id, inchi_key, smiles, or name)"
            )
