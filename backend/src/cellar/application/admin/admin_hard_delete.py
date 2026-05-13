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
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from returns.result import Failure, Result, Success

from cellar.application.admin.admin_delete_registry import (
    AdminDeletableRepoMap,
    get_entry,
)
from cellar.application.admin.cascade_service import (
    CascadeService,
    InboundReference,
)
from cellar.application.audit.audit_recording_service import AuditRecordingService
from cellar.application.auth import AuthContext, require_admin
from cellar.application.shared.command import Command
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.audit_compliance.enums import AuditAction, OperationType
from cellar.domain.audit_compliance.models import AuditEntry
from cellar.domain.shared.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)


@dataclass(frozen=True, kw_only=True)
class AdminHardDeleteCommand(Command):
    workspace_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    reason: str


class BlockedByDependenciesError(ConflictError):
    """Tier-1 RESTRICT: caller must clean up dependents first.

    Maps to HTTP 409 via the ConflictError parent. The blocker list is
    surfaced in the response body via ``body_extras``.
    """

    def __init__(self, blockers: Sequence[InboundReference]) -> None:
        self.blockers = tuple(blockers)
        parts = [f"{r.count} {r.entity_type}(s)" for r in self.blockers]
        super().__init__("Cannot delete: " + ", ".join(parts) + " reference this entity.")

    def body_extras(self) -> dict[str, object]:
        return {
            "error": "delete_blocked_by_dependencies",
            "blockers": [
                {
                    "table": r.table,
                    "entity_type": r.entity_type,
                    "fk_column": r.fk_column,
                    "count": r.count,
                    "samples": r.samples,
                    "truncated": r.truncated,
                }
                for r in self.blockers
            ],
        }


class AdminHardDelete:
    def __init__(
        self,
        uow: UnitOfWork,
        audit: AuditRecordingService,
        repos: AdminDeletableRepoMap | Callable[[UnitOfWork], AdminDeletableRepoMap],
        cascade_service: CascadeService,
    ) -> None:
        self._uow = uow
        self._audit = audit
        # Accept either a pre-built map or a factory callable (UoW → map).
        # The factory form allows DI to wire repos that need the active session.
        self._repos = repos
        self._cascade_service = cascade_service

    def _get_repo_map(self, uow: UnitOfWork) -> AdminDeletableRepoMap:
        if callable(self._repos):
            return self._repos(uow)
        return self._repos

    async def __call__(
        self,
        input: AdminHardDeleteCommand,
        auth: AuthContext | None = None,
    ) -> Result[None, DomainError]:
        require_admin(auth)

        if not (input.reason or "").strip():
            return Failure(ValidationError("reason is required"))

        entry = get_entry(input.entity_type)
        if entry is None:
            return Failure(NotFoundError("entity_type", input.entity_type))

        async with self._uow:
            repo_map = self._get_repo_map(self._uow)
            repo = repo_map.get(input.entity_type)
            if repo is None:
                return Failure(NotFoundError("entity_type", input.entity_type))

            obj = await repo.find_by_id(input.workspace_id, input.entity_id)
            if obj is None:
                return Failure(NotFoundError(input.entity_type, str(input.entity_id)))

            blockers = await self._cascade_service.find_inbound_references(
                workspace_id=input.workspace_id,
                parent_table=entry.table,
                parent_id=input.entity_id,
            )
            if blockers:
                return Failure(BlockedByDependenciesError(blockers))

            snapshot = _to_snapshot_dict(obj)
            await repo.delete(input.workspace_id, input.entity_id)

            # Audit inside the active transaction so that audit failure rolls
            # back the delete — atomicity required for 21 CFR Part 11.
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
                session=self._uow.session,
            )
            await self._uow.commit()

        return Success(None)


def _to_snapshot_dict(obj) -> dict:
    """Best-effort serialize a domain object or ORM row to a dict."""
    if hasattr(obj, "__dataclass_fields__"):
        return {f: getattr(obj, f) for f in obj.__dataclass_fields__}
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
    return {"value": str(obj)}
