"""Repository protocol for the domain layer."""

from __future__ import annotations

import uuid
from typing import Protocol, TypeVar, runtime_checkable

from chem_vault.domain.shared.entity import AggregateRoot

T = TypeVar("T", bound=AggregateRoot)


@runtime_checkable
class Repository(Protocol[T]):
    """Generic repository interface.

    Concrete implementations live in the infrastructure layer.
    Raises ``NotFoundError`` on missing entities and
    ``ConcurrencyConflictError`` on version mismatches.
    """

    async def find_by_id(self, id: uuid.UUID) -> T | None: ...

    async def save(self, aggregate: T) -> None: ...
