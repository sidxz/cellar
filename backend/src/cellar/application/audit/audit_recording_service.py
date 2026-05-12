"""Audit recording service — bridges domain events to audit operations.

This service provides two APIs:
1. ``record()`` — explicit audit recording from use cases
2. ``handle_event()`` — generic handler registered with EventDispatcher
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from cellar.domain.audit_compliance.enums import (
    ActorType,
    AuditAction,
    AuditStatus,
    OperationType,
)
from cellar.domain.audit_compliance.models import AuditEntry, AuditOperation
from cellar.domain.audit_compliance.repository import AuditRepository
from cellar.domain.shared.events import DomainEvent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from cellar.infrastructure.persistence.sqlalchemy.audit.audit_repository import (
        SQLAlchemyAuditRepository,
    )


class AuditRecordingService:
    """Records audit operations from domain events or explicit calls."""

    def __init__(self, repository: AuditRepository) -> None:
        self._repository = repository

    async def record(
        self,
        *,
        workspace_id: uuid.UUID,
        operation_type: OperationType,
        entity_type: str,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
        entries: list[AuditEntry],
        actor_type: ActorType = ActorType.USER,
        reason: str | None = None,
        correlation_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        session: Any | None = None,
    ) -> AuditOperation:
        """Create and persist an audit operation with entries.

        Parameters
        ----------
        session:
            When provided (must be an ``AsyncSession``), the audit write is
            added to *that* session without issuing a separate commit.  The
            caller (unit-of-work) owns the transaction; if it rolls back the
            audit write rolls back too.  This is the safe path for mutations
            that must be audited atomically (e.g. admin hard-delete).

            When ``None`` (default), a fresh session is opened and committed
            immediately — the original behaviour used by event handlers and
            other call sites.
        """
        now = datetime.now(UTC)
        operation = AuditOperation(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            operation_type=operation_type,
            reason=reason,
            user_id=user_id,
            actor_type=actor_type,
            correlation_id=correlation_id,
            entity_type=entity_type,
            entity_id=entity_id,
            status=AuditStatus.COMPLETED,
            ip_address=ip_address,
            user_agent=user_agent,
            started_at=now,
            completed_at=now,
            entries=[],
        )
        for entry in entries:
            operation.add_entry(entry)

        if session is not None:
            # Participate in the caller's transaction — no self-commit.
            # Requires the underlying repository to support session injection.
            repo = self._repository
            if hasattr(repo, "save_with_session"):
                await repo.save_with_session(operation, session)  # type: ignore[union-attr]
            else:
                # Fallback: repository doesn't support session injection.
                # This should not happen in production; raise to surface the gap.
                raise RuntimeError(
                    f"AuditRepository {type(repo).__name__!r} does not support "
                    "session-scoped saves. Implement save_with_session()."
                )
        else:
            await self._repository.save(operation)
        return operation

    async def handle_event(self, event: DomainEvent) -> None:
        """Generic event handler — creates a minimal audit operation.

        Use cases should call ``record()`` directly for richer audit trails.
        This handler serves as a fallback for events that don't have
        a dedicated audit handler wired up.
        """
        operation = AuditOperation(
            id=uuid.uuid4(),
            workspace_id=getattr(event, "workspace_id", uuid.UUID(int=0)),
            operation_type=_infer_operation_type(event),
            user_id=getattr(event, "user_id", uuid.UUID(int=0)),
            actor_type=ActorType.SYSTEM,
            entity_type=event.aggregate_type,
            entity_id=event.aggregate_id,
            status=AuditStatus.COMPLETED,
            started_at=event.occurred_at,
            completed_at=event.occurred_at,
        )

        operation.add_entry(
            AuditEntry(
                entity_type=event.aggregate_type,
                entity_id=event.aggregate_id,
                field_name="event",
                action=AuditAction.CREATE,
                new_value=type(event).__name__,
                timestamp=event.occurred_at,
            )
        )

        await self._repository.save(operation)


def _infer_operation_type(event: DomainEvent) -> OperationType:
    """Best-effort mapping from event class name to operation type."""
    name = type(event).__name__.lower()
    mapping: dict[str, OperationType] = {
        "registered": OperationType.REGISTRATION,
        "disclosed": OperationType.DISCLOSURE,
        "merged": OperationType.MERGE,
        "corrected": OperationType.STRUCTURE_CORRECTION,
        "approved": OperationType.APPROVAL,
        "rejected": OperationType.REJECTION,
        "locked": OperationType.DATA_LOCK,
        "unlocked": OperationType.DATA_UNLOCK,
        "lifecycle": OperationType.LIFECYCLE_CHANGE,
    }
    for keyword, op_type in mapping.items():
        if keyword in name:
            return op_type
    return OperationType.DATA_ENTRY
