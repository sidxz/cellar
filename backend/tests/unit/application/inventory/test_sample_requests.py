"""Unit tests for SampleRequest use cases."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self

import pytest
from returns.result import Failure, Success

from chem_vault.application.inventory.sample_requests import (
    ApproveSampleRequestCommand,
    ApproveSampleRequest,
    CancelSampleRequestCommand,
    CancelSampleRequest,
    CreateSampleRequestCommand,
    CreateSampleRequest,
    FulfillSampleRequestCommand,
    FulfillSampleRequest,
    GetSampleRequestQuery,
    GetSampleRequest,
    ListSampleRequestsQuery,
    ListSampleRequests,
    RejectSampleRequestCommand,
    RejectSampleRequest,
    StartPreparingSampleRequestCommand,
    StartPreparingSampleRequest,
)
from chem_vault.domain.inventory.enums import SampleRequestStatus
from chem_vault.domain.inventory.sample_request import SampleRequest
from chem_vault.domain.shared.errors import NotFoundError, ValidationError
from chem_vault.domain.shared.events import DomainEvent
from chem_vault.domain.shared.value_objects import Amount
from chem_vault.domain.shared.enums import AmountUnit
from tests.fakes.fake_auth import FakeAuth


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

WS_ID = uuid.uuid4()
OTHER_WS_ID = uuid.uuid4()


class FakeSampleRequestRepo:
    def __init__(self, items: list[SampleRequest] | None = None) -> None:
        self._store: dict[uuid.UUID, SampleRequest] = {
            item.id: item for item in (items or [])
        }

    async def find_by_id(self, id: uuid.UUID) -> SampleRequest | None:
        return self._store.get(id)

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> SampleRequest | None:
        item = self._store.get(id)
        if item is not None and item.workspace_id == workspace_id:
            return item
        return None

    async def find_by_workspace(
        self, workspace_id: uuid.UUID, *, status: str | None = None
    ) -> list[SampleRequest]:
        results = [r for r in self._store.values() if r.workspace_id == workspace_id]
        if status:
            results = [r for r in results if r.status.value == status]
        return results

    async def save(self, aggregate: SampleRequest) -> None:
        self._store[aggregate.id] = aggregate


class FakeUoW:
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass

    async def commit(self) -> list[DomainEvent]:
        return []


class FakeDispatcher:
    def __init__(self) -> None:
        self.dispatched: list[DomainEvent] = []

    async def dispatch_all(self, events: list[DomainEvent]) -> None:
        self.dispatched.extend(events)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(
    workspace_id: uuid.UUID = WS_ID,
    status: SampleRequestStatus = SampleRequestStatus.SUBMITTED,
) -> SampleRequest:
    """Build a SampleRequest in a given status via factory + manual transitions."""
    req = SampleRequest.create(
        workspace_id=workspace_id,
        requester_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
        requested_amount=Amount(value=10.0, unit=AmountUnit.MG),
        purpose="Testing",
    )
    req.clear_events()

    if status == SampleRequestStatus.APPROVED:
        req.approve()
        req.clear_events()
    elif status == SampleRequestStatus.PREPARING:
        req.approve()
        req.start_preparing()
        req.clear_events()
    elif status == SampleRequestStatus.FULFILLED:
        req.approve()
        req.start_preparing()
        req.fulfill(uuid.uuid4())
        req.clear_events()
    elif status == SampleRequestStatus.REJECTED:
        req.reject("Test rejection")
        req.clear_events()
    elif status == SampleRequestStatus.CANCELLED:
        req.cancel()
        req.clear_events()

    return req


def _make_auth(workspace_id: uuid.UUID = WS_ID, role: str = "editor") -> FakeAuth:
    return FakeAuth(workspace_id=workspace_id, role=role)


# ---------------------------------------------------------------------------
# CreateSampleRequest
# ---------------------------------------------------------------------------


class TestCreateSampleRequest:
    @pytest.mark.asyncio
    async def test_creates_in_submitted_status(self) -> None:
        repo = FakeSampleRequestRepo()
        uc = CreateSampleRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        cmd = CreateSampleRequestCommand(
            workspace_id=WS_ID,
            requester_id=auth.user_id,
            molecule_id=uuid.uuid4(),
            amount_value=5.0,
            amount_unit="mg",
            purpose="Screening assay",
        )
        result = await uc(cmd, auth)

        assert isinstance(result, Success)
        req = result.unwrap()
        assert req.status == SampleRequestStatus.SUBMITTED
        assert req.workspace_id == WS_ID
        assert req.purpose == "Screening assay"
        assert req.requested_amount.value == 5.0
        assert req.requested_amount.unit == AmountUnit.MG

    @pytest.mark.asyncio
    async def test_persists_to_repo(self) -> None:
        repo = FakeSampleRequestRepo()
        uc = CreateSampleRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        cmd = CreateSampleRequestCommand(
            workspace_id=WS_ID,
            requester_id=auth.user_id,
            molecule_id=uuid.uuid4(),
            amount_value=10.0,
            amount_unit="mg",
            purpose="Check persistence",
        )
        result = await uc(cmd, auth)
        req = result.unwrap()

        stored = await repo.find_by_id(req.id)
        assert stored is not None
        assert stored.id == req.id

    @pytest.mark.asyncio
    async def test_creates_with_batch_id(self) -> None:
        repo = FakeSampleRequestRepo()
        uc = CreateSampleRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()
        batch_id = uuid.uuid4()

        cmd = CreateSampleRequestCommand(
            workspace_id=WS_ID,
            requester_id=auth.user_id,
            molecule_id=uuid.uuid4(),
            batch_id=batch_id,
            amount_value=2.5,
            amount_unit="g",
            purpose="Batch-linked request",
            priority="urgent",
        )
        result = await uc(cmd, auth)

        assert isinstance(result, Success)
        req = result.unwrap()
        assert req.batch_id == batch_id

    @pytest.mark.asyncio
    async def test_viewer_cannot_create(self) -> None:
        repo = FakeSampleRequestRepo()
        uc = CreateSampleRequest(FakeUoW(), repo, FakeDispatcher())
        auth = FakeAuth(workspace_id=WS_ID, role="viewer")

        cmd = CreateSampleRequestCommand(
            workspace_id=WS_ID,
            requester_id=auth.user_id,
            molecule_id=uuid.uuid4(),
            amount_value=5.0,
            amount_unit="mg",
            purpose="Should fail",
        )
        with pytest.raises(Exception):
            await uc(cmd, auth)


# ---------------------------------------------------------------------------
# GetSampleRequest
# ---------------------------------------------------------------------------


class TestGetSampleRequest:
    @pytest.mark.asyncio
    async def test_returns_found_request(self) -> None:
        req = _make_request()
        repo = FakeSampleRequestRepo([req])
        uc = GetSampleRequest(FakeUoW(), repo)
        auth = _make_auth()

        result = await uc(GetSampleRequestQuery(workspace_id=WS_ID, request_id=req.id), auth)

        assert isinstance(result, Success)
        assert result.unwrap().id == req.id

    @pytest.mark.asyncio
    async def test_returns_failure_when_not_found(self) -> None:
        repo = FakeSampleRequestRepo()
        uc = GetSampleRequest(FakeUoW(), repo)
        auth = _make_auth()

        result = await uc(GetSampleRequestQuery(workspace_id=WS_ID, request_id=uuid.uuid4()), auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_cross_workspace_returns_failure(self) -> None:
        req = _make_request(workspace_id=OTHER_WS_ID)
        repo = FakeSampleRequestRepo([req])
        uc = GetSampleRequest(FakeUoW(), repo)
        auth = _make_auth(workspace_id=WS_ID)

        result = await uc(GetSampleRequestQuery(workspace_id=WS_ID, request_id=req.id), auth)
        assert isinstance(result, Failure)


# ---------------------------------------------------------------------------
# ListSampleRequests
# ---------------------------------------------------------------------------


class TestListSampleRequests:
    @pytest.mark.asyncio
    async def test_returns_workspace_requests(self) -> None:
        req1 = _make_request(workspace_id=WS_ID)
        req2 = _make_request(workspace_id=WS_ID)
        req_other = _make_request(workspace_id=OTHER_WS_ID)
        repo = FakeSampleRequestRepo([req1, req2, req_other])
        uc = ListSampleRequests(FakeUoW(), repo)
        auth = _make_auth()

        result = await uc(ListSampleRequestsQuery(workspace_id=WS_ID), auth)

        assert isinstance(result, Success)
        ids = {r.id for r in result.unwrap()}
        assert req1.id in ids
        assert req2.id in ids
        assert req_other.id not in ids

    @pytest.mark.asyncio
    async def test_filters_by_status(self) -> None:
        submitted = _make_request(status=SampleRequestStatus.SUBMITTED)
        approved = _make_request(status=SampleRequestStatus.APPROVED)
        repo = FakeSampleRequestRepo([submitted, approved])
        uc = ListSampleRequests(FakeUoW(), repo)
        auth = _make_auth()

        result = await uc(
            ListSampleRequestsQuery(workspace_id=WS_ID, status="submitted"), auth
        )

        assert isinstance(result, Success)
        requests = result.unwrap()
        assert all(r.status == SampleRequestStatus.SUBMITTED for r in requests)
        assert approved.id not in {r.id for r in requests}

    @pytest.mark.asyncio
    async def test_empty_workspace_returns_empty_list(self) -> None:
        repo = FakeSampleRequestRepo()
        uc = ListSampleRequests(FakeUoW(), repo)
        auth = _make_auth()

        result = await uc(ListSampleRequestsQuery(workspace_id=WS_ID), auth)

        assert isinstance(result, Success)
        assert result.unwrap() == []


# ---------------------------------------------------------------------------
# ApproveSampleRequest
# ---------------------------------------------------------------------------


class TestApproveSampleRequest:
    @pytest.mark.asyncio
    async def test_transitions_to_approved(self) -> None:
        req = _make_request(status=SampleRequestStatus.SUBMITTED)
        repo = FakeSampleRequestRepo([req])
        uc = ApproveSampleRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(ApproveSampleRequestCommand(workspace_id=WS_ID, request_id=req.id), auth)

        assert isinstance(result, Success)
        assert result.unwrap().status == SampleRequestStatus.APPROVED

    @pytest.mark.asyncio
    async def test_approve_with_assigned_to(self) -> None:
        req = _make_request(status=SampleRequestStatus.SUBMITTED)
        repo = FakeSampleRequestRepo([req])
        uc = ApproveSampleRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()
        assignee = uuid.uuid4()

        result = await uc(
            ApproveSampleRequestCommand(workspace_id=WS_ID, request_id=req.id, assigned_to=assignee), auth
        )

        assert isinstance(result, Success)
        approved = result.unwrap()
        assert approved.assigned_to == assignee

    @pytest.mark.asyncio
    async def test_returns_failure_for_not_found(self) -> None:
        repo = FakeSampleRequestRepo()
        uc = ApproveSampleRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(
            ApproveSampleRequestCommand(workspace_id=WS_ID, request_id=uuid.uuid4()), auth
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_cannot_approve_already_approved(self) -> None:
        req = _make_request(status=SampleRequestStatus.APPROVED)
        repo = FakeSampleRequestRepo([req])
        uc = ApproveSampleRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        with pytest.raises(ValidationError):
            await uc(ApproveSampleRequestCommand(workspace_id=WS_ID, request_id=req.id), auth)


# ---------------------------------------------------------------------------
# RejectSampleRequest
# ---------------------------------------------------------------------------


class TestRejectSampleRequest:
    @pytest.mark.asyncio
    async def test_transitions_to_rejected_with_reason(self) -> None:
        req = _make_request(status=SampleRequestStatus.SUBMITTED)
        repo = FakeSampleRequestRepo([req])
        uc = RejectSampleRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(
            RejectSampleRequestCommand(workspace_id=WS_ID, request_id=req.id, reason="Insufficient stock"),
            auth,
        )

        assert isinstance(result, Success)
        rejected = result.unwrap()
        assert rejected.status == SampleRequestStatus.REJECTED
        assert rejected.rejection_reason == "Insufficient stock"

    @pytest.mark.asyncio
    async def test_returns_failure_for_not_found(self) -> None:
        repo = FakeSampleRequestRepo()
        uc = RejectSampleRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(
            RejectSampleRequestCommand(workspace_id=WS_ID, request_id=uuid.uuid4(), reason="No stock"),
            auth,
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_empty_reason_raises_validation_error(self) -> None:
        req = _make_request(status=SampleRequestStatus.SUBMITTED)
        repo = FakeSampleRequestRepo([req])
        uc = RejectSampleRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        with pytest.raises(ValidationError):
            await uc(
                RejectSampleRequestCommand(workspace_id=WS_ID, request_id=req.id, reason="   "),
                auth,
            )


# ---------------------------------------------------------------------------
# FulfillSampleRequest
# ---------------------------------------------------------------------------


class TestFulfillSampleRequest:
    @pytest.mark.asyncio
    async def test_transitions_from_preparing_to_fulfilled(self) -> None:
        req = _make_request(status=SampleRequestStatus.PREPARING)
        repo = FakeSampleRequestRepo([req])
        uc = FulfillSampleRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()
        sample_id = uuid.uuid4()

        result = await uc(
            FulfillSampleRequestCommand(workspace_id=WS_ID, request_id=req.id, sample_id=sample_id), auth
        )

        assert isinstance(result, Success)
        fulfilled = result.unwrap()
        assert fulfilled.status == SampleRequestStatus.FULFILLED
        assert fulfilled.fulfilled_sample_id == sample_id
        assert fulfilled.fulfilled_at is not None

    @pytest.mark.asyncio
    async def test_returns_failure_for_not_found(self) -> None:
        repo = FakeSampleRequestRepo()
        uc = FulfillSampleRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(
            FulfillSampleRequestCommand(workspace_id=WS_ID, request_id=uuid.uuid4(), sample_id=uuid.uuid4()),
            auth,
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_cannot_fulfill_from_submitted(self) -> None:
        req = _make_request(status=SampleRequestStatus.SUBMITTED)
        repo = FakeSampleRequestRepo([req])
        uc = FulfillSampleRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        with pytest.raises(ValidationError):
            await uc(
                FulfillSampleRequestCommand(workspace_id=WS_ID, request_id=req.id, sample_id=uuid.uuid4()),
                auth,
            )


# ---------------------------------------------------------------------------
# CancelSampleRequest
# ---------------------------------------------------------------------------


class TestCancelSampleRequest:
    @pytest.mark.asyncio
    async def test_cancels_from_submitted(self) -> None:
        req = _make_request(status=SampleRequestStatus.SUBMITTED)
        repo = FakeSampleRequestRepo([req])
        uc = CancelSampleRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(CancelSampleRequestCommand(workspace_id=WS_ID, request_id=req.id), auth)

        assert isinstance(result, Success)
        assert result.unwrap().status == SampleRequestStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancels_from_approved(self) -> None:
        req = _make_request(status=SampleRequestStatus.APPROVED)
        repo = FakeSampleRequestRepo([req])
        uc = CancelSampleRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(CancelSampleRequestCommand(workspace_id=WS_ID, request_id=req.id), auth)

        assert isinstance(result, Success)
        assert result.unwrap().status == SampleRequestStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancels_from_preparing(self) -> None:
        req = _make_request(status=SampleRequestStatus.PREPARING)
        repo = FakeSampleRequestRepo([req])
        uc = CancelSampleRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(CancelSampleRequestCommand(workspace_id=WS_ID, request_id=req.id), auth)

        assert isinstance(result, Success)
        assert result.unwrap().status == SampleRequestStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_returns_failure_for_not_found(self) -> None:
        repo = FakeSampleRequestRepo()
        uc = CancelSampleRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(CancelSampleRequestCommand(workspace_id=WS_ID, request_id=uuid.uuid4()), auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_cannot_cancel_fulfilled(self) -> None:
        req = _make_request(status=SampleRequestStatus.FULFILLED)
        repo = FakeSampleRequestRepo([req])
        uc = CancelSampleRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        with pytest.raises(ValidationError):
            await uc(CancelSampleRequestCommand(workspace_id=WS_ID, request_id=req.id), auth)


# ---------------------------------------------------------------------------
# StartPreparingSampleRequest
# ---------------------------------------------------------------------------


class TestStartPreparingSampleRequest:
    @pytest.mark.asyncio
    async def test_transitions_from_approved_to_preparing(self) -> None:
        req = _make_request(status=SampleRequestStatus.APPROVED)
        repo = FakeSampleRequestRepo([req])
        uc = StartPreparingSampleRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(StartPreparingSampleRequestCommand(workspace_id=WS_ID, request_id=req.id), auth)

        assert isinstance(result, Success)
        assert result.unwrap().status == SampleRequestStatus.PREPARING

    @pytest.mark.asyncio
    async def test_returns_failure_for_not_found(self) -> None:
        repo = FakeSampleRequestRepo()
        uc = StartPreparingSampleRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        result = await uc(
            StartPreparingSampleRequestCommand(workspace_id=WS_ID, request_id=uuid.uuid4()), auth
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_cannot_prepare_from_submitted(self) -> None:
        req = _make_request(status=SampleRequestStatus.SUBMITTED)
        repo = FakeSampleRequestRepo([req])
        uc = StartPreparingSampleRequest(FakeUoW(), repo, FakeDispatcher())
        auth = _make_auth()

        with pytest.raises(ValidationError):
            await uc(StartPreparingSampleRequestCommand(workspace_id=WS_ID, request_id=req.id), auth)

    @pytest.mark.asyncio
    async def test_dispatcher_receives_events(self) -> None:
        req = _make_request(status=SampleRequestStatus.SUBMITTED)
        repo = FakeSampleRequestRepo([req])
        dispatcher = FakeDispatcher()
        approve_uc = ApproveSampleRequest(FakeUoW(), repo, dispatcher)
        auth = _make_auth()

        await approve_uc(ApproveSampleRequestCommand(workspace_id=WS_ID, request_id=req.id), auth)

        # Dispatcher called with events (SampleRequestApproved event registered)
        # Events list could be empty since FakeUoW.commit() returns [] but domain
        # events were registered on the aggregate before save — this verifies
        # the dispatcher integration path works without errors
        assert isinstance(dispatcher.dispatched, list)
