"""Domain events for research organization context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from chem_vault.domain.shared.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class ProjectCreated(DomainEvent):
    workspace_id: uuid.UUID
    name: str


@dataclass(frozen=True, kw_only=True)
class ProjectArchived(DomainEvent):
    workspace_id: uuid.UUID
    archived_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class CollectionCreated(DomainEvent):
    workspace_id: uuid.UUID
    name: str


@dataclass(frozen=True, kw_only=True)
class CollectionMembersChanged(DomainEvent):
    workspace_id: uuid.UUID
    added_ids: list[uuid.UUID]
    removed_ids: list[uuid.UUID]


@dataclass(frozen=True, kw_only=True)
class SavedSearchCreated(DomainEvent):
    workspace_id: uuid.UUID
    name: str
