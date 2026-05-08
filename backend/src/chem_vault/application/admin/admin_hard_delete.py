"""Tier-1 admin hard-delete use case.

Behavior:
  1. require_admin(auth)
  2. Look up the entity in its repo (404 if missing).
  3. find_inbound_references(...) — RESTRICT if any.
  4. Snapshot the entity, hard-delete, and write one AuditOperation
     with operation_type=ADMIN_HARD_DELETE.

Returns:
  Success(None) on delete.
  Failure(BlockedByDependenciesError) with structured payload on blockers.
  Failure(NotFoundError) / Failure(AuthorizationError) on the obvious failures.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Sequence

from returns.result import Failure, Result, Success

from chem_vault.application.admin.admin_delete_registry import get_entry
from chem_vault.application.audit.audit_recording_service import AuditRecordingService
from chem_vault.application.auth import AuthContext, require_admin
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.audit_compliance.enums import AuditAction, OperationType
from chem_vault.domain.audit_compliance.models import AuditEntry
from chem_vault.domain.shared.errors import (
    AuthorizationError,
    DomainError,
    NotFoundError,
    ValidationError,
)
from chem_vault.infrastructure.cascade.inbound_refs import (
    InboundReference,
    find_inbound_references,
)


@dataclass(frozen=True, kw_only=True)
class AdminHardDeleteCommand(Command):
    workspace_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    reason: str


@dataclass(frozen=True)
class BlockedByDependenciesError(DomainError):
    """Tier-1 RESTRICT: caller must clean up dependents first."""

    blockers: Sequence[InboundReference]

    @property
    def message(self) -> str:  # type: ignore[override]
        parts = [f"{r.count} {r.entity_type}(s)" for r in self.blockers]
        return "Cannot delete: " + ", ".join(parts) + " reference this entity."


class AdminHardDelete:
    def __init__(
        self,
        uow: UnitOfWork,
        audit: AuditRecordingService,
        container,  # Lagom Container — used to resolve per-entity repos
    ) -> None:
        self._uow = uow
        self._audit = audit
        self._container = container

    async def __call__(
        self,
        input: AdminHardDeleteCommand,
        auth: AuthContext | None = None,
    ) -> Result[None, DomainError]:
        try:
            require_admin(auth)
        except AuthorizationError as e:
            return Failure(e)

        if not (input.reason or "").strip():
            return Failure(ValidationError("reason is required"))

        entry = get_entry(input.entity_type)
        if entry is None:
            return Failure(NotFoundError("entity_type", input.entity_type))

        async with self._uow:
            # Resolve the repo inside the active UoW so the adapter shares
            # the same transaction (repo_resolver signature: (container, uow)).
            repo = entry.repo_resolver(self._container, self._uow)
            obj = await repo.find_by_id(input.workspace_id, input.entity_id)
            if obj is None:
                return Failure(NotFoundError(input.entity_type, str(input.entity_id)))

            blockers = await find_inbound_references(
                self._uow.session,  # type: ignore[attr-defined]
                parent_table=entry.table,
                parent_id=input.entity_id,
                workspace_id=input.workspace_id,
            )
            if blockers:
                return Failure(BlockedByDependenciesError(blockers=tuple(blockers)))

            snapshot = _to_snapshot_dict(obj)
            await repo.delete(input.workspace_id, input.entity_id)
            await self._uow.commit()

        # Audit *after* commit — admin delete records actual outcome, not intent.
        assert auth is not None  # require_admin already enforced
        now = datetime.now(UTC)
        await self._audit.record(
            workspace_id=input.workspace_id,
            operation_type=OperationType.ADMIN_HARD_DELETE,
            entity_type=input.entity_type,
            entity_id=input.entity_id,
            user_id=auth.user_id,
            reason=input.reason,
            entries=[
                AuditEntry(
                    entity_type=input.entity_type,
                    entity_id=input.entity_id,
                    field_name="*",
                    action=AuditAction.DELETE,
                    old_value=json.dumps(snapshot, default=str, sort_keys=True),
                    new_value=None,
                    timestamp=now,
                )
            ],
        )

        return Success(None)


def _to_snapshot_dict(obj) -> dict:
    """Best-effort serialize a domain object or ORM row to a dict."""
    if hasattr(obj, "__dataclass_fields__"):
        return {f: getattr(obj, f) for f in obj.__dataclass_fields__}
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
    return {"value": str(obj)}
