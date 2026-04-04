"""Audit & compliance domain models.

All models are append-only — no UPDATE or DELETE permitted.
AuditOperation is the aggregate root; AuditEntry and ElectronicSignature
are owned entities within its boundary.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from chem_vault.domain.audit_compliance.enums import (
    ActorType,
    AuditAction,
    AuditStatus,
    AuthMethod,
    OperationType,
)


@dataclass
class AuditEntry:
    """Field-level change record — the 'what' of a mutation.

    Append-only: once created, never modified or deleted.
    """

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    operation_id: uuid.UUID = field(default_factory=uuid.uuid4)
    entity_type: str = ""
    entity_id: uuid.UUID = field(default_factory=uuid.uuid4)
    field_name: str = ""
    action: AuditAction = AuditAction.CREATE
    old_value: str | None = None
    new_value: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ElectronicSignature:
    """Re-authentication record for regulated actions (21 CFR Part 11).

    Append-only: once created, never modified or deleted.
    """

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    operation_id: uuid.UUID = field(default_factory=uuid.uuid4)
    user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    meaning: str = ""
    auth_method: AuthMethod = AuthMethod.PASSWORD
    signed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class AuditOperation:
    """Logical operation grouping related changes — the 'why' and 'who'.

    This is the aggregate root of the audit context. It is append-only:
    once created, never modified or deleted. No versioning needed
    (optimistic concurrency is irrelevant for insert-only data).
    """

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    workspace_id: uuid.UUID = field(default_factory=uuid.uuid4)
    operation_type: OperationType = OperationType.DATA_ENTRY
    reason: str | None = None
    user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    actor_type: ActorType = ActorType.USER
    correlation_id: uuid.UUID | None = None
    entity_type: str = ""
    entity_id: uuid.UUID = field(default_factory=uuid.uuid4)
    status: AuditStatus = AuditStatus.COMPLETED
    ip_address: str | None = None
    user_agent: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    entries: list[AuditEntry] = field(default_factory=list)
    signature: ElectronicSignature | None = None

    def add_entry(self, entry: AuditEntry) -> None:
        """Add a field-level change record."""
        entry.operation_id = self.id
        self.entries.append(entry)

    def add_signature(self, signature: ElectronicSignature) -> None:
        """Attach an electronic signature to this operation."""
        signature.operation_id = self.id
        self.signature = signature
