"""Domain events for chemical registration context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from chem_vault.domain.shared.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class MoleculeRegistered(DomainEvent):
    registration_number: str
    molecule_type: str
    originating_org_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class MoleculeDisclosed(DomainEvent):
    inchi_key: str
    was_merged: bool = False
    merged_into_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class MoleculeMerged(DomainEvent):
    source_molecule_id: uuid.UUID
    target_molecule_id: uuid.UUID
    merge_event_id: uuid.UUID
    reason: str


@dataclass(frozen=True, kw_only=True)
class MoleculeLifecycleChanged(DomainEvent):
    old_stage: str
    new_stage: str
    changed_by: uuid.UUID
    reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class MoleculeStructureCorrected(DomainEvent):
    old_inchi_key: str
    new_inchi_key: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class MoleculeTagsUpdated(DomainEvent):
    added_tags: tuple[str, ...]
    removed_tags: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class DisclosureRequested(DomainEvent):
    molecule_id: uuid.UUID
    disclosing_org_id: uuid.UUID | None


@dataclass(frozen=True, kw_only=True)
class DisclosureResolved(DomainEvent):
    resolution_type: str
    resolved_to_molecule_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class DisclosureConflict(DomainEvent):
    conflict_reason: str


@dataclass(frozen=True, kw_only=True)
class DisclosurePendingConfirmation(DomainEvent):
    matched_molecule_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class DisclosureRejected(DomainEvent):
    reason: str


# ---------------------------------------------------------------------------
# Bulk Registration events
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class BulkRegistrationStarted(DomainEvent):
    source_file: str
    file_format: str
    total_count: int
    submitted_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class BulkRegistrationCompleted(DomainEvent):
    registered_count: int
    duplicate_count: int
    error_count: int


# ---------------------------------------------------------------------------
# Bulk Disclosure events
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class BulkDisclosureStarted(DomainEvent):
    source_file: str
    partner_org_id: uuid.UUID
    total_count: int
    submitted_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class BulkDisclosureCompleted(DomainEvent):
    disclosed_count: int
    merged_count: int
    conflict_count: int
    error_count: int


# ---------------------------------------------------------------------------
# Molecule Updated event
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class MoleculeUpdated(DomainEvent):
    pass


# ---------------------------------------------------------------------------
# CDD Molecule Import events
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class CddMoleculeImportStarted(DomainEvent):
    cdd_vault_id: str
    import_mode: str
    submitted_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class CddMoleculeImportDiscoveryComplete(DomainEvent):
    total_count: int


@dataclass(frozen=True, kw_only=True)
class CddMoleculeImportCompleted(DomainEvent):
    registered_count: int
    duplicate_count: int
    error_count: int
    skipped_count: int


@dataclass(frozen=True, kw_only=True)
class CddMoleculeImportFailed(DomainEvent):
    reason: str


# ---------------------------------------------------------------------------
# Synthesis Route events
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class SynthesisRouteCreated(DomainEvent):
    target_molecule_id: uuid.UUID
    route_type: str
    source: str


@dataclass(frozen=True, kw_only=True)
class SynthesisRouteValidated(DomainEvent):
    total_steps: int
    overall_yield: float | None = None


@dataclass(frozen=True, kw_only=True)
class SynthesisRoutePreferred(DomainEvent):
    target_molecule_id: uuid.UUID
    previous_preferred_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class SynthesisRouteDeprecated(DomainEvent):
    reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class ReactionStepOutcomeRecorded(DomainEvent):
    step_id: uuid.UUID
    yield_percent: float | None = None
    batch_id: uuid.UUID | None = None
