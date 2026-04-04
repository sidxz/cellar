"""Domain events for chemical registration context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from chem_vault.domain.shared.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class MoleculeRegistered(DomainEvent):
    registration_number: str
    molecule_type: str
    workspace_id: uuid.UUID
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
