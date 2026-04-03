"""Tests for DomainEvent base class."""

import uuid
from dataclasses import FrozenInstanceError, dataclass
from datetime import UTC, datetime

import pytest

from chem_vault.domain.shared.events import DomainEvent


class TestDomainEvent:
    def test_create_with_defaults(self) -> None:
        agg_id = uuid.uuid4()
        event = DomainEvent(aggregate_id=agg_id, aggregate_type="Molecule")

        assert isinstance(event.event_id, uuid.UUID)
        assert isinstance(event.occurred_at, datetime)
        assert event.occurred_at.tzinfo == UTC
        assert event.aggregate_id == agg_id
        assert event.aggregate_type == "Molecule"

    def test_immutable(self) -> None:
        event = DomainEvent(aggregate_id=uuid.uuid4(), aggregate_type="X")
        with pytest.raises(FrozenInstanceError):
            event.aggregate_type = "Y"  # type: ignore[misc]

    def test_unique_event_ids(self) -> None:
        a = DomainEvent(aggregate_id=uuid.uuid4(), aggregate_type="X")
        b = DomainEvent(aggregate_id=uuid.uuid4(), aggregate_type="X")
        assert a.event_id != b.event_id

    def test_subclass(self) -> None:
        @dataclass(frozen=True, kw_only=True)
        class MoleculeRegistered(DomainEvent):
            registration_number: str

        event = MoleculeRegistered(
            aggregate_id=uuid.uuid4(),
            aggregate_type="Molecule",
            registration_number="CV-00001",
        )
        assert event.registration_number == "CV-00001"
        assert isinstance(event, DomainEvent)
