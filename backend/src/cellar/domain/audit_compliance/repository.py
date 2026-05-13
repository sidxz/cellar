"""Audit repository protocol — append-only, no update or delete."""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from cellar.domain.audit_compliance.models import AuditOperation


@runtime_checkable
class AuditRepository(Protocol):
    """Append-only repository for audit operations.

    No update() or delete() — 21 CFR Part 11 compliance.
    """

    async def save(self, operation: AuditOperation) -> None:
        """Persist an audit operation with its entries and optional signature."""
        ...

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> AuditOperation | None:
        """Retrieve an audit operation by ID, scoped to workspace."""
        ...

    async def find_by_entity(
        self, workspace_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID
    ) -> list[AuditOperation]:
        """Retrieve all audit operations for a given entity within a workspace."""
        ...

    async def find_all(
        self,
        workspace_id: uuid.UUID,
        *,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
    ) -> list[AuditOperation]:
        """Retrieve audit operations with optional filters."""
        ...
