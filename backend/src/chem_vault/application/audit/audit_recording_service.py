"""Audit recording service — bridges domain events to audit operations.

This service provides two APIs:
1. ``record()`` — explicit audit recording from use cases
2. ``handle_event()`` — generic handler registered with EventDispatcher
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from chem_vault.domain.audit_compliance.enums import (
    ActorType,
    AuditAction,
    AuditStatus,
    OperationType,
)
from chem_vault.domain.audit_compliance.models import AuditEntry, AuditOperation
from chem_vault.domain.audit_compliance.repository import AuditRepository
from chem_vault.domain.shared.events import DomainEvent


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
    ) -> AuditOperation:
        """Create and persist an audit operation with entries."""
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
