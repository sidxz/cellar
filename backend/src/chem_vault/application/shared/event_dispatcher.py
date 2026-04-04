"""Event dispatcher protocol — application-layer abstraction.

Concrete implementation lives in infrastructure.messaging.event_dispatcher.
"""

from __future__ import annotations

from typing import Protocol

from chem_vault.domain.shared.events import DomainEvent


class EventDispatcherProtocol(Protocol):
    """Dispatch domain events to registered handlers."""

    async def dispatch_all(self, events: list[DomainEvent]) -> None: ...
