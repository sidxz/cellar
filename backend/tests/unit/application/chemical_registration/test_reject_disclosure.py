"""Tests for RejectDisclosure use case."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self

import pytest
from returns.result import Failure, Success

from cellar.application.chemical_registration.reject_disclosure import (
    RejectDisclosure,
    RejectDisclosureCommand,
)
from cellar.domain.chemical_registration.disclosure_request import DisclosureRequest
from cellar.domain.chemical_registration.enums import DisclosureStatus
from cellar.domain.shared.errors import NotFoundError, ValidationError
from cellar.domain.shared.events import DomainEvent
from tests.fakes.fake_auth import FakeAuth

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

WS_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
TARGET_MOL_ID = uuid.uuid4()


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> list[DomainEvent]:
        self.committed = True
        return []

    async def rollback(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass


class FakeEventDispatcher:
    def __init__(self) -> None:
        self.dispatched: list[DomainEvent] = []

    async def dispatch_all(self, events: list[DomainEvent]) -> None:
        self.dispatched.extend(events)


class FakeDisclosureRepo:
    def __init__(self) -> None:
        self._store: dict[uuid.UUID, DisclosureRequest] = {}

    def add(self, dr: DisclosureRequest) -> None:
        self._store[dr.id] = dr

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> DisclosureRequest | None:
        entity = self._store.get(id)
        if entity is not None and entity.workspace_id != workspace_id:
            return None
        return entity

    async def save(self, aggregate: DisclosureRequest) -> None:
        self._store[aggregate.id] = aggregate


def _make_pending_confirmation_dr() -> DisclosureRequest:
    dr = DisclosureRequest.create(
        workspace_id=WS_ID,
        molecule_id=uuid.uuid4(),
        disclosed_smiles="CCO",
        requested_by=USER_ID,
    )
    dr.start_processing()
    dr.mark_pending_confirmation(
        canonical_smiles="CCO",
        inchi_key="LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
        matched_molecule_id=TARGET_MOL_ID,
    )
    dr.clear_events()
    return dr


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRejectDisclosureSuccess:
    @pytest.mark.asyncio
    async def test_reject_transitions_to_rejected(self) -> None:
        uow = FakeUnitOfWork()
        disclosure_repo = FakeDisclosureRepo()
        dispatcher = FakeEventDispatcher()

        dr = _make_pending_confirmation_dr()
        disclosure_repo.add(dr)

        uc = RejectDisclosure(
            uow=uow,
            disclosure_repo=disclosure_repo,
            dispatcher=dispatcher,
        )

        result = await uc(
            RejectDisclosureCommand(
                workspace_id=WS_ID,
                disclosure_id=dr.id,
                reason="I don't want to merge",
                rejected_by=USER_ID,
            ),
            auth=FakeAuth(),
        )

        assert isinstance(result, Success)
        rejected = result.unwrap()
        assert rejected.status == DisclosureStatus.REJECTED
        assert rejected.resolved_at is not None

    @pytest.mark.asyncio
    async def test_reject_uses_default_reason(self) -> None:
        disclosure_repo = FakeDisclosureRepo()
        dr = _make_pending_confirmation_dr()
        disclosure_repo.add(dr)

        uc = RejectDisclosure(
            uow=FakeUnitOfWork(),
            disclosure_repo=disclosure_repo,
            dispatcher=FakeEventDispatcher(),
        )

        result = await uc(
            RejectDisclosureCommand(
                workspace_id=WS_ID,
                disclosure_id=dr.id,
                rejected_by=USER_ID,
            ),
            auth=FakeAuth(),
        )

        assert isinstance(result, Success)
        assert result.unwrap().conflict_reason == "Merge rejected by user"


class TestRejectDisclosureValidation:
    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        uc = RejectDisclosure(
            uow=FakeUnitOfWork(),
            disclosure_repo=FakeDisclosureRepo(),
            dispatcher=FakeEventDispatcher(),
        )

        result = await uc(
            RejectDisclosureCommand(
                workspace_id=WS_ID,
                disclosure_id=uuid.uuid4(),
                rejected_by=USER_ID,
            ),
            auth=FakeAuth(),
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_wrong_status(self) -> None:
        disclosure_repo = FakeDisclosureRepo()

        dr = DisclosureRequest.create(
            workspace_id=WS_ID,
            molecule_id=uuid.uuid4(),
            disclosed_smiles="CCO",
            requested_by=USER_ID,
        )
        dr.clear_events()
        disclosure_repo.add(dr)

        uc = RejectDisclosure(
            uow=FakeUnitOfWork(),
            disclosure_repo=disclosure_repo,
            dispatcher=FakeEventDispatcher(),
        )

        result = await uc(
            RejectDisclosureCommand(
                workspace_id=WS_ID,
                disclosure_id=dr.id,
                rejected_by=USER_ID,
            ),
            auth=FakeAuth(),
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)
