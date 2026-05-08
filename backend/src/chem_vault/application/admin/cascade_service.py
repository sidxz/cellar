"""Application-layer Protocol for cascade preview + execute.

Hides the SQLAlchemy session detail and the CascadeRunner concrete class
from the use case layer.  Infrastructure provides ``UoWBackedCascadeService``
as the concrete implementation.
"""
from __future__ import annotations

import uuid
from typing import Protocol

from chem_vault.domain.audit_compliance.models import AuditEntry
from chem_vault.domain.shared.cascade import CascadeNode


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
