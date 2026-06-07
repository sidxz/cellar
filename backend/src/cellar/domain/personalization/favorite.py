"""Favorite aggregate — a per-user bookmark ("pin") of any entity."""

from __future__ import annotations

import uuid
from datetime import datetime

from cellar.domain.personalization.enums import FavoriteEntityType
from cellar.domain.shared.entity import AggregateRoot


class Favorite(AggregateRoot):
    """A user's favorite of a single entity.

    Holds only a *soft* reference — ``entity_type`` + ``entity_id`` — so the
    Personalization context never depends on the favorited entity's context.
    Immutable once created: favorites are added and removed, never edited.
    No domain events: a personal preference, not regulated/audited data.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        entity_type: FavoriteEntityType,
        entity_id: uuid.UUID,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        self.workspace_id = workspace_id
        self.user_id = user_id
        self.entity_type = entity_type
        self.entity_id = entity_id

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        entity_type: FavoriteEntityType,
        entity_id: uuid.UUID,
    ) -> Favorite:
        return cls(
            workspace_id=workspace_id,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )
