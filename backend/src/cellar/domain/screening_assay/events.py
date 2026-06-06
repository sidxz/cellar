"""Domain events for Screening & Assay context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from cellar.domain.shared.events import DomainEvent

# ---------------------------------------------------------------------------
# Protocol events
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class ProtocolCreated(DomainEvent):
    name: str
    version: int
    protocol_type: str


@dataclass(frozen=True, kw_only=True)
class ProtocolVersionCreated(DomainEvent):
    parent_protocol_id: uuid.UUID
    version: int


@dataclass(frozen=True, kw_only=True)
class ProtocolPublished(DomainEvent):
    pass


@dataclass(frozen=True, kw_only=True)
class ProtocolRetired(DomainEvent):
    reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class ProtocolLocked(DomainEvent):
    locked_by: uuid.UUID
    lock_reason: str


@dataclass(frozen=True, kw_only=True)
class ProtocolUnlocked(DomainEvent):
    unlocked_by: uuid.UUID
    reason: str


@dataclass(frozen=True, kw_only=True)
class ProtocolTargetAdded(DomainEvent):
    """A direct target was attached to a protocol.

    Targets are an M2M association, not aggregate state, so these events are
    constructed by the use case (not registered on the aggregate) and emitted
    only when a link row was actually inserted — idempotent re-adds stay
    silent. ``user_id`` feeds actor attribution in the audit catch-all.
    """

    target_id: uuid.UUID
    user_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class ProtocolTargetRemoved(DomainEvent):
    target_id: uuid.UUID
    user_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# Run events
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class RunCreated(DomainEvent):
    protocol_id: uuid.UUID
    operator: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class RunCompleted(DomainEvent):
    plate_count: int
    data_point_count: int


@dataclass(frozen=True, kw_only=True)
class RunApproved(DomainEvent):
    approved_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class RunRejected(DomainEvent):
    rejected_by: uuid.UUID
    reason: str


@dataclass(frozen=True, kw_only=True)
class RunLocked(DomainEvent):
    locked_by: uuid.UUID
    lock_reason: str


@dataclass(frozen=True, kw_only=True)
class RunUnlocked(DomainEvent):
    unlocked_by: uuid.UUID
    reason: str


@dataclass(frozen=True, kw_only=True)
class RunTargetAdded(DomainEvent):
    """A target was attached to a run. See ``ProtocolTargetAdded`` for the
    use-case-constructed emission convention."""

    target_id: uuid.UUID
    user_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class RunTargetRemoved(DomainEvent):
    target_id: uuid.UUID
    user_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class RunDataReset(DomainEvent):
    """Emitted when a run's plates/wells/readouts/curves/QC are wiped.

    The run row, its metadata, and any uploaded file attachments are
    preserved — this is the destructive escape hatch for a chemist who
    needs to redo an import from scratch without losing the run audit
    history.
    """

    plates_deleted: int
    wells_deleted: int
    readouts_deleted: int
    curves_deleted: int
