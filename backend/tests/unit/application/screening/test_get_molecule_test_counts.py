"""Unit tests for GetMoleculeTestCounts use case."""

from __future__ import annotations

import uuid
from typing import Self
from unittest.mock import AsyncMock

import pytest

from cellar.application.screening.get_molecule_test_counts import (
    GetMoleculeTestCounts,
    GetMoleculeTestCountsQuery,
)
from tests.fakes.fake_auth import FakeAuth


class _FakeUoW:
    is_active = True

    async def commit(self) -> list:
        return []

    async def rollback(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


WS = uuid.uuid4()
MOL_A = uuid.uuid4()
MOL_B = uuid.uuid4()
PROJ_ID = uuid.uuid4()


@pytest.mark.asyncio
class TestGetMoleculeTestCounts:
    async def test_returns_zero_for_untested_molecule(self) -> None:
        fake_repo = AsyncMock()
        fake_repo.count_distinct_protocols_per_molecule.return_value = {MOL_A: 0}
        uc = GetMoleculeTestCounts(uow=_FakeUoW(), dr_curve_repo=fake_repo)
        auth = FakeAuth(role="viewer", workspace_id=WS)

        result = await uc.execute(
            GetMoleculeTestCountsQuery(workspace_id=WS, molecule_ids=[MOL_A]),
            auth=auth,
        )

        assert result[MOL_A] == 0
        fake_repo.count_distinct_protocols_per_molecule.assert_awaited_once_with(
            workspace_id=WS,
            molecule_ids=[MOL_A],
            project_id=None,
        )

    async def test_returns_count_for_tested_molecule(self) -> None:
        fake_repo = AsyncMock()
        fake_repo.count_distinct_protocols_per_molecule.return_value = {MOL_A: 3, MOL_B: 1}
        uc = GetMoleculeTestCounts(uow=_FakeUoW(), dr_curve_repo=fake_repo)
        auth = FakeAuth(role="viewer", workspace_id=WS)

        result = await uc.execute(
            GetMoleculeTestCountsQuery(workspace_id=WS, molecule_ids=[MOL_A, MOL_B]),
            auth=auth,
        )

        assert result[MOL_A] == 3
        assert result[MOL_B] == 1

    async def test_passes_project_id_to_repo(self) -> None:
        fake_repo = AsyncMock()
        fake_repo.count_distinct_protocols_per_molecule.return_value = {MOL_A: 2}
        uc = GetMoleculeTestCounts(uow=_FakeUoW(), dr_curve_repo=fake_repo)
        auth = FakeAuth(role="viewer", workspace_id=WS)

        await uc.execute(
            GetMoleculeTestCountsQuery(
                workspace_id=WS,
                molecule_ids=[MOL_A],
                project_id=PROJ_ID,
            ),
            auth=auth,
        )

        fake_repo.count_distinct_protocols_per_molecule.assert_awaited_once_with(
            workspace_id=WS,
            molecule_ids=[MOL_A],
            project_id=PROJ_ID,
        )

    async def test_empty_molecule_ids_returns_empty(self) -> None:
        fake_repo = AsyncMock()
        uc = GetMoleculeTestCounts(uow=_FakeUoW(), dr_curve_repo=fake_repo)
        auth = FakeAuth(role="viewer", workspace_id=WS)

        result = await uc.execute(
            GetMoleculeTestCountsQuery(workspace_id=WS, molecule_ids=[]),
            auth=auth,
        )

        assert result == {}
        fake_repo.count_distinct_protocols_per_molecule.assert_not_called()
