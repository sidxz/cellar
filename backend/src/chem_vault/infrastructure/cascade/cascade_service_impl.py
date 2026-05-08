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

from chem_vault.application.admin.cascade_service import CascadeService
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.audit_compliance.models import AuditEntry
from chem_vault.domain.shared.cascade import CascadeNode
from chem_vault.infrastructure.cascade.cascade_runner import CascadeRunner


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


# Re-export so importers can use the Protocol type in annotations.
__all__ = ["UoWBackedCascadeService", "CascadeService"]
