"""In-process domain event dispatcher.

Synchronous dispatch — handlers run in the same transaction context.
Multiple handlers can be registered per event type.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from chem_vault.domain.shared.events import DomainEvent

logger = structlog.get_logger(__name__)

# Handler signature: async callable that takes a DomainEvent subclass
EventHandler = Callable[[Any], Awaitable[None]]


class EventDispatcher:
    """Registry + dispatcher for domain event handlers.

    Usage::

        dispatcher = EventDispatcher()
        dispatcher.register(MoleculeRegistered, audit_handler)
        dispatcher.register(MoleculeRegistered, notification_handler)

        # After UoW.commit() returns events:
        await dispatcher.dispatch_all(events)
    """

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[EventHandler]] = defaultdict(list)

    def register(
        self, event_type: type[DomainEvent], handler: EventHandler
    ) -> None:
        """Register a handler for a specific event type."""
        self._handlers[event_type].append(handler)

    async def dispatch(self, event: DomainEvent) -> None:
        """Dispatch a single event to all registered handlers.

        Handlers are called in registration order. If a handler raises,
        the exception propagates (fail-fast for in-process dispatch).

        Supports base-class handlers: a handler registered for ``DomainEvent``
        receives all events (catch-all).
        """
        event_type = type(event)

        # Exact-match handlers
        for handler in self._handlers.get(event_type, []):
            logger.debug(
                "Dispatching %s to %s",
                event_type.__name__,
                getattr(handler, "__qualname__", repr(handler)),
            )
            await handler(event)

        # Base-class catch-all handlers (e.g., DomainEvent → audit)
        if event_type is not DomainEvent:
            for handler in self._handlers.get(DomainEvent, []):
                logger.debug(
                    "Dispatching %s to catch-all %s",
                    event_type.__name__,
                    getattr(handler, "__qualname__", repr(handler)),
                )
                await handler(event)

    async def dispatch_all(self, events: list[DomainEvent]) -> None:
        """Dispatch a batch of events (e.g., from UoW.commit())."""
        for event in events:
            await self.dispatch(event)
