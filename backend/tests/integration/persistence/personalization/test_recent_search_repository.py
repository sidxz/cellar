"""Integration tests for SQLAlchemyRecentSearchRepository."""

from __future__ import annotations

import uuid

import pytest

from cellar.domain.personalization.recent_search import RecentSearch
from cellar.infrastructure.persistence.sqlalchemy.personalization.recent_search_repository import (
    SQLAlchemyRecentSearchRepository,
)

pytestmark = pytest.mark.integration


def _search(ws: uuid.UUID, user: uuid.UUID, protocol: str, **over) -> RecentSearch:
    return RecentSearch.record(
        workspace_id=ws,
        user_id=user,
        query={
            "logic": "and",
            "criteria": [{"type": "activity", "protocol_id": protocol, "where": []}],
            **over.pop("query_extra", {}),
        },
        **over,
    )


async def test_newest_first_and_trimmed_to_keep(session_factory) -> None:
    repo = SQLAlchemyRecentSearchRepository(session_factory)
    ws, user = uuid.uuid4(), uuid.uuid4()
    for p in ("p1", "p2", "p3", "p4"):
        await repo.record(_search(ws, user, p), keep=3)

    listed = await repo.list_for_user(ws, user, limit=10)
    assert [s.query["criteria"][0]["protocol_id"] for s in listed] == ["p4", "p3", "p2"]


async def test_running_a_search_again_moves_it_up_instead_of_duplicating(session_factory) -> None:
    repo = SQLAlchemyRecentSearchRepository(session_factory)
    ws, user = uuid.uuid4(), uuid.uuid4()
    first = await repo.record(_search(ws, user, "p1", result_count=10), keep=20)
    await repo.record(_search(ws, user, "p2"), keep=20)
    again = await repo.record(
        _search(
            ws,
            user,
            "p1",
            result_count=12,
            columns={"protocolColumns": ["drc:x"]},
            query_extra={"aggregation": "geometric_mean"},
        ),
        keep=20,
    )

    listed = await repo.list_for_user(ws, user, limit=10)
    assert [s.query["criteria"][0]["protocol_id"] for s in listed] == ["p1", "p2"]
    assert again.id == first.id
    # The latest run's count, table set-up and aggregation rule replace the old ones.
    assert listed[0].result_count == 12
    assert listed[0].columns == {"protocolColumns": ["drc:x"]}
    assert listed[0].query["aggregation"] == "geometric_mean"


async def test_history_is_per_user_and_per_workspace(session_factory) -> None:
    repo = SQLAlchemyRecentSearchRepository(session_factory)
    ws, other_ws, me, colleague = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await repo.record(_search(ws, me, "mine"), keep=20)
    await repo.record(_search(ws, colleague, "theirs"), keep=1)
    await repo.record(_search(other_ws, me, "elsewhere"), keep=1)

    listed = await repo.list_for_user(ws, me, limit=10)
    assert [s.query["criteria"][0]["protocol_id"] for s in listed] == ["mine"]


async def test_clear_removes_only_my_history(session_factory) -> None:
    repo = SQLAlchemyRecentSearchRepository(session_factory)
    ws, me, colleague = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await repo.record(_search(ws, me, "p1"), keep=20)
    await repo.record(_search(ws, colleague, "p1"), keep=20)

    await repo.clear(ws, me)

    assert await repo.list_for_user(ws, me, limit=10) == []
    assert len(await repo.list_for_user(ws, colleague, limit=10)) == 1
