"""Infrastructure binding of the CascadeService Protocol.

``UoWBackedCascadeService`` satisfies the application-layer ``CascadeService``
Protocol by reading the session from an active UoW.  It must be called inside
an ``async with uow:`` block — the UoW exposes its session via the documented
protocol attribute.

Accessing ``uow.session`` here is legitimate: this is infrastructure code
depending on infrastructure (AsyncUnitOfWork), so no abstraction is breached.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from chem_vault.application.admin.cascade_service import (
    CascadeService,
    InboundReference,
)
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.audit_compliance.models import AuditEntry
from chem_vault.domain.shared.cascade import CascadeNode
from chem_vault.infrastructure.cascade.cascade_runner import CascadeRunner
from chem_vault.infrastructure.cascade.inbound_refs import find_inbound_references
from chem_vault.infrastructure.cascade.label_fields import label_for_table
from chem_vault.infrastructure.persistence.sqlalchemy.base import Base


class UoWBackedCascadeService:
    """Implements CascadeService by reading the active UoW's session.

    Must be called inside an active ``async with uow:`` block.
    """

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def preview(
        self,
        *,
        workspace_id: uuid.UUID,
        parent_table: str,
        parent_id: uuid.UUID,
    ) -> CascadeNode:
        runner = CascadeRunner(self._uow.session)  # infra-to-infra: OK
        return await runner.preview(
            workspace_id=workspace_id,
            parent_table=parent_table,
            parent_id=parent_id,
        )

    async def execute(
        self,
        *,
        workspace_id: uuid.UUID,
        parent_table: str,
        parent_id: uuid.UUID,
    ) -> list[AuditEntry]:
        runner = CascadeRunner(self._uow.session)  # infra-to-infra: OK
        return await runner.execute(
            workspace_id=workspace_id,
            parent_table=parent_table,
            parent_id=parent_id,
        )

    async def find_inbound_references(
        self,
        *,
        workspace_id: uuid.UUID,
        parent_table: str,
        parent_id: uuid.UUID,
    ) -> list[InboundReference]:
        return await find_inbound_references(
            self._uow.session,
            parent_table=parent_table,
            parent_id=parent_id,
            workspace_id=workspace_id,
        )

    async def fetch_typed_name_label(
        self,
        *,
        workspace_id: uuid.UUID,
        table: str,
        entity_id: uuid.UUID,
    ) -> str | None:
        _et, label_col = label_for_table(table)
        if not label_col:
            return None
        sa_table = Base.metadata.tables[table]
        if label_col not in sa_table.c:
            return None
        stmt = select(sa_table.c[label_col]).where(sa_table.c.id == entity_id)
        if "workspace_id" in sa_table.c:
            stmt = stmt.where(sa_table.c["workspace_id"] == workspace_id)
        result = await self._uow.session.execute(stmt)
        return result.scalar_one_or_none()


# Re-export so importers can use the Protocol type in annotations.
__all__ = ["UoWBackedCascadeService", "CascadeService"]
