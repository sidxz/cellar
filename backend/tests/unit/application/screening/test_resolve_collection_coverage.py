"""Unit tests for collection-coverage + gap read use cases.

Mirrors the local-fakes convention in ``test_delete_run.py``: a local
``FakeUoW`` (async context manager) and a ``FakeAuth`` dataclass, with
``AsyncMock`` repos/readers. Verifies the ownership-first 404 discipline
(``find_lock_state`` → ``None`` short-circuits before the reader runs).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.screening.get_collection_gap import (
    GetProtocolCollectionGap,
    GetProtocolCollectionGapQuery,
    GetRunCollectionGap,
    GetRunCollectionGapQuery,
)
from cellar.application.screening.resolve_collection_coverage import (
    GetProtocolCollectionCoverage,
    GetProtocolCollectionCoverageQuery,
    ResolveRunCollections,
    ResolveRunCollectionsQuery,
)
from cellar.domain.screening_assay.collection_coverage import (
    CollectionCoverage,
    CollectionRef,
    EffectiveCollectionCoverage,
)
from cellar.domain.shared.errors import NotFoundError

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeUoW:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> list:
        self.committed = True
        return []

    async def rollback(self) -> None:  # pragma: no cover
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        return None


@dataclass
class FakeAuth:
    user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    workspace_id: uuid.UUID = field(default_factory=uuid.uuid4)
    workspace_role: str = "viewer"
    is_admin: bool = False

    def has_role(self, minimum_role: str) -> bool:
        roles = ["viewer", "editor", "admin"]
        return roles.index(self.workspace_role) >= roles.index(minimum_role)


def _ref() -> CollectionRef:
    return CollectionRef(id=uuid.uuid4(), name="Kinase Library", type="library")


# ---------------------------------------------------------------------------
# GetProtocolCollectionCoverage
# ---------------------------------------------------------------------------


class TestGetProtocolCollectionCoverage:
    @pytest.mark.asyncio
    async def test_foreign_or_missing_protocol_404s(self) -> None:
        auth = FakeAuth()
        protocol_repo = AsyncMock()
        protocol_repo.find_lock_state = AsyncMock(return_value=None)
        reader = AsyncMock()
        reader.protocol_coverage = AsyncMock(return_value=[])
        uc = GetProtocolCollectionCoverage(
            uow=FakeUoW(), protocol_repo=protocol_repo, reader=reader
        )

        result = await uc(
            GetProtocolCollectionCoverageQuery(
                workspace_id=auth.workspace_id, protocol_id=uuid.uuid4()
            ),
            auth=auth,
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        reader.protocol_coverage.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_owned_protocol_returns_reader_rollup(self) -> None:
        auth = FakeAuth()
        protocol_id = uuid.uuid4()
        rollup = [EffectiveCollectionCoverage(ref=_ref(), covered=3, total=4, run_count=2)]
        protocol_repo = AsyncMock()
        protocol_repo.find_lock_state = AsyncMock(return_value=False)
        reader = AsyncMock()
        reader.protocol_coverage = AsyncMock(return_value=rollup)
        uc = GetProtocolCollectionCoverage(
            uow=FakeUoW(), protocol_repo=protocol_repo, reader=reader
        )

        result = await uc(
            GetProtocolCollectionCoverageQuery(
                workspace_id=auth.workspace_id, protocol_id=protocol_id
            ),
            auth=auth,
        )

        assert isinstance(result, Success), result
        rows = result.unwrap()
        assert rows == rollup
        assert rows[0].fraction == 0.75
        assert rows[0].run_count == 2
        reader.protocol_coverage.assert_awaited_once_with(auth.workspace_id, protocol_id)


# ---------------------------------------------------------------------------
# ResolveRunCollections
# ---------------------------------------------------------------------------


class TestResolveRunCollections:
    @pytest.mark.asyncio
    async def test_returns_reader_dict(self) -> None:
        auth = FakeAuth()
        run_id = uuid.uuid4()
        coverage = {run_id: [CollectionCoverage(ref=_ref(), covered=2, total=5)]}
        reader = AsyncMock()
        reader.run_coverage = AsyncMock(return_value=coverage)
        uc = ResolveRunCollections(uow=FakeUoW(), reader=reader)

        result = await uc(
            ResolveRunCollectionsQuery(workspace_id=auth.workspace_id, run_ids=(run_id,)),
            auth=auth,
        )

        assert isinstance(result, Success), result
        assert result.unwrap() == coverage
        reader.run_coverage.assert_awaited_once_with(auth.workspace_id, [run_id])


# ---------------------------------------------------------------------------
# GetRunCollectionGap
# ---------------------------------------------------------------------------


class TestGetRunCollectionGap:
    @pytest.mark.asyncio
    async def test_missing_run_404s(self) -> None:
        auth = FakeAuth()
        run_repo = AsyncMock()
        run_repo.find_lock_state = AsyncMock(return_value=None)
        reader = AsyncMock()
        reader.run_gap = AsyncMock(return_value=[])
        uc = GetRunCollectionGap(uow=FakeUoW(), run_repo=run_repo, reader=reader)

        result = await uc(
            GetRunCollectionGapQuery(
                workspace_id=auth.workspace_id,
                run_id=uuid.uuid4(),
                collection_id=uuid.uuid4(),
            ),
            auth=auth,
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        reader.run_gap.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_owned_run_returns_gap_ids(self) -> None:
        auth = FakeAuth()
        run_id = uuid.uuid4()
        collection_id = uuid.uuid4()
        gap = [uuid.uuid4(), uuid.uuid4()]
        run_repo = AsyncMock()
        run_repo.find_lock_state = AsyncMock(return_value=False)
        reader = AsyncMock()
        reader.run_gap = AsyncMock(return_value=gap)
        uc = GetRunCollectionGap(uow=FakeUoW(), run_repo=run_repo, reader=reader)

        result = await uc(
            GetRunCollectionGapQuery(
                workspace_id=auth.workspace_id,
                run_id=run_id,
                collection_id=collection_id,
                offset=10,
                limit=25,
            ),
            auth=auth,
        )

        assert isinstance(result, Success), result
        assert result.unwrap() == gap
        reader.run_gap.assert_awaited_once_with(
            auth.workspace_id, run_id, collection_id, offset=10, limit=25
        )


# ---------------------------------------------------------------------------
# GetProtocolCollectionGap
# ---------------------------------------------------------------------------


class TestGetProtocolCollectionGap:
    @pytest.mark.asyncio
    async def test_missing_protocol_404s(self) -> None:
        auth = FakeAuth()
        protocol_repo = AsyncMock()
        protocol_repo.find_lock_state = AsyncMock(return_value=None)
        reader = AsyncMock()
        reader.protocol_gap = AsyncMock(return_value=[])
        uc = GetProtocolCollectionGap(uow=FakeUoW(), protocol_repo=protocol_repo, reader=reader)

        result = await uc(
            GetProtocolCollectionGapQuery(
                workspace_id=auth.workspace_id,
                protocol_id=uuid.uuid4(),
                collection_id=uuid.uuid4(),
            ),
            auth=auth,
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        reader.protocol_gap.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_owned_protocol_returns_gap_ids(self) -> None:
        auth = FakeAuth()
        protocol_id = uuid.uuid4()
        collection_id = uuid.uuid4()
        gap = [uuid.uuid4()]
        protocol_repo = AsyncMock()
        protocol_repo.find_lock_state = AsyncMock(return_value=False)
        reader = AsyncMock()
        reader.protocol_gap = AsyncMock(return_value=gap)
        uc = GetProtocolCollectionGap(uow=FakeUoW(), protocol_repo=protocol_repo, reader=reader)

        result = await uc(
            GetProtocolCollectionGapQuery(
                workspace_id=auth.workspace_id,
                protocol_id=protocol_id,
                collection_id=collection_id,
            ),
            auth=auth,
        )

        assert isinstance(result, Success), result
        assert result.unwrap() == gap
        reader.protocol_gap.assert_awaited_once_with(
            auth.workspace_id, protocol_id, collection_id, offset=0, limit=100
        )
