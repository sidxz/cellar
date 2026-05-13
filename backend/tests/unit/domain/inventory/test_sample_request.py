"""Tests for SampleRequest aggregate root."""

import uuid

import pytest

from cellar.domain.inventory.enums import RequestPriority, SampleRequestStatus
from cellar.domain.inventory.events import (
    SampleRequestApproved,
    SampleRequestCreated,
    SampleRequestFulfilled,
    SampleRequestRejected,
)
from cellar.domain.inventory.sample_request import SampleRequest
from cellar.domain.shared.enums import AmountUnit
from cellar.domain.shared.errors import ValidationError
from cellar.domain.shared.value_objects import Amount


@pytest.fixture
def ws_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_request(ws_id: uuid.UUID, **overrides) -> SampleRequest:
    defaults = dict(
        workspace_id=ws_id,
        requester_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
        requested_amount=Amount(value=5.0, unit=AmountUnit.MG),
        purpose="IC50 confirmation study",
    )
    defaults.update(overrides)
    return SampleRequest.create(**defaults)


class TestSampleRequestCreation:
    def test_create_basic(self, ws_id):
        req = _make_request(ws_id)
        assert req.status == SampleRequestStatus.SUBMITTED
        assert req.priority == RequestPriority.ROUTINE
        assert req.requested_amount.value == 5.0

    def test_create_emits_event(self, ws_id):
        req = _make_request(ws_id)
        events = req.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], SampleRequestCreated)

    def test_create_zero_amount_raises(self, ws_id):
        with pytest.raises(ValidationError, match="positive"):
            _make_request(ws_id, requested_amount=Amount(value=0, unit=AmountUnit.MG))

    def test_create_empty_purpose_raises(self, ws_id):
        with pytest.raises(ValidationError, match="Purpose"):
            _make_request(ws_id, purpose="   ")


class TestSampleRequestTransitions:
    def test_approve(self, ws_id):
        req = _make_request(ws_id)
        assignee = uuid.uuid4()
        req.approve(assigned_to=assignee)
        assert req.status == SampleRequestStatus.APPROVED
        assert req.assigned_to == assignee
        assert any(isinstance(e, SampleRequestApproved) for e in req.collect_events())

    def test_approve_then_prepare(self, ws_id):
        req = _make_request(ws_id)
        req.approve()
        req.start_preparing()
        assert req.status == SampleRequestStatus.PREPARING

    def test_fulfill(self, ws_id):
        req = _make_request(ws_id)
        req.approve()
        req.start_preparing()
        sample_id = uuid.uuid4()
        req.fulfill(sample_id)
        assert req.status == SampleRequestStatus.FULFILLED
        assert req.fulfilled_sample_id == sample_id
        assert req.fulfilled_at is not None

    def test_reject_requires_reason(self, ws_id):
        req = _make_request(ws_id)
        with pytest.raises(ValidationError, match="reason"):
            req.reject("   ")

    def test_reject(self, ws_id):
        req = _make_request(ws_id)
        req.reject("Insufficient stock")
        assert req.status == SampleRequestStatus.REJECTED
        assert req.rejection_reason == "Insufficient stock"
        assert any(isinstance(e, SampleRequestRejected) for e in req.collect_events())

    def test_cancel_from_submitted(self, ws_id):
        req = _make_request(ws_id)
        req.cancel()
        assert req.status == SampleRequestStatus.CANCELLED

    def test_cancel_from_approved(self, ws_id):
        req = _make_request(ws_id)
        req.approve()
        req.cancel()
        assert req.status == SampleRequestStatus.CANCELLED

    def test_cancel_from_preparing(self, ws_id):
        req = _make_request(ws_id)
        req.approve()
        req.start_preparing()
        req.cancel()
        assert req.status == SampleRequestStatus.CANCELLED

    def test_cannot_cancel_fulfilled(self, ws_id):
        req = _make_request(ws_id)
        req.approve()
        req.start_preparing()
        req.fulfill(uuid.uuid4())
        with pytest.raises(ValidationError, match="Cannot transition"):
            req.cancel()

    def test_cannot_approve_rejected(self, ws_id):
        req = _make_request(ws_id)
        req.reject("No stock")
        with pytest.raises(ValidationError, match="Cannot transition"):
            req.approve()

    def test_terminal_states(self, ws_id):
        req = _make_request(ws_id)
        req.approve()
        req.start_preparing()
        req.fulfill(uuid.uuid4())
        assert req.is_terminal
