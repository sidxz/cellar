# application/admin/cascade_delete.py
from __future__ import annotations
import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.admin.admin_delete_registry import get_entry
from chem_vault.application.admin.cascade_preview import TIER2_ENTITY_TYPES
from chem_vault.application.audit.audit_recording_service import AuditRecordingService
from chem_vault.application.auth import AuthContext, require_admin
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.audit_compliance.enums import OperationType
from chem_vault.domain.shared.errors import (
    AuthorizationError, DomainError, NotFoundError, ValidationError,
)
from chem_vault.infrastructure.cascade.cascade_runner import (
    CascadeExecutionError, CascadeRunner,
)
from chem_vault.infrastructure.cascade.label_fields import label_for_table


@dataclass(frozen=True, kw_only=True)
class CascadeDeleteCommand(Command):
    workspace_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    typed_name: str
    reason: str


class CascadeDelete:
    def __init__(self, uow: UnitOfWork, audit: AuditRecordingService) -> None:
        self._uow = uow
        self._audit = audit

    async def __call__(
        self, input: CascadeDeleteCommand, auth: AuthContext | None = None,
    ) -> Result[None, DomainError]:
        try:
            require_admin(auth)
        except AuthorizationError as e:
            return Failure(e)
        if input.entity_type not in TIER2_ENTITY_TYPES:
            return Failure(NotFoundError("entity_type", input.entity_type))
        if not input.reason.strip():
            return Failure(ValidationError("reason is required"))

        entry = get_entry(input.entity_type)
        if entry is None:
            return Failure(NotFoundError("entity_type", input.entity_type))

        async with self._uow:
            actual_label = await _fetch_label(
                self._uow.session, entry.table, input.entity_id,  # type: ignore[attr-defined]
                workspace_id=input.workspace_id,
            )
            if actual_label is None:
                return Failure(NotFoundError(input.entity_type, str(input.entity_id)))
            if input.typed_name != actual_label:
                return Failure(ValidationError(
                    f"typed_name does not match {input.entity_type} name"
                ))

            runner = CascadeRunner(self._uow.session)  # type: ignore[attr-defined]
            try:
                entries = await runner.execute(
                    parent_table=entry.table,
                    parent_id=input.entity_id,
                    workspace_id=input.workspace_id,
                )
            except CascadeExecutionError as e:
                return Failure(ValidationError(str(e)))
            await self._uow.commit()

        assert auth is not None
        await self._audit.record(
            workspace_id=input.workspace_id,
            operation_type=OperationType.ADMIN_HARD_DELETE,
            entity_type=input.entity_type,
            entity_id=input.entity_id,
            user_id=auth.user_id,
            reason=input.reason,
            entries=entries,
        )
        return Success(None)


async def _fetch_label(
    session, table_name: str, id_: uuid.UUID, *, workspace_id: uuid.UUID
):
    from sqlalchemy import select
    from chem_vault.infrastructure.persistence.sqlalchemy.base import Base
    _et, label_col = label_for_table(table_name)
    if not label_col:
        return None
    t = Base.metadata.tables[table_name]
    stmt = select(t.c[label_col]).where(t.c.id == id_)
    if "workspace_id" in t.c:
        stmt = stmt.where(t.c["workspace_id"] == workspace_id)
    return (await session.execute(stmt)).scalar_one_or_none()
