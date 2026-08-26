"""Tests for DomainEvent base class."""

import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from cellar.domain.shared.events import DomainEvent


class TestDomainEvent:
    def test_create_with_defaults(self) -> None:
        agg_id = uuid.uuid4()
        ws_id = uuid.uuid4()
        event = DomainEvent(aggregate_id=agg_id, aggregate_type="Molecule", workspace_id=ws_id)

        assert isinstance(event.event_id, uuid.UUID)
        assert isinstance(event.occurred_at, datetime)
        assert event.occurred_at.tzinfo == UTC
        assert event.aggregate_id == agg_id
        assert event.aggregate_type == "Molecule"
        assert event.workspace_id == ws_id

    def test_immutable(self) -> None:
        event = DomainEvent(aggregate_id=uuid.uuid4(), aggregate_type="X", workspace_id=uuid.uuid4())
        with pytest.raises(FrozenInstanceError):
            event.aggregate_type = "Y"  # type: ignore[misc]

    def test_unique_event_ids(self) -> None:
        a = DomainEvent(aggregate_id=uuid.uuid4(), aggregate_type="X", workspace_id=uuid.uuid4())
        b = DomainEvent(aggregate_id=uuid.uuid4(), aggregate_type="X", workspace_id=uuid.uuid4())
        assert a.event_id != b.event_id
