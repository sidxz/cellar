"""Registry of entity types that support admin hard-delete (Tier 1).

The registry is populated at DI bootstrap time via ``register_admin_delete``.
It holds **metadata only** — entity_type, table, label_field.

The mapping from entity_type to a usable repo (``AdminDeletableRepoMap``) is
built at DI bootstrap and injected into ``AdminHardDelete`` directly, removing
the service-locator anti-pattern that previously lived in ``repo_resolver``.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


class AdminDeletableRepo(Protocol):
    """Protocol for repositories that support admin hard-delete."""

    async def find_by_id(self, workspace_id: uuid.UUID, id: uuid.UUID) -> object: ...

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...


# Type alias — DI populates this mapping and injects it into AdminHardDelete.
AdminDeletableRepoMap = Mapping[str, AdminDeletableRepo]


@dataclass(frozen=True)
class AdminDeleteEntry:
    """Registry entry for an admin-deletable entity type (metadata only)."""

    entity_type: str
    table: str
    label_field: str | None


# entity_type -> AdminDeleteEntry. Populated by register_admin_delete().
_REGISTRY: dict[str, AdminDeleteEntry] = {}


def register_admin_delete(
    *,
    entity_type: str,
    table: str,
    label_field: str | None,
) -> None:
    """Register an entity type as admin-deletable (Tier 1).

    Args:
        entity_type: Unique identifier for the entity type (e.g., "vocabulary").
        table: Database table name.
        label_field: Optional field name for display labels (e.g., "name").

    Note:
        Idempotent — re-registration of the same entity_type is a no-op.
        This supports test setups that call create_container multiple times
        in one process.
    """
    if entity_type in _REGISTRY:
        # Idempotent re-registration (e.g. multiple test containers calling
        # create_container in the same process). Skip silently.
        return
    _REGISTRY[entity_type] = AdminDeleteEntry(
        entity_type=entity_type,
        table=table,
        label_field=label_field,
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
