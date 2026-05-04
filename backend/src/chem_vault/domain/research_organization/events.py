"""Domain events for research organization context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from chem_vault.domain.shared.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class ProjectCreated(DomainEvent):
    name: str


@dataclass(frozen=True, kw_only=True)
class ProjectArchived(DomainEvent):
    archived_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class CollectionCreated(DomainEvent):
    name: str


@dataclass(frozen=True, kw_only=True)
class CollectionMembersChanged(DomainEvent):
    added_ids: list[uuid.UUID]
    removed_ids: list[uuid.UUID]


@dataclass(frozen=True, kw_only=True)
class SavedSearchCreated(DomainEvent):
    name: str


@dataclass(frozen=True, kw_only=True)
class ProjectMemberAdded(DomainEvent):
    """Fired when a user is added to a project."""

    project_id: uuid.UUID
    user_id: uuid.UUID
    role: str


@dataclass(frozen=True, kw_only=True)
class ProjectMemberRemoved(DomainEvent):
    """Fired when a user is removed from a project."""

    project_id: uuid.UUID
    user_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class EntityAddedToProject(DomainEvent):
    """Fired when a molecule or protocol is added to a project."""

    entity_type: str  # "molecule" | "protocol"
    entity_id: uuid.UUID
    project_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class EntityRemovedFromProject(DomainEvent):
    """Fired when a molecule or protocol is removed from a project."""

    entity_type: str
    entity_id: uuid.UUID
    project_id: uuid.UUID
