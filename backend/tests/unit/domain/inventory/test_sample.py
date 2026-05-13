"""Tests for Sample aggregate root — state machine, amount tracking, events."""

import uuid

import pytest

from cellar.domain.inventory.enums import ContainerType, SampleStatus
from cellar.domain.inventory.events import (
    LowStockDetected,
    SampleAliquoted,
    SampleCreated,
    SampleDepleted,
    SampleDisposed,
    SampleMoved,
    SampleQuarantined,
)
from cellar.domain.inventory.sample import Sample
from cellar.domain.shared.enums import AmountUnit
from cellar.domain.shared.errors import ValidationError
from cellar.domain.shared.value_objects import Amount, Barcode


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def batch_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_sample(
    workspace_id: uuid.UUID,
    batch_id: uuid.UUID,
    *,
    amount: float = 10.0,
    low_stock_threshold: float | None = None,
) -> Sample:
    return Sample.create(
        workspace_id=workspace_id,
        batch_id=batch_id,
        barcode=Barcode(value="SMP-001"),
        container_type=ContainerType.VIAL,
        amount=Amount(value=amount, unit=AmountUnit.MG),
        low_stock_threshold=low_stock_threshold,
    )


class TestSampleCreation:
    def test_create_sets_all_fields(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        sample = _make_sample(workspace_id, batch_id)

        assert sample.workspace_id == workspace_id
        assert sample.batch_id == batch_id
        assert sample.barcode.value == "SMP-001"
        assert sample.container_type == ContainerType.VIAL
        assert sample.amount.value == 10.0
        assert sample.status == SampleStatus.AVAILABLE
        assert sample.freeze_thaw_count == 0
        assert sample.version == 1

    def test_create_emits_event(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        sample = _make_sample(workspace_id, batch_id)
        events = sample.collect_events()

        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, SampleCreated)
        assert evt.batch_id == batch_id
        assert evt.barcode == "SMP-001"

    def test_negative_amount_raises(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValueError, match="must be >= 0"):
            _make_sample(workspace_id, batch_id, amount=-1)

    def test_all_container_types(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        for ct in ContainerType:
            sample = Sample.create(
                workspace_id=workspace_id,
                batch_id=batch_id,
                barcode=Barcode(value=f"SMP-{ct.value}"),
                container_type=ct,
                amount=Amount(value=1.0, unit=AmountUnit.MG),
            )
            assert sample.container_type == ct


class TestSampleAliquot:
    def test_aliquot_reduces_amount(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        sample = _make_sample(workspace_id, batch_id, amount=10.0)
        sample.clear_events()
        sample.aliquot(3.0)

        assert sample.amount.value == 7.0
        events = sample.collect_events()
        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, SampleAliquoted)
        assert evt.amount_removed == 3.0
        assert evt.remaining_amount == 7.0

    def test_aliquot_to_zero_depletes(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        sample = _make_sample(workspace_id, batch_id, amount=5.0)
        sample.clear_events()
        sample.aliquot(5.0)

        assert sample.amount.value == 0
        assert sample.status == SampleStatus.DEPLETED
        events = sample.collect_events()
        event_types = {type(e) for e in events}
        assert SampleAliquoted in event_types
        assert SampleDepleted in event_types

    def test_aliquot_triggers_low_stock(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        sample = _make_sample(workspace_id, batch_id, amount=10.0, low_stock_threshold=3.0)
        sample.clear_events()
        sample.aliquot(8.0)

        assert sample.amount.value == 2.0
        events = sample.collect_events()
        low_stock = [e for e in events if isinstance(e, LowStockDetected)]
        assert len(low_stock) == 1
        assert low_stock[0].current_amount == 2.0
        assert low_stock[0].threshold == 3.0

    def test_aliquot_more_than_available_raises(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        sample = _make_sample(workspace_id, batch_id, amount=5.0)
        with pytest.raises(ValidationError, match="Cannot remove"):
            sample.aliquot(6.0)

    def test_aliquot_zero_raises(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        sample = _make_sample(workspace_id, batch_id, amount=5.0)
        with pytest.raises(ValidationError, match="must be > 0"):
            sample.aliquot(0)

    def test_aliquot_negative_raises(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        sample = _make_sample(workspace_id, batch_id, amount=5.0)
        with pytest.raises(ValidationError, match="must be > 0"):
            sample.aliquot(-1)

    def test_cannot_aliquot_depleted(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        sample = _make_sample(workspace_id, batch_id, amount=1.0)
        sample.aliquot(1.0)
        with pytest.raises(ValidationError, match="terminal state"):
            sample.aliquot(0.5)

    def test_cannot_aliquot_disposed(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        sample = _make_sample(workspace_id, batch_id)
        sample.dispose(reason="expired")
        with pytest.raises(ValidationError, match="terminal state"):
            sample.aliquot(1.0)


class TestSampleStateTransitions:
    def test_available_to_quarantined(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        sample = _make_sample(workspace_id, batch_id)
        sample.clear_events()
        sample.quarantine(reason="QC failure")

        assert sample.status == SampleStatus.QUARANTINED
        events = sample.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], SampleQuarantined)
        assert events[0].reason == "QC failure"

    def test_quarantined_to_available(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        sample = _make_sample(workspace_id, batch_id)
        sample.quarantine(reason="QC issue")
        sample.clear_quarantine()
        assert sample.status == SampleStatus.AVAILABLE

    def test_quarantined_to_disposed(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        sample = _make_sample(workspace_id, batch_id)
        sample.quarantine(reason="QC issue")
        sample.dispose(reason="failed QC")
        assert sample.status == SampleStatus.DISPOSED

    def test_available_to_expired(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        sample = _make_sample(workspace_id, batch_id)
        sample.expire()
        assert sample.status == SampleStatus.EXPIRED

    def test_expired_to_disposed(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        sample = _make_sample(workspace_id, batch_id)
        sample.expire()
        sample.dispose(reason="cleanup")
        assert sample.status == SampleStatus.DISPOSED

    def test_available_to_disposed(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        sample = _make_sample(workspace_id, batch_id)
        sample.clear_events()
        sample.dispose(reason="no longer needed")

        assert sample.status == SampleStatus.DISPOSED
        events = sample.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], SampleDisposed)

    def test_depleted_is_terminal(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        sample = _make_sample(workspace_id, batch_id, amount=1.0)
        sample.aliquot(1.0)
        assert sample.status == SampleStatus.DEPLETED

        with pytest.raises(ValidationError):
            sample.quarantine(reason="test")
        with pytest.raises(ValidationError):
            sample.dispose()
        with pytest.raises(ValidationError):
            sample.expire()

    def test_disposed_is_terminal(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        sample = _make_sample(workspace_id, batch_id)
        sample.dispose(reason="cleanup")

        with pytest.raises(ValidationError):
            sample.quarantine(reason="test")
        with pytest.raises(ValidationError):
            sample.expire()

    def test_invalid_transition_raises(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        sample = _make_sample(workspace_id, batch_id)
        sample.expire()
        # expired → quarantined is not allowed
        with pytest.raises(ValidationError, match="Cannot transition"):
            sample.quarantine(reason="test")


class TestSampleMove:
    def test_move_to_location(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        sample = _make_sample(workspace_id, batch_id)
        sample.clear_events()
        loc = uuid.uuid4()
        sample.move_to(loc)

        assert sample.location_id == loc
        events = sample.collect_events()
        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, SampleMoved)
        assert evt.old_location_id is None
        assert evt.new_location_id == loc

    def test_move_between_locations(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        sample = _make_sample(workspace_id, batch_id)
        loc1 = uuid.uuid4()
        loc2 = uuid.uuid4()
        sample.move_to(loc1)
        sample.clear_events()
        sample.move_to(loc2)

        events = sample.collect_events()
        assert events[0].old_location_id == loc1  # type: ignore[union-attr]
        assert events[0].new_location_id == loc2  # type: ignore[union-attr]

    def test_cannot_move_disposed(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        sample = _make_sample(workspace_id, batch_id)
        sample.dispose()
        with pytest.raises(ValidationError, match="terminal state"):
            sample.move_to(uuid.uuid4())


class TestSampleFreezeThaw:
    def test_record_freeze_thaw(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        sample = _make_sample(workspace_id, batch_id)
        assert sample.freeze_thaw_count == 0
        sample.record_freeze_thaw()
        assert sample.freeze_thaw_count == 1
        sample.record_freeze_thaw()
        assert sample.freeze_thaw_count == 2

    def test_cannot_freeze_thaw_disposed(
        self, workspace_id: uuid.UUID, batch_id: uuid.UUID
    ) -> None:
        sample = _make_sample(workspace_id, batch_id)
        sample.dispose()
        with pytest.raises(ValidationError, match="terminal state"):
            sample.record_freeze_thaw()
