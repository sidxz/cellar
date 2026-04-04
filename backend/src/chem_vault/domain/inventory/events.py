"""Domain events for inventory context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from chem_vault.domain.shared.events import DomainEvent


# ---------------------------------------------------------------------------
# Batch events
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class BatchCreated(DomainEvent):
    molecule_id: uuid.UUID
    batch_number: str
    source: str
    supplier_org_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class BatchReassigned(DomainEvent):
    old_molecule_id: uuid.UUID
    new_molecule_id: uuid.UUID
    merge_event_id: uuid.UUID


# ---------------------------------------------------------------------------
# Sample events
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class SampleCreated(DomainEvent):
    batch_id: uuid.UUID
    barcode: str
    amount_value: float
    amount_unit: str


@dataclass(frozen=True, kw_only=True)
class SampleAliquoted(DomainEvent):
    amount_removed: float
    remaining_amount: float
    amount_unit: str


@dataclass(frozen=True, kw_only=True)
class SampleMoved(DomainEvent):
    old_location_id: uuid.UUID | None
    new_location_id: uuid.UUID | None


@dataclass(frozen=True, kw_only=True)
class SampleDepleted(DomainEvent):
    batch_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class SampleDisposed(DomainEvent):
    batch_id: uuid.UUID
    reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class LowStockDetected(DomainEvent):
    batch_id: uuid.UUID
    current_amount: float
    threshold: float
    amount_unit: str


@dataclass(frozen=True, kw_only=True)
class SampleQuarantined(DomainEvent):
    reason: str
