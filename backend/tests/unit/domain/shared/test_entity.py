"""Tests for Entity and AggregateRoot base classes."""

import uuid
from datetime import UTC, datetime

from cellar.domain.shared.entity import AggregateRoot, Entity
from cellar.domain.shared.events import DomainEvent


class TestEntity:
    def test_auto_id(self) -> None:
        e = Entity()
        assert isinstance(e.id, uuid.UUID)

    def test_explicit_id(self) -> None:
        eid = uuid.uuid4()
        e = Entity(id=eid)
        assert e.id == eid

    def test_timestamps_default_to_now(self) -> None:
        before = datetime.now(UTC)
        e = Entity()
        after = datetime.now(UTC)
        assert before <= e.created_at <= after
        assert before <= e.updated_at <= after

    def test_equality_by_id(self) -> None:
        eid = uuid.uuid4()
        a = Entity(id=eid)
        b = Entity(id=eid)
        assert a == b

    def test_inequality(self) -> None:
        assert Entity() != Entity()

    def test_equality_with_non_entity(self) -> None:
        assert Entity().__eq__("not an entity") is NotImplemented

    def test_hash_by_id(self) -> None:
        eid = uuid.uuid4()
        a = Entity(id=eid)
        b = Entity(id=eid)
        assert hash(a) == hash(b)
        assert len({a, b}) == 1


class TestAggregateRoot:


    def test_register_and_collect_events(self) -> None:
        ar = AggregateRoot()
        event = DomainEvent(aggregate_id=ar.id, aggregate_type="Test", workspace_id=uuid.uuid4())
        ar.register_event(event)
        events = ar.collect_events()
        assert len(events) == 1
        assert events[0] is event

    def test_collect_returns_copy(self) -> None:
        ar = AggregateRoot()
        ar.register_event(DomainEvent(aggregate_id=ar.id, aggregate_type="Test", workspace_id=uuid.uuid4()))
        events = ar.collect_events()
        events.clear()
        assert len(ar.collect_events()) == 1

    def test_clear_events(self) -> None:
        ar = AggregateRoot()
        ar.register_event(DomainEvent(aggregate_id=ar.id, aggregate_type="Test", workspace_id=uuid.uuid4()))
        ar.clear_events()
        assert ar.collect_events() == []

    def test_no_events_initially(self) -> None:
        assert AggregateRoot().collect_events() == []
