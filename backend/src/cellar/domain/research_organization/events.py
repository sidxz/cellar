"""Domain events for research organization context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from cellar.domain.shared.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class ProjectCreated(DomainEvent):
    name: str


@dataclass(frozen=True, kw_only=True)
class ProjectArchived(DomainEvent):
    archived_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class CollectionCreated(DomainEvent):
    name: str
    type: str


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


@dataclass(frozen=True, kw_only=True)
class CampaignCreated(DomainEvent):
    """Fired when a screen campaign is created."""

    project_id: uuid.UUID
    name: str


@dataclass(frozen=True, kw_only=True)
class CampaignClosed(DomainEvent):
    """Fired when a campaign is closed (locked)."""

    closed_by: uuid.UUID
    note: str | None


@dataclass(frozen=True, kw_only=True)
class CampaignReopened(DomainEvent):
    """Fired when a closed campaign is reopened back to draft."""

    reopened_by: uuid.UUID
    reason: str


@dataclass(frozen=True, kw_only=True)
class CampaignSuperseded(DomainEvent):
    """Fired when a closed campaign is replaced by a new one."""

    superseded_by_campaign_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class CampaignCollectionAdded(DomainEvent):
    """A library was linked to a campaign. Use-case-constructed, emitted only
    when a link row was actually inserted (idempotent re-adds stay silent)."""

    collection_id: uuid.UUID
    user_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class CampaignCollectionRemoved(DomainEvent):
    collection_id: uuid.UUID
    user_id: uuid.UUID | None = None
