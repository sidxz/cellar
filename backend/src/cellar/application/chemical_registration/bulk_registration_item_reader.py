"""Read-model protocol for BulkRegistrationItem queries.

Concrete impl in
``infrastructure.persistence.sqlalchemy.chemical_registration.bulk_registration_item_reader``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class BulkRegistrationItemRow:
    """Per-row outcome projected for the summary results table."""

    id: uuid.UUID
    bulk_registration_id: uuid.UUID
    row_index: int
    action: str
    success: bool
    molecule_id: uuid.UUID | None
    molecule_name: str | None
    registration_number: str | None
    batch_id: uuid.UUID | None
    batch_number: str | None
    error: str | None
    created_at: datetime


@dataclass(frozen=True)
class BulkRegistrationItemPage:
    rows: list[BulkRegistrationItemRow]
    total: int


@runtime_checkable
class BulkRegistrationItemReader(Protocol):
    """Application-layer protocol for paged per-row item queries."""

    async def list_items(
        self,
        *,
        workspace_id: uuid.UUID,
        bulk_registration_id: uuid.UUID,
        action: str | None,
        limit: int,
        offset: int,
    ) -> BulkRegistrationItemPage: ...
