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


def _view_facts(name: str, visibility: str, project_id: uuid.UUID | None) -> list[tuple[str, str]]:
    facts = [("name", name), ("visibility", visibility)]
    return facts + ([("project_id", str(project_id))] if project_id else [])


@dataclass(frozen=True, kw_only=True)
class SavedVisualizationCreated(DomainEvent):
    name: str
    visibility: str
    project_id: uuid.UUID | None = None

    def audit_changes(self) -> list[tuple[str, str | None, str | None]]:
        return [(f, None, v) for f, v in _view_facts(self.name, self.visibility, self.project_id)]


@dataclass(frozen=True, kw_only=True)
class SavedVisualizationUpdated(DomainEvent):
    """Old and new value per changed field; ``source`` and ``config`` are named without
    values (they are JSON documents, not audit text)."""

    changes: tuple[tuple[str, str | None, str | None], ...]

    def audit_changes(self) -> list[tuple[str, str | None, str | None]]:
        return list(self.changes)


@dataclass(frozen=True, kw_only=True)
class SavedVisualizationDeleted(DomainEvent):
    name: str
    visibility: str
    project_id: uuid.UUID | None = None

    def audit_changes(self) -> list[tuple[str, str | None, str | None]]:
        return [(f, v, None) for f, v in _view_facts(self.name, self.visibility, self.project_id)]


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
