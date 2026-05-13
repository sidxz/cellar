"""Application-layer Protocol for cascade preview + execute.

Hides the SQLAlchemy session detail and the CascadeRunner concrete class
from the use case layer.  Infrastructure provides ``UoWBackedCascadeService``
as the concrete implementation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol

from cellar.domain.audit_compliance.models import AuditEntry
from cellar.domain.shared.cascade import CascadeNode


class CascadeExecutionError(Exception):
    """Raised when a BLOCK rule matched at execute time (race after preview)."""


@dataclass(frozen=True)
class InboundReference:
    """Tier-1 RESTRICT blocker — one row group referencing the parent."""

    table: str
    fk_column: str
    entity_type: str
    count: int
    samples: list[dict] = field(default_factory=list)
    truncated: bool = False


class CascadeService(Protocol):
    async def preview(
        self,
        *,
        workspace_id: uuid.UUID,
        parent_table: str,
        parent_id: uuid.UUID,
    ) -> CascadeNode: ...

    async def execute(
        self,
        *,
        workspace_id: uuid.UUID,
        parent_table: str,
        parent_id: uuid.UUID,
    ) -> list[AuditEntry]: ...

    async def find_inbound_references(
        self,
        *,
        workspace_id: uuid.UUID,
        parent_table: str,
        parent_id: uuid.UUID,
    ) -> list[InboundReference]: ...

    async def fetch_typed_name_label(
        self,
        *,
        workspace_id: uuid.UUID,
        table: str,
        entity_id: uuid.UUID,
    ) -> str | None: ...
