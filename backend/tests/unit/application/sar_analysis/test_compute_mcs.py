"""Unit tests for the ComputeMcs use case."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest

from cellar.application.sar_analysis.compute_mcs import ComputeMcs, ComputeMcsInput
from cellar.domain.shared.errors import AuthorizationError, NotFoundError
from cellar.infrastructure.rdkit.mcs_calculator import RdkitMcsCalculator
from tests.unit.application.research_organization._helpers import fake_auth


class _FakeUoW:
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        return None


def _fetcher(rows: list[tuple[uuid.UUID, str, str | None]]) -> AsyncMock:
    fetcher = AsyncMock()
    fetcher.fetch_for_scaffold_tree = AsyncMock(return_value=rows)
    return fetcher


def _use_case(rows: list[tuple[uuid.UUID, str, str | None]]) -> tuple[ComputeMcs, AsyncMock]:
    fetcher = _fetcher(rows)
    return (
        ComputeMcs(
            molecule_fetcher=fetcher, calculator=RdkitMcsCalculator(), uow=_FakeUoW()
        ),
        fetcher,
    )


SERIES = [
    (uuid.uuid4(), "Cc1ccc2ncc(C(=O)O)c(N)c2c1", None),
    (uuid.uuid4(), "Clc1ccc2ncc(C(=O)O)c(NC)c2c1", None),
    (uuid.uuid4(), "COc1ccc2ncc(C(=O)O)c(N)c2c1", None),
]


@pytest.mark.asyncio
async def test_computes_the_core_of_the_fetched_structures():
    auth = fake_auth(role="viewer")
    uc, fetcher = _use_case(SERIES)

    result = await uc.execute(
        ComputeMcsInput(
            molecule_ids=[r[0] for r in SERIES], workspace_id=auth.workspace_id
        ),
        auth=auth,
    )

    assert result.core_smiles == "Nc1c(C(=O)O)cnc2ccccc12"
    assert result.molecule_count == 3
    assert result.timed_out is False
    # The fetch is workspace-scoped — that is what keeps another tenant's
    # structures out of the answer.
    assert fetcher.fetch_for_scaffold_tree.await_args.kwargs["workspace_id"] == auth.workspace_id


@pytest.mark.asyncio
async def test_duplicate_structures_count_once():
    auth = fake_auth(role="viewer")
    duplicated = [*SERIES, (uuid.uuid4(), SERIES[0][1], None)]
    uc, _ = _use_case(duplicated)

    result = await uc.execute(
        ComputeMcsInput(
            molecule_ids=[r[0] for r in duplicated], workspace_id=auth.workspace_id
        ),
        auth=auth,
    )

    # Four rows, three distinct structures: "shared by 3 of 3", not 4.
    assert result.molecule_count == 3


@pytest.mark.asyncio
async def test_molecules_the_workspace_does_not_own_simply_are_not_in_the_answer():
    # The fetch returns only what the workspace owns, so an id from elsewhere
    # drops out — and molecule_count reports what the answer really covers.
    auth = fake_auth(role="viewer")
    uc, _ = _use_case(SERIES[:2])

    result = await uc.execute(
        ComputeMcsInput(
            molecule_ids=[*[r[0] for r in SERIES], uuid.uuid4()],
            workspace_id=auth.workspace_id,
        ),
        auth=auth,
    )

    assert result.molecule_count == 2


@pytest.mark.asyncio
async def test_requires_a_workspace_member():
    auth = fake_auth(role="viewer")
    auth.has_role = lambda _minimum_role: False
    uc, _ = _use_case(SERIES)

    with pytest.raises(AuthorizationError):
        await uc.execute(
            ComputeMcsInput(molecule_ids=[], workspace_id=auth.workspace_id), auth=auth
        )


@pytest.mark.asyncio
async def test_another_workspace_cannot_compute_over_these_ids():
    auth = fake_auth(role="viewer")
    uc, _ = _use_case(SERIES)

    with pytest.raises(NotFoundError):
        await uc.execute(
            ComputeMcsInput(molecule_ids=[], workspace_id=uuid.uuid4()), auth=auth
        )
