"""Repository protocol for the domain layer."""

from __future__ import annotations

import uuid
from typing import Protocol, TypeVar, runtime_checkable

from cellar.domain.shared.entity import AggregateRoot

T = TypeVar("T", bound=AggregateRoot)


@runtime_checkable
class Repository(Protocol[T]):
    """Generic repository interface.

    Concrete implementations live in the infrastructure layer.
    Raises ``NotFoundError`` on missing entities and
    ``ConcurrencyConflictError`` on version mismatches.

    Concrete Protocols (e.g. ``MoleculeRepository``) advertise the
    ``find_by_id_in_workspace`` shape so application code cannot ask for a
    cross-tenant unscoped lookup by accident.
    """

    async def save(self, aggregate: T) -> None: ...
