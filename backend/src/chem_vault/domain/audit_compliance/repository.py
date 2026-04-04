"""Audit repository protocol — append-only, no update or delete."""

from __future__ import annotations

import uuid
from typing import Protocol

from chem_vault.domain.audit_compliance.models import AuditOperation


class AuditRepository(Protocol):
    """Append-only repository for audit operations.

    No update() or delete() — 21 CFR Part 11 compliance.
    """

    async def save(self, operation: AuditOperation) -> None:
        """Persist an audit operation with its entries and optional signature."""
        ...

    async def find_by_id(self, id: uuid.UUID) -> AuditOperation | None:
        """Retrieve an audit operation by ID."""
        ...

    async def find_by_entity(
        self, entity_type: str, entity_id: uuid.UUID
    ) -> list[AuditOperation]:
        """Retrieve all audit operations for a given entity."""
        ...
