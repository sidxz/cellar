"""Registry of entity types that support admin hard-delete (Tier 1).

Each entry is a (table_name, RepoProtocol) pair plus a small adapter
that knows how to fetch+delete from that repo. The adapter signatures
are uniform: `find_by_id(workspace_id, id)` and `delete(workspace_id, id)`.

The registry is populated at module import time. New entities opt-in
by adding an entry here.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol


class _DeletableRepo(Protocol):
    """Protocol for repositories that support admin hard-delete."""

    async def find_by_id(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> Any: ...

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...


@dataclass(frozen=True)
class AdminDeleteEntry:
    """Registry entry for an admin-deletable entity type."""

    entity_type: str
    table: str
    label_field: str | None
    repo_resolver: Callable[..., _DeletableRepo]  # (container) -> repo


# entity_type -> AdminDeleteEntry. Populated by register_admin_delete().
_REGISTRY: dict[str, AdminDeleteEntry] = {}


def register_admin_delete(
    *,
    entity_type: str,
    table: str,
    label_field: str | None,
    repo_resolver: Callable[..., _DeletableRepo],
) -> None:
    """Register an entity type as admin-deletable (Tier 1).

    Args:
        entity_type: Unique identifier for the entity type (e.g., "vocabulary").
        table: Database table name.
        label_field: Optional field name for display labels (e.g., "name").
        repo_resolver: Callable that returns a _DeletableRepo instance.

    Raises:
        RuntimeError: If entity_type is already registered.
    """
    if entity_type in _REGISTRY:
        raise RuntimeError(
            f"{entity_type} already registered for admin-delete"
        )
    _REGISTRY[entity_type] = AdminDeleteEntry(
        entity_type=entity_type,
        table=table,
        label_field=label_field,
        repo_resolver=repo_resolver,
    )


def get_entry(entity_type: str) -> AdminDeleteEntry | None:
    """Look up an admin-delete entry by entity_type.

    Args:
        entity_type: The entity type to look up.

    Returns:
        AdminDeleteEntry if found, None otherwise.
    """
    return _REGISTRY.get(entity_type)


def all_entity_types() -> list[str]:
    """Return a sorted list of all registered entity types.

    Returns:
        Sorted list of entity type strings.
    """
    return sorted(_REGISTRY.keys())
