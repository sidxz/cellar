"""Domain events for inventory context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from cellar.domain.shared.events import DomainEvent

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


# ---------------------------------------------------------------------------
# Storage location events
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class StorageLocationCreated(DomainEvent):
    name: str
    location_type: str
    parent_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# Sample request events
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class SampleRequestCreated(DomainEvent):
    molecule_id: uuid.UUID
    requester_id: uuid.UUID
    requested_amount: float
    amount_unit: str
    priority: str


@dataclass(frozen=True, kw_only=True)
class SampleRequestApproved(DomainEvent):
    assigned_to: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class SampleRequestFulfilled(DomainEvent):
    fulfilled_sample_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class SampleRequestRejected(DomainEvent):
    reason: str


# ---------------------------------------------------------------------------
# Shipment events
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class ShipmentCreated(DomainEvent):
    destination_org_id: uuid.UUID
    item_count: int


@dataclass(frozen=True, kw_only=True)
class ShipmentShipped(DomainEvent):
    tracking_number: str


@dataclass(frozen=True, kw_only=True)
class ShipmentDelivered(DomainEvent):
    received_date: str


# ---------------------------------------------------------------------------
# Synthesis request events
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class SynthesisRequestCreated(DomainEvent):
    molecule_id: uuid.UUID
    requested_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class SynthesisRequested(DomainEvent):
    molecule_id: uuid.UUID
    requester_id: uuid.UUID
    requested_amount: float
    amount_unit: str
    priority: str


@dataclass(frozen=True, kw_only=True)
class SynthesisRequestApproved(DomainEvent):
    approved_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class SynthesisRequestRejected(DomainEvent):
    rejected_by: uuid.UUID
    reason: str


@dataclass(frozen=True, kw_only=True)
class SynthesisRequestAssigned(DomainEvent):
    assignment_type: str
    assigned_to: uuid.UUID | None = None
    assigned_org_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class SynthesisStarted(DomainEvent):
    proposed_route_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class SynthesisFeasibilityFlagged(DomainEvent):
    feasibility_status: str
    feasibility_notes: str | None = None


@dataclass(frozen=True, kw_only=True)
class SynthesisCompleted(DomainEvent):
    actual_cost_value: float | None = None
    actual_cost_unit: str | None = None


@dataclass(frozen=True, kw_only=True)
class SynthesisFailed(DomainEvent):
    failure_reason: str


@dataclass(frozen=True, kw_only=True)
class SynthesisRequestFulfilled(DomainEvent):
    fulfilled_batch_id: uuid.UUID


# ---------------------------------------------------------------------------
# Registered plate events
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class PlateRegistered(DomainEvent):
    barcode: str
    format: str
    plate_type: str
    registered_by: uuid.UUID
    owner_org_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class PlateWellsMapped(DomainEvent):
    well_count: int
    batch_ids: list[uuid.UUID]


@dataclass(frozen=True, kw_only=True)
class PlateMoved(DomainEvent):
    old_location_id: uuid.UUID | None
    new_location_id: uuid.UUID | None


@dataclass(frozen=True, kw_only=True)
class PlateStatusChanged(DomainEvent):
    old_status: str
    new_status: str


@dataclass(frozen=True, kw_only=True)
class PlateDisposed(DomainEvent):
    barcode: str


# ---------------------------------------------------------------------------
# Org plate policy events
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class OrgPlatePolicySet(DomainEvent):
    org_id: uuid.UUID


# ---------------------------------------------------------------------------
# CDD plate import events
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class CddPlateImportStarted(DomainEvent):
    cdd_vault_id: str
    submitted_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class CddPlateImportDiscoveryComplete(DomainEvent):
    total_count: int


@dataclass(frozen=True, kw_only=True)
class CddPlateImportCompleted(DomainEvent):
    plates_registered: int
    plates_duplicate: int
    plates_error: int
    wells_mapped: int
    wells_unresolved: int


@dataclass(frozen=True, kw_only=True)
class CddPlateImportFailed(DomainEvent):
    reason: str
