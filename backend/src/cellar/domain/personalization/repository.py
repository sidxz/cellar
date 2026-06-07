"""Repository protocol for Favorite aggregates."""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from cellar.domain.personalization.enums import FavoriteEntityType
from cellar.domain.personalization.favorite import Favorite


@runtime_checkable
class FavoriteRepository(Protocol):
    """Repository for Favorite aggregates.

    Favorites are addressed by their *natural key* — (user_id, entity_type,
    entity_id) within a workspace — so ``remove`` deletes by natural key and a
    PK-based ``delete`` is intentionally absent. ``entity_type`` is required on
    ``list_for_user``; broadening it to optional (cross-type listing) is a
    non-breaking change deferred until a second FavoriteEntityType exists.
    """

    async def save(self, aggregate: Favorite) -> None: ...

    async def find_by_entity(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        entity_type: FavoriteEntityType,
        entity_id: uuid.UUID,
    ) -> Favorite | None: ...

    async def list_for_user(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        entity_type: FavoriteEntityType,
    ) -> list[Favorite]: ...

    async def remove(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        entity_type: FavoriteEntityType,
        entity_id: uuid.UUID,
    ) -> None: ...

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> Favorite | None: ...
