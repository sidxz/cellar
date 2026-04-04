"""Unit tests for the in-process event dispatcher."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest

from chem_vault.domain.shared.events import DomainEvent
from chem_vault.infrastructure.messaging.event_dispatcher import EventDispatcher


@dataclass(frozen=True, kw_only=True)
class FakeRegisteredEvent(DomainEvent):
    """Test event."""

    smiles: str = "CCO"


@dataclass(frozen=True, kw_only=True)
class FakeMergedEvent(DomainEvent):
    """Another test event."""

    target_id: uuid.UUID = uuid.UUID(int=0)


class TestEventDispatcher:
    @pytest.fixture
    def dispatcher(self) -> EventDispatcher:
        return EventDispatcher()

    async def test_dispatch_calls_registered_handler(
        self, dispatcher: EventDispatcher
    ) -> None:
        received: list[DomainEvent] = []

        async def handler(event: FakeRegisteredEvent) -> None:
            received.append(event)

        dispatcher.register(FakeRegisteredEvent, handler)
        event = FakeRegisteredEvent(
            aggregate_id=uuid.uuid4(), aggregate_type="molecule"
        )
        await dispatcher.dispatch(event)

        assert len(received) == 1
        assert received[0] is event

    async def test_dispatch_calls_multiple_handlers(
        self, dispatcher: EventDispatcher
    ) -> None:
        calls: list[str] = []

        async def handler_a(event: FakeRegisteredEvent) -> None:
            calls.append("a")

        async def handler_b(event: FakeRegisteredEvent) -> None:
            calls.append("b")

        dispatcher.register(FakeRegisteredEvent, handler_a)
        dispatcher.register(FakeRegisteredEvent, handler_b)

        event = FakeRegisteredEvent(
            aggregate_id=uuid.uuid4(), aggregate_type="molecule"
        )
        await dispatcher.dispatch(event)

        assert calls == ["a", "b"]

    async def test_dispatch_ignores_unregistered_event_types(
        self, dispatcher: EventDispatcher
    ) -> None:
        received: list[DomainEvent] = []

        async def handler(event: FakeRegisteredEvent) -> None:
            received.append(event)

        dispatcher.register(FakeRegisteredEvent, handler)

        # Dispatch a different event type
        event = FakeMergedEvent(
            aggregate_id=uuid.uuid4(), aggregate_type="molecule"
        )
        await dispatcher.dispatch(event)

        assert len(received) == 0

    async def test_dispatch_all(self, dispatcher: EventDispatcher) -> None:
        received: list[DomainEvent] = []

        async def handler(event: FakeRegisteredEvent) -> None:
            received.append(event)

        dispatcher.register(FakeRegisteredEvent, handler)

        events = [
            FakeRegisteredEvent(
                aggregate_id=uuid.uuid4(), aggregate_type="molecule"
            )
            for _ in range(3)
        ]
        await dispatcher.dispatch_all(events)

        assert len(received) == 3

    async def test_handler_exception_propagates(
        self, dispatcher: EventDispatcher
    ) -> None:
        async def bad_handler(event: FakeRegisteredEvent) -> None:
            raise ValueError("boom")

        dispatcher.register(FakeRegisteredEvent, bad_handler)

        event = FakeRegisteredEvent(
            aggregate_id=uuid.uuid4(), aggregate_type="molecule"
        )
        with pytest.raises(ValueError, match="boom"):
            await dispatcher.dispatch(event)

    async def test_dispatch_all_with_mixed_types(
        self, dispatcher: EventDispatcher
    ) -> None:
        reg_calls: list[str] = []
        merge_calls: list[str] = []

        async def reg_handler(event: FakeRegisteredEvent) -> None:
            reg_calls.append("reg")

        async def merge_handler(event: FakeMergedEvent) -> None:
            merge_calls.append("merge")

        dispatcher.register(FakeRegisteredEvent, reg_handler)
        dispatcher.register(FakeMergedEvent, merge_handler)

        events: list[DomainEvent] = [
            FakeRegisteredEvent(
                aggregate_id=uuid.uuid4(), aggregate_type="molecule"
            ),
            FakeMergedEvent(
                aggregate_id=uuid.uuid4(), aggregate_type="molecule"
            ),
            FakeRegisteredEvent(
                aggregate_id=uuid.uuid4(), aggregate_type="molecule"
            ),
        ]
        await dispatcher.dispatch_all(events)

        assert reg_calls == ["reg", "reg"]
        assert merge_calls == ["merge"]
