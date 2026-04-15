"""Tests for ConfirmDisclosure use case."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.chemical_registration.confirm_disclosure import (
    ConfirmDisclosure,
    ConfirmDisclosureCommand,
)
from chem_vault.application.chemical_registration.merge_service import MergeEvent
from chem_vault.domain.chemical_registration.disclosure_request import DisclosureRequest
from chem_vault.domain.chemical_registration.enums import DisclosureStatus
from chem_vault.domain.shared.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)
from chem_vault.domain.shared.events import DomainEvent
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


def _make_pending_confirmation_dr(
    molecule_id: uuid.UUID | None = None,
) -> DisclosureRequest:
    """Create a DisclosureRequest in PENDING_CONFIRMATION state."""
    mol_id = molecule_id or uuid.uuid4()
    dr = DisclosureRequest.create(
        workspace_id=WS_ID,
        molecule_id=mol_id,
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


class TestConfirmDisclosureSuccess:
    @pytest.mark.asyncio
    async def test_confirm_transitions_to_merged(self) -> None:
        uow = FakeUnitOfWork()
        disclosure_repo = FakeDisclosureRepo()
        dispatcher = FakeEventDispatcher()

        dr = _make_pending_confirmation_dr()
        disclosure_repo.add(dr)

        # Mock merge_service.merge_in_transaction to return success
        mock_merge_event = AsyncMock(spec=MergeEvent)
        merge_service = AsyncMock()
        merge_service.merge_in_transaction = AsyncMock(
            return_value=Success(mock_merge_event)
        )

        uc = ConfirmDisclosure(
            uow=uow,
            disclosure_repo=disclosure_repo,
            merge_service=merge_service,
            dispatcher=dispatcher,
        )

        result = await uc(
            ConfirmDisclosureCommand(
                workspace_id=WS_ID,
                disclosure_id=dr.id,
                confirmed_by=USER_ID,
            ),
            auth=FakeAuth(),
        )

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.was_merged is True
        assert outcome.merged_into_molecule_id == TARGET_MOL_ID
        assert outcome.disclosure_request.status == DisclosureStatus.MERGED

    @pytest.mark.asyncio
    async def test_merge_failure_marks_conflict(self) -> None:
        uow = FakeUnitOfWork()
        disclosure_repo = FakeDisclosureRepo()
        dispatcher = FakeEventDispatcher()

        dr = _make_pending_confirmation_dr()
        disclosure_repo.add(dr)

        merge_service = AsyncMock()
        merge_service.merge_in_transaction = AsyncMock(
            return_value=Failure(ConflictError("Active sample requests block merge"))
        )

        uc = ConfirmDisclosure(
            uow=uow,
            disclosure_repo=disclosure_repo,
            merge_service=merge_service,
            dispatcher=dispatcher,
        )

        result = await uc(
            ConfirmDisclosureCommand(
                workspace_id=WS_ID,
                disclosure_id=dr.id,
                confirmed_by=USER_ID,
            ),
            auth=FakeAuth(),
        )

        assert isinstance(result, Failure)
        # DR should be in conflict state now
        saved_dr = await disclosure_repo.find_by_id_in_workspace(WS_ID, dr.id)
        assert saved_dr is not None
        assert saved_dr.status == DisclosureStatus.CONFLICT


class TestConfirmDisclosureValidation:
    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        uc = ConfirmDisclosure(
            uow=FakeUnitOfWork(),
            disclosure_repo=FakeDisclosureRepo(),
            merge_service=AsyncMock(),
            dispatcher=FakeEventDispatcher(),
        )

        result = await uc(
            ConfirmDisclosureCommand(
                workspace_id=WS_ID,
                disclosure_id=uuid.uuid4(),
                confirmed_by=USER_ID,
            ),
            auth=FakeAuth(),
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_wrong_status(self) -> None:
        disclosure_repo = FakeDisclosureRepo()

        # DR in PENDING status, not PENDING_CONFIRMATION
        dr = DisclosureRequest.create(
            workspace_id=WS_ID,
            molecule_id=uuid.uuid4(),
            disclosed_smiles="CCO",
            requested_by=USER_ID,
        )
        dr.clear_events()
        disclosure_repo.add(dr)

        uc = ConfirmDisclosure(
            uow=FakeUnitOfWork(),
            disclosure_repo=disclosure_repo,
            merge_service=AsyncMock(),
            dispatcher=FakeEventDispatcher(),
        )

        result = await uc(
            ConfirmDisclosureCommand(
                workspace_id=WS_ID,
                disclosure_id=dr.id,
                confirmed_by=USER_ID,
            ),
            auth=FakeAuth(),
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)
