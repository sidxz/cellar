"""Unit tests for CountSearch -- live search-button count preview."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.count_search import (
    CountSearch,
    CountSearchQuery,
)
from cellar.domain.research_organization.saved_search import SavedSearch
from cellar.domain.shared.errors import NotFoundError, ValidationError
from cellar.domain.shared.events import DomainEvent
from tests.fakes.fake_auth import FakeAuth


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


def _make_saved_search(workspace_id: uuid.UUID) -> SavedSearch:
    return SavedSearch(
        workspace_id=workspace_id,
        name="Saved",
        query={"keyword": "aspirin"},
        created_by=uuid.uuid4(),
    )


class TestCountSearch:
    @pytest.mark.asyncio
    async def test_inline_query_returns_count(self) -> None:
        ws_id = uuid.uuid4()
        auth = FakeAuth(workspace_id=ws_id)

        mol_reader = AsyncMock()
        mol_reader.count_by_query = AsyncMock(return_value=42)

        uc = CountSearch(
            uow=FakeUnitOfWork(),
            molecule_reader=mol_reader,
            saved_search_repo=AsyncMock(),
        )

        result = await uc(
            CountSearchQuery(
                workspace_id=ws_id,
                query={"criteria": [], "logic": "and"},
            ),
            auth=auth,
        )

        assert isinstance(result, Success)
        assert result.unwrap() == 42

    @pytest.mark.asyncio
    async def test_saved_search_resolved_then_counted(self) -> None:
        ws_id = uuid.uuid4()
        auth = FakeAuth(workspace_id=ws_id)
        saved = _make_saved_search(ws_id)

        mol_reader = AsyncMock()
        mol_reader.count_by_query = AsyncMock(return_value=7)

        ss_repo = AsyncMock()
        ss_repo.find_by_id_in_workspace = AsyncMock(return_value=saved)

        uc = CountSearch(
            uow=FakeUnitOfWork(),
            molecule_reader=mol_reader,
            saved_search_repo=ss_repo,
        )

        result = await uc(
            CountSearchQuery(workspace_id=ws_id, saved_search_id=saved.id),
            auth=auth,
        )

        assert isinstance(result, Success)
        assert result.unwrap() == 7
        # Count uses the saved search's query, not a write-back call
        mol_reader.count_by_query.assert_awaited_once()
        called_kwargs = mol_reader.count_by_query.call_args.kwargs
        called_args = mol_reader.count_by_query.call_args.args
        # workspace_id is positional
        assert called_args[0] == ws_id
        assert called_args[1] == saved.query
        assert called_kwargs.get("project_ids") is None

    @pytest.mark.asyncio
    async def test_saved_search_not_found(self) -> None:
        ws_id = uuid.uuid4()
        auth = FakeAuth(workspace_id=ws_id)

        ss_repo = AsyncMock()
        ss_repo.find_by_id_in_workspace = AsyncMock(return_value=None)

        uc = CountSearch(
            uow=FakeUnitOfWork(),
            molecule_reader=AsyncMock(),
            saved_search_repo=ss_repo,
        )

        result = await uc(
            CountSearchQuery(workspace_id=ws_id, saved_search_id=uuid.uuid4()),
            auth=auth,
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_no_query_or_saved_search_id_is_validation_error(self) -> None:
        ws_id = uuid.uuid4()
        auth = FakeAuth(workspace_id=ws_id)

        uc = CountSearch(
            uow=FakeUnitOfWork(),
            molecule_reader=AsyncMock(),
            saved_search_repo=AsyncMock(),
        )

        result = await uc(CountSearchQuery(workspace_id=ws_id), auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)

    @pytest.mark.asyncio
    async def test_composer_value_error_becomes_validation_error(self) -> None:
        ws_id = uuid.uuid4()
        auth = FakeAuth(workspace_id=ws_id)

        mol_reader = AsyncMock()
        mol_reader.count_by_query = AsyncMock(
            side_effect=ValueError("bad SMARTS")
        )

        uc = CountSearch(
            uow=FakeUnitOfWork(),
            molecule_reader=mol_reader,
            saved_search_repo=AsyncMock(),
        )

        result = await uc(
            CountSearchQuery(workspace_id=ws_id, query={"criteria": []}),
            auth=auth,
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)

    @pytest.mark.asyncio
    async def test_workspace_mismatch_raises_notfound(self) -> None:
        """Cross-workspace requests are masked as NotFound to avoid leaking
        the existence of entities in another tenant."""
        ws_id = uuid.uuid4()
        auth = FakeAuth(workspace_id=uuid.uuid4())  # different workspace

        uc = CountSearch(
            uow=FakeUnitOfWork(),
            molecule_reader=AsyncMock(),
            saved_search_repo=AsyncMock(),
        )

        with pytest.raises(NotFoundError):
            await uc(
                CountSearchQuery(
                    workspace_id=ws_id,
                    query={"criteria": []},
                ),
                auth=auth,
            )

    @pytest.mark.asyncio
    async def test_does_not_call_search_by_query(self) -> None:
        """Count path must not materialize rows -- only count_by_query."""
        ws_id = uuid.uuid4()
        auth = FakeAuth(workspace_id=ws_id)

        mol_reader = AsyncMock()
        mol_reader.count_by_query = AsyncMock(return_value=3)
        # search_by_query is also AsyncMock by default; assert it stays untouched

        uc = CountSearch(
            uow=FakeUnitOfWork(),
            molecule_reader=mol_reader,
            saved_search_repo=AsyncMock(),
        )

        result = await uc(
            CountSearchQuery(workspace_id=ws_id, query={"criteria": []}),
            auth=auth,
        )

        assert isinstance(result, Success)
        mol_reader.search_by_query.assert_not_awaited()
