"""Repository protocols for the Personalization context."""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from cellar.domain.personalization.enums import FavoriteEntityType
from cellar.domain.personalization.favorite import Favorite
from cellar.domain.personalization.recent_search import RecentSearch


@runtime_checkable
class FavoriteRepository(Protocol):
    """Repository for Favorite aggregates.

    Favorites are addressed by their *natural key* — (user_id, entity_type,
    entity_id) within a workspace — so ``remove`` deletes by natural key and a
    PK-based ``delete`` is intentionally absent. ``entity_type`` is required on
    ``list_for_user``; broadening it to optional (cross-type listing) is a
    non-breaking change deferred until a second FavoriteEntityType exists.
    """

    async def save(self, aggregate: Favorite) -> None:
        """Idempotently persist a favorite — insert on natural key, no-op on conflict.

        Favorites are immutable (add/remove only), so ``save`` is a pure
        idempotent insert, not an INSERT-or-UPDATE. A second save of the same
        natural key (e.g. a lost concurrent-add race) silently no-ops; the
        unique index on (workspace_id, user_id, entity_type, entity_id) is the
        DB backstop. Never raises on duplicate.
        """
        ...

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


@runtime_checkable
class RecentSearchRepository(Protocol):
    """A user's recent searches within a workspace, newest first.

    ``record`` is one atomic step: the entry replaces any older entry for the
    same search (same ``query_key``), then everything past the newest ``keep``
    entries is dropped. Plain-CRUD persistence — no UnitOfWork (see
    ``RecentSearch``).
    """

    async def record(self, search: RecentSearch, *, keep: int) -> RecentSearch: ...

    async def list_for_user(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, limit: int
    ) -> list[RecentSearch]: ...

    async def clear(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> None: ...
