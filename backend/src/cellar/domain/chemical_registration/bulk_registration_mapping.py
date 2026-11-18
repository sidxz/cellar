"""BulkRegistrationMapping — a saved "Match columns" choice, reused when a file's
headers match it (e.g. a lab's regular CDD export).

Workspace-scoped. ``columns`` is the ``ColumnMapping.to_dict()["columns"]`` list;
the application layer validates it before it reaches the entity.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from cellar.domain.shared.entity import Entity
from cellar.domain.shared.errors import ValidationError


class BulkRegistrationMapping(Entity):
    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        name: str,
        columns: list[dict[str, Any]],
        created_by: uuid.UUID,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)
        self.workspace_id = workspace_id
        self.name = self._valid_name(name)
        self.columns = list(columns)
        self.created_by = created_by

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        name: str,
        columns: list[dict[str, Any]],
        created_by: uuid.UUID,
    ) -> BulkRegistrationMapping:
        return cls(workspace_id=workspace_id, name=name, columns=columns, created_by=created_by)

    def update(
        self, *, name: str | None = None, columns: list[dict[str, Any]] | None = None
    ) -> None:
        if name is not None:
            self.name = self._valid_name(name)
        if columns is not None:
            self.columns = list(columns)
        self.updated_at = datetime.now(UTC)

    @staticmethod
    def _valid_name(name: str) -> str:
        if not name or not name.strip():
            raise ValidationError("A saved mapping needs a name")
        return name.strip()
