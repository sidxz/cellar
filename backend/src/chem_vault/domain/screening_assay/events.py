"""Domain events for Screening & Assay context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from chem_vault.domain.shared.events import DomainEvent


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
