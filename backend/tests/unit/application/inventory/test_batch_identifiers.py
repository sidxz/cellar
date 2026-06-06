"""Unit tests for batch identifier CRUD use cases."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from returns.result import Failure, Success

from cellar.application.inventory.batch_identifiers import (
    AddBatchIdentifier,
    AddBatchIdentifierCommand,
    ListBatchIdentifiers,
    ListBatchIdentifiersQuery,
    RemoveBatchIdentifier,
    RemoveBatchIdentifierCommand,
)
from cellar.domain.inventory.batch import Batch
from cellar.domain.inventory.batch_identifier import BatchIdentifier
from cellar.domain.inventory.enums import BatchSource
from cellar.domain.shared.enums import AmountUnit
from cellar.domain.shared.errors import ConflictError, NotFoundError
from cellar.domain.shared.value_objects import Amount, BatchNumber
from tests.fakes.fake_auth import FakeAuth


def _make_batch(ws: uuid.UUID, mol: uuid.UUID) -> Batch:
    return Batch.create(
        workspace_id=ws,
        molecule_id=mol,
        batch_number=BatchNumber(value="CC-000001-001"),
        amount=Amount(value=1.0, unit=AmountUnit.MG),
        source=BatchSource.SYNTHESIZED,
        chemist=uuid.uuid4(),
    )


def _editor_auth(ws: uuid.UUID) -> FakeAuth:
    return FakeAuth(role="editor", workspace_id=ws)


def _mock_uow() -> MagicMock:
    uow = MagicMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    uow.commit = AsyncMock(return_value=[])
    return uow


@pytest.mark.asyncio
class TestAddBatchIdentifier:
    async def test_adds_identifier_when_unique(self) -> None:
        ws = uuid.uuid4()
        mol = uuid.uuid4()
        batch = _make_batch(ws, mol)
        repo = AsyncMock()
        repo.find_by_id_in_workspace = AsyncMock(return_value=batch)
        repo.find_by_external_identifier = AsyncMock(return_value=None)
        repo.save = AsyncMock()
        uow = _mock_uow()
        dispatcher = AsyncMock()

        uc = AddBatchIdentifier(uow=uow, repo=repo, dispatcher=dispatcher)
        result = await uc(
            AddBatchIdentifierCommand(
                workspace_id=ws,
                batch_id=batch.id,
                identifier="SACC-009999-001",
                identifier_type="external_lot",
                source="CDD",
                registered_by=uuid.uuid4(),
            ),
            auth=_editor_auth(ws),
        )
        assert isinstance(result, Success)
        assert len(result.unwrap().identifiers) == 1

    async def test_rejects_when_identifier_taken_by_another_batch(self) -> None:
        ws = uuid.uuid4()
        mol = uuid.uuid4()
        my_batch = _make_batch(ws, mol)
        other_batch = _make_batch(ws, mol)
        repo = AsyncMock()
        repo.find_by_id_in_workspace = AsyncMock(return_value=my_batch)
        repo.find_by_external_identifier = AsyncMock(return_value=other_batch)
        repo.save = AsyncMock()
        uow = _mock_uow()
        dispatcher = AsyncMock()

        uc = AddBatchIdentifier(uow=uow, repo=repo, dispatcher=dispatcher)
        result = await uc(
            AddBatchIdentifierCommand(
                workspace_id=ws,
                batch_id=my_batch.id,
                identifier="SACC-009999-001",
                identifier_type="external_lot",
                source="CDD",
                registered_by=uuid.uuid4(),
            ),
            auth=_editor_auth(ws),
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ConflictError)

    async def test_returns_not_found_when_batch_missing(self) -> None:
        ws = uuid.uuid4()
        repo = AsyncMock()
        repo.find_by_id_in_workspace = AsyncMock(return_value=None)
        uow = _mock_uow()
        dispatcher = AsyncMock()

        uc = AddBatchIdentifier(uow=uow, repo=repo, dispatcher=dispatcher)
        result = await uc(
            AddBatchIdentifierCommand(
                workspace_id=ws,
                batch_id=uuid.uuid4(),
                identifier="X",
                identifier_type="custom",
                source="user",
                registered_by=uuid.uuid4(),
            ),
            auth=_editor_auth(ws),
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)


@pytest.mark.asyncio
class TestRemoveBatchIdentifier:
    async def test_removes_existing(self) -> None:
        ws = uuid.uuid4()
        mol = uuid.uuid4()
        batch = _make_batch(ws, mol)
        ident = BatchIdentifier.create(
            batch_id=batch.id,
            identifier="X",
            identifier_type="custom",
            source="user",
            registered_by=uuid.uuid4(),
        )
        batch.add_identifier(ident)
        repo = AsyncMock()
        repo.find_by_id_in_workspace = AsyncMock(return_value=batch)
        repo.save = AsyncMock()
        uow = _mock_uow()
        dispatcher = AsyncMock()

        uc = RemoveBatchIdentifier(uow=uow, repo=repo, dispatcher=dispatcher)
        result = await uc(
            RemoveBatchIdentifierCommand(
                workspace_id=ws,
                batch_id=batch.id,
                identifier_id=ident.id,
            ),
            auth=_editor_auth(ws),
        )
        assert isinstance(result, Success)
        assert batch.identifiers == []


@pytest.mark.asyncio
class TestListBatchIdentifiers:
    async def test_lists_identifiers(self) -> None:
        ws = uuid.uuid4()
        mol = uuid.uuid4()
        batch = _make_batch(ws, mol)
        batch.add_identifier(
            BatchIdentifier.create(
                batch_id=batch.id,
                identifier="A",
                identifier_type="custom",
                source="user",
                registered_by=uuid.uuid4(),
            )
        )
        batch.add_identifier(
            BatchIdentifier.create(
                batch_id=batch.id,
                identifier="B",
                identifier_type="custom",
                source="user",
                registered_by=uuid.uuid4(),
            )
        )
        repo = AsyncMock()
        repo.find_by_id_in_workspace = AsyncMock(return_value=batch)
        uow = _mock_uow()

        uc = ListBatchIdentifiers(uow=uow, repo=repo)
        result = await uc(
            ListBatchIdentifiersQuery(workspace_id=ws, batch_id=batch.id),
            auth=_editor_auth(ws),
        )
        assert isinstance(result, Success)
        assert len(result.unwrap()) == 2
