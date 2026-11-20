"""Tests for GetMergeHistory query use case."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self

import pytest
from returns.result import Failure

from cellar.application.chemical_registration.get_merge_history import (
    GetMergeHistory,
    GetMergeHistoryQuery,
)
from cellar.domain.chemical_registration.merge_event import MergeEvent
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.shared.errors import NotFoundError
from cellar.domain.shared.events import DomainEvent

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

WS_ID = uuid.uuid4()


class FakeUnitOfWork:
    async def commit(self) -> list[DomainEvent]:
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


class FakeMoleculeRepo:
    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> Molecule | None:
        return None


class FakeMergeEventRepo:
    async def find_by_molecule(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID
    ) -> list[MergeEvent]:
        return []


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetMergeHistory:
    @pytest.mark.asyncio
    async def test_molecule_not_found(self) -> None:
        mol_repo = FakeMoleculeRepo()
        merge_repo = FakeMergeEventRepo()

        uc = GetMergeHistory(FakeUnitOfWork(), mol_repo, merge_repo)
        result = await uc(
            GetMergeHistoryQuery(workspace_id=WS_ID, molecule_id=uuid.uuid4())
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
