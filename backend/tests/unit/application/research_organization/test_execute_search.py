"""Unit tests for ExecuteSearch use case — record_execution write-back."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock, patch

import pytest
from returns.result import Success

from cellar.application.research_organization.execute_search import (
    ExecuteSearch,
    ExecuteSearchQuery,
)
from cellar.domain.research_organization.saved_search import SavedSearch
from cellar.domain.shared.events import DomainEvent
from tests.fakes.fake_auth import FakeAuth

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
        name="Test Search",
        query={"keyword": "aspirin"},
        created_by=uuid.uuid4(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExecuteSearchRecordExecution:
    """Verify that record_execution is called on first page for saved searches."""

    @pytest.mark.asyncio
    async def test_first_page_records_execution(self) -> None:
        """When saved_search_id is provided and cursor_id is None (first page),
        record_execution should be called and the saved search should be persisted."""
        ws_id = uuid.uuid4()
        auth = FakeAuth(workspace_id=ws_id)
        saved_search = _make_saved_search(ws_id)

        uow = FakeUnitOfWork()
        mol_reader = AsyncMock()
        mol_reader.search_by_query = AsyncMock(return_value=[])
        mol_reader.count_by_query = AsyncMock(return_value=42)

        saved_search_repo = AsyncMock()
        saved_search_repo.find_by_id_in_workspace = AsyncMock(return_value=saved_search)
        saved_search_repo.save = AsyncMock()

        uc = ExecuteSearch(
            uow=uow,
            molecule_reader=mol_reader,
            saved_search_repo=saved_search_repo,
        )

        query = ExecuteSearchQuery(
            workspace_id=ws_id,
            saved_search_id=saved_search.id,
            cursor=None,
        )

        with patch.object(
            saved_search, "record_execution", wraps=saved_search.record_execution
        ) as mock_record:
            result = await uc(query, auth=auth)

        assert isinstance(result, Success)
        mock_record.assert_called_once_with(result_count=42)
        saved_search_repo.save.assert_awaited_once_with(saved_search)
        assert saved_search.last_run_at is not None
        assert saved_search.result_count == 42

    @pytest.mark.asyncio
    async def test_first_page_uses_len_when_count_fails(self) -> None:
        """When count_by_query raises ValueError, record_execution uses len(items)."""
        ws_id = uuid.uuid4()
        auth = FakeAuth(workspace_id=ws_id)
        saved_search = _make_saved_search(ws_id)

        uow = FakeUnitOfWork()
        mol_reader = AsyncMock()
        mol_reader.search_by_query = AsyncMock(return_value=[])
        mol_reader.count_by_query = AsyncMock(side_effect=ValueError("bad query"))

        saved_search_repo = AsyncMock()
        saved_search_repo.find_by_id_in_workspace = AsyncMock(return_value=saved_search)
        saved_search_repo.save = AsyncMock()

        uc = ExecuteSearch(
            uow=uow,
            molecule_reader=mol_reader,
            saved_search_repo=saved_search_repo,
        )

        query = ExecuteSearchQuery(
            workspace_id=ws_id,
            saved_search_id=saved_search.id,
            cursor=None,
        )

        result = await uc(query, auth=auth)
        assert isinstance(result, Success)
        # total_count is None (count failed), so len(molecules)=0 is used
        assert saved_search.result_count == 0
        saved_search_repo.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_pagination_does_not_record_execution(self) -> None:
        """When cursor_id is present (subsequent page), record_execution must NOT be called."""
        ws_id = uuid.uuid4()
        auth = FakeAuth(workspace_id=ws_id)
        saved_search = _make_saved_search(ws_id)

        uow = FakeUnitOfWork()
        mol_reader = AsyncMock()
        mol_reader.search_by_query = AsyncMock(return_value=[])

        saved_search_repo = AsyncMock()
        saved_search_repo.find_by_id_in_workspace = AsyncMock(return_value=saved_search)
        saved_search_repo.save = AsyncMock()

        uc = ExecuteSearch(
            uow=uow,
            molecule_reader=mol_reader,
            saved_search_repo=saved_search_repo,
        )

        query = ExecuteSearchQuery(
            workspace_id=ws_id,
            saved_search_id=saved_search.id,
            cursor=str(uuid.uuid4()),  # Subsequent page
        )

        with patch.object(saved_search, "record_execution") as mock_record:
            result = await uc(query, auth=auth)

        assert isinstance(result, Success)
        mock_record.assert_not_called()
        saved_search_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_inline_query_does_not_record_execution(self) -> None:
        """When using an inline query (no saved_search_id), no write-back happens."""
        ws_id = uuid.uuid4()
        auth = FakeAuth(workspace_id=ws_id)

        uow = FakeUnitOfWork()
        mol_reader = AsyncMock()
        mol_reader.search_by_query = AsyncMock(return_value=[])
        mol_reader.count_by_query = AsyncMock(return_value=5)

        saved_search_repo = AsyncMock()

        uc = ExecuteSearch(
            uow=uow,
            molecule_reader=mol_reader,
            saved_search_repo=saved_search_repo,
        )

        query = ExecuteSearchQuery(
            workspace_id=ws_id,
            query={"keyword": "test"},
            cursor=None,
        )

        result = await uc(query, auth=auth)
        assert isinstance(result, Success)
        saved_search_repo.find_by_id_in_workspace.assert_not_awaited()
        saved_search_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_writeback_failure_still_returns_results(self) -> None:
        """When the write-back commit fails, the search result should still be returned."""
        ws_id = uuid.uuid4()
        auth = FakeAuth(workspace_id=ws_id)
        saved_search = _make_saved_search(ws_id)

        class _FailingCommitUoW(FakeUnitOfWork):
            async def commit(self) -> list[DomainEvent]:
                raise RuntimeError("connection lost")

        uow = _FailingCommitUoW()
        mol_reader = AsyncMock()
        mol_reader.search_by_query = AsyncMock(return_value=[])
        mol_reader.count_by_query = AsyncMock(return_value=10)

        saved_search_repo = AsyncMock()
        saved_search_repo.find_by_id_in_workspace = AsyncMock(return_value=saved_search)
        saved_search_repo.save = AsyncMock()

        uc = ExecuteSearch(
            uow=uow,
            molecule_reader=mol_reader,
            saved_search_repo=saved_search_repo,
        )

        query = ExecuteSearchQuery(
            workspace_id=ws_id,
            saved_search_id=saved_search.id,
            cursor=None,
        )

        result = await uc(query, auth=auth)
        # Search should succeed despite write-back failure
        assert isinstance(result, Success)
        page = result.unwrap()
        assert page.total_count == 10


class TestRankedPagingReusesTheRanking:
    """One ExecuteSearch instance (an export walking its pages) ranks once."""

    @pytest.mark.asyncio
    async def test_pages_of_one_sorted_search_rank_once(self) -> None:
        ws_id = uuid.uuid4()
        ids = [uuid.uuid4() for _ in range(5)]
        mol_reader = AsyncMock()
        mol_reader.ranked_ids_by_query = AsyncMock(return_value=[(i, None) for i in ids])
        mol_reader.find_by_ids_ordered = AsyncMock(
            side_effect=lambda ws, page: [type("M", (), {"id": i})() for i in page]
        )
        uc = ExecuteSearch(
            uow=FakeUnitOfWork(), molecule_reader=mol_reader, saved_search_repo=AsyncMock()
        )

        cursor = None
        seen: list[uuid.UUID] = []
        for _ in range(3):
            result = await uc(
                ExecuteSearchQuery(
                    workspace_id=ws_id,
                    query={"logic": "and", "criteria": []},
                    sort_by="molecular_weight",
                    limit=2,
                    cursor=cursor,
                ),
                auth=FakeAuth(workspace_id=ws_id),
            )
            page = result.unwrap()
            seen += [m.id for m in page.items]
            cursor = page.next_cursor
        assert seen == ids
        assert mol_reader.ranked_ids_by_query.await_count == 1
