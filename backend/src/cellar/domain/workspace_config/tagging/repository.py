"""Repository protocols for the tagging capability."""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from cellar.domain.workspace_config.tagging.tag import (
    AssignedTag,
    Tag,
    TaggableEntityType,
    TagName,
)


@runtime_checkable
class TagRepository(Protocol):
    """Registry of Tag aggregates (the deduplicated set of key/value pairs)."""

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> Tag | None: ...

    async def find_by_normalized(
        self, workspace_id: uuid.UUID, name: TagName
    ) -> Tag | None: ...

    async def get_or_create(
        self, workspace_id: uuid.UUID, name: TagName, created_by: uuid.UUID
    ) -> Tag:
        """Return the existing tag for ``name`` or create it (race-safe).

        Emits ``TagCreated`` (collected on commit) only when a new row is
        actually inserted.
        """
        ...

    async def search(
        self,
        workspace_id: uuid.UUID,
        *,
        q: str | None = None,
        created_by: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[Tag]:
        """Autocomplete / listing — substring match on normalized key/value."""
        ...

    async def save(self, aggregate: Tag) -> None: ...

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...


@runtime_checkable
class TagLinkRepository(Protocol):
    """Manages tag↔entity links for ONE taggable entity type.

    Each concrete implementation is bound to a single link table; obtain the
    right one from a ``TagLinkRepositoryProvider``.
    """

    async def entity_exists_in_workspace(
        self, workspace_id: uuid.UUID, entity_id: uuid.UUID
    ) -> bool: ...

    async def add(
        self,
        workspace_id: uuid.UUID,
        entity_id: uuid.UUID,
        tag_id: uuid.UUID,
        assigned_by: uuid.UUID,
    ) -> None: ...

    async def remove(
        self, workspace_id: uuid.UUID, entity_id: uuid.UUID, tag_id: uuid.UUID
    ) -> None: ...

    async def set_for_entity(
        self,
        workspace_id: uuid.UUID,
        entity_id: uuid.UUID,
        tag_ids: list[uuid.UUID],
        assigned_by: uuid.UUID,
    ) -> None: ...

    async def find_tags_for_entity(
        self, workspace_id: uuid.UUID, entity_id: uuid.UUID
    ) -> list[Tag]: ...

    async def find_assigned_tags_for_entity(
        self, workspace_id: uuid.UUID, entity_id: uuid.UUID
    ) -> list[AssignedTag]:
        """Tags on the entity, each with its assignment provenance."""
        ...

    async def find_entity_ids_for_tags(
        self,
        workspace_id: uuid.UUID,
        tag_ids: list[uuid.UUID],
        *,
        match_all: bool,
    ) -> list[uuid.UUID]: ...

    async def repoint(
        self, from_tag_id: uuid.UUID, to_tag_id: uuid.UUID
    ) -> None: ...


@runtime_checkable
class TagLinkRepositoryProvider(Protocol):
    """Resolves the right ``TagLinkRepository`` for a given entity type."""

    def for_type(self, entity_type: TaggableEntityType) -> TagLinkRepository: ...
