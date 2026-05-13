# application/admin/cascade_delete.py
from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.admin.admin_delete_registry import get_entry
from cellar.application.admin.cascade_service import (
    CascadeExecutionError,
    CascadeService,
)
from cellar.application.admin.tier2_entities import TIER2_ENTITY_TYPES
from cellar.application.audit.audit_recording_service import AuditRecordingService
from cellar.application.auth import AuthContext, require_admin
from cellar.application.shared.command import Command
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.audit_compliance.enums import OperationType
from cellar.domain.shared.errors import (
    DomainError,
    NotFoundError,
    ValidationError,
)


@dataclass(frozen=True, kw_only=True)
class CascadeDeleteCommand(Command):
    workspace_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    typed_name: str
    reason: str


class CascadeDelete:
    def __init__(
        self,
        uow: UnitOfWork,
        audit: AuditRecordingService,
        cascade_service: CascadeService,
    ) -> None:
        self._uow = uow
        self._audit = audit
        self._cascade_service = cascade_service

    async def __call__(
        self,
        input: CascadeDeleteCommand,
        auth: AuthContext | None = None,
    ) -> Result[None, DomainError]:
        require_admin(auth)
        if input.entity_type not in TIER2_ENTITY_TYPES:
            return Failure(NotFoundError("entity_type", input.entity_type))
        if not input.reason.strip():
            return Failure(ValidationError("reason is required"))

        entry = get_entry(input.entity_type)
        if entry is None:
            return Failure(NotFoundError("entity_type", input.entity_type))

        async with self._uow:
            actual_label = await self._cascade_service.fetch_typed_name_label(
                workspace_id=input.workspace_id,
                table=entry.table,
                entity_id=input.entity_id,
            )
            if actual_label is None:
                return Failure(NotFoundError(input.entity_type, str(input.entity_id)))
            if input.typed_name != actual_label:
                return Failure(
                    ValidationError(f"typed_name does not match {input.entity_type} name")
                )

            try:
                entries = await self._cascade_service.execute(
                    parent_table=entry.table,
                    parent_id=input.entity_id,
                    workspace_id=input.workspace_id,
                )
            except CascadeExecutionError as e:
                return Failure(ValidationError(str(e)))

            # Audit inside the active transaction so that audit failure rolls
            # back the entire cascade — atomicity required for 21 CFR Part 11.
            assert auth is not None
            await self._audit.record(
                workspace_id=input.workspace_id,
                operation_type=OperationType.ADMIN_HARD_DELETE,
                entity_type=input.entity_type,
                entity_id=input.entity_id,
                user_id=auth.user_id,
                reason=input.reason,
                entries=entries,
                session=self._uow.session,
            )
            await self._uow.commit()

        return Success(None)
