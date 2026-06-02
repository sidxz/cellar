"""Domain events for the tagging capability."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from cellar.domain.shared.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class TagCreated(DomainEvent):
    key: str
    value: str | None


@dataclass(frozen=True, kw_only=True)
class TagRenamed(DomainEvent):
    key: str
    value: str | None


@dataclass(frozen=True, kw_only=True)
class TagDeleted(DomainEvent):
    key: str
    value: str | None


@dataclass(frozen=True, kw_only=True)
class TagMerged(DomainEvent):
    """Emitted on the source tag when it is merged into ``target_tag_id``."""

    target_tag_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class TagAssigned(DomainEvent):
    """Emitted when a tag is applied to an entity. ``aggregate_id`` is the tag id."""

    target_type: str
    target_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class TagUnassigned(DomainEvent):
    """Emitted when a tag is removed from an entity. ``aggregate_id`` is the tag id."""

    target_type: str
    target_id: uuid.UUID
