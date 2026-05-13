"""Entity and AggregateRoot base classes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from cellar.domain.shared.events import DomainEvent


class Entity:
    """Base class for all domain entities.

    Identity-based equality — two entities are equal iff they share the same id.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        self.id = id or uuid.uuid4()
        now = datetime.now(UTC)
        self.created_at = created_at or now
        self.updated_at = updated_at or now

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Entity):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(id={self.id})"


class AggregateRoot(Entity):
    """Base class for aggregate roots.

    Extends Entity with:
    - ``version`` for optimistic concurrency control
    - Domain event collection for post-commit dispatch
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)
        self.version = version
        self._domain_events: list[DomainEvent] = []

    def register_event(self, event: DomainEvent) -> None:
        """Queue a domain event for post-commit dispatch."""
        self._domain_events.append(event)

    def collect_events(self) -> list[DomainEvent]:
        """Return a copy of pending events."""
        return list(self._domain_events)

    def clear_events(self) -> None:
        """Clear pending events (called after successful dispatch)."""
        self._domain_events.clear()
