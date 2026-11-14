"""Integration tests for the recent-search use cases (Railway Result)."""

from __future__ import annotations

import uuid

import pytest
from returns.result import Failure, Success
from tests.fakes.fake_auth import FakeAuth

from cellar.application.personalization.clear_recent_searches import (
    ClearRecentSearches,
    ClearRecentSearchesCommand,
)
from cellar.application.personalization.list_recent_searches import (
    ListRecentSearches,
    ListRecentSearchesQuery,
)
from cellar.application.personalization.record_recent_search import (
    RecordRecentSearch,
    RecordRecentSearchCommand,
)
from cellar.domain.shared.errors import AuthorizationError, ValidationError
from cellar.infrastructure.persistence.sqlalchemy.personalization.recent_search_repository import (
    SQLAlchemyRecentSearchRepository,
)

pytestmark = pytest.mark.integration

_QUERY = {"logic": "and", "criteria": [{"type": "activity", "protocol_id": "p1", "where": []}]}


def _record_cmd(ws: uuid.UUID, user: uuid.UUID, query: dict = _QUERY) -> RecordRecentSearchCommand:
    return RecordRecentSearchCommand(workspace_id=ws, user_id=user, query=query, result_count=27)


async def test_a_viewer_records_and_lists_their_searches(
    session_factory, workspace_id, user_id
) -> None:
    repo = SQLAlchemyRecentSearchRepository(session_factory)
    auth = FakeAuth(role="viewer", workspace_id=workspace_id, user_id=user_id)

    recorded = await RecordRecentSearch(repo)(_record_cmd(workspace_id, user_id), auth=auth)
    listed = await ListRecentSearches(repo)(
        ListRecentSearchesQuery(workspace_id=workspace_id, user_id=user_id), auth=auth
    )

    assert isinstance(recorded, Success)
    assert isinstance(listed, Success)
    assert [s.result_count for s in listed.unwrap()] == [27]


async def test_an_empty_search_is_a_validation_failure(
    session_factory, workspace_id, user_id
) -> None:
    repo = SQLAlchemyRecentSearchRepository(session_factory)
    auth = FakeAuth(role="viewer", workspace_id=workspace_id, user_id=user_id)

    result = await RecordRecentSearch(repo)(
        _record_cmd(workspace_id, user_id, {"criteria": []}), auth=auth
    )

    assert isinstance(result, Failure)
    assert isinstance(result.failure(), ValidationError)


async def test_nobody_reads_or_writes_another_users_history(
    session_factory, workspace_id, user_id
) -> None:
    repo = SQLAlchemyRecentSearchRepository(session_factory)
    colleague = FakeAuth(role="admin", workspace_id=workspace_id, user_id=uuid.uuid4())

    with pytest.raises(AuthorizationError):
        await RecordRecentSearch(repo)(_record_cmd(workspace_id, user_id), auth=colleague)
    with pytest.raises(AuthorizationError):
        await ListRecentSearches(repo)(
            ListRecentSearchesQuery(workspace_id=workspace_id, user_id=user_id), auth=colleague
        )
    with pytest.raises(AuthorizationError):
        await ClearRecentSearches(repo)(
            ClearRecentSearchesCommand(workspace_id=workspace_id, user_id=user_id),
            auth=colleague,
        )


async def test_clear_empties_the_history(session_factory, workspace_id, user_id) -> None:
    repo = SQLAlchemyRecentSearchRepository(session_factory)
    auth = FakeAuth(role="viewer", workspace_id=workspace_id, user_id=user_id)
    await RecordRecentSearch(repo)(_record_cmd(workspace_id, user_id), auth=auth)

    cleared = await ClearRecentSearches(repo)(
        ClearRecentSearchesCommand(workspace_id=workspace_id, user_id=user_id), auth=auth
    )
    listed = await ListRecentSearches(repo)(
        ListRecentSearchesQuery(workspace_id=workspace_id, user_id=user_id), auth=auth
    )

    assert isinstance(cleared, Success)
    assert listed.unwrap() == []
