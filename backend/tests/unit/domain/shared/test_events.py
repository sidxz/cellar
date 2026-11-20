"""Tests for DomainEvent base class."""

import uuid
from datetime import UTC, datetime

from cellar.domain.shared.events import DomainEvent


class TestDomainEvent:
    def test_create_with_defaults(self) -> None:
        event = DomainEvent(
            aggregate_id=uuid.uuid4(), aggregate_type="Molecule", workspace_id=uuid.uuid4()
        )

        assert isinstance(event.event_id, uuid.UUID)
        assert isinstance(event.occurred_at, datetime)
        assert event.occurred_at.tzinfo == UTC

    def test_unique_event_ids(self) -> None:
        a = DomainEvent(aggregate_id=uuid.uuid4(), aggregate_type="X", workspace_id=uuid.uuid4())
        b = DomainEvent(aggregate_id=uuid.uuid4(), aggregate_type="X", workspace_id=uuid.uuid4())
        assert a.event_id != b.event_id
