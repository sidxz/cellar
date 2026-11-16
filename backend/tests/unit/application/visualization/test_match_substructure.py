"""MatchSubstructure — guards, blank query, id cap, empty ids, unreadable query."""

from __future__ import annotations

import uuid

import pytest
from returns.result import Failure, Success

from cellar.application.visualization.match_substructure import (
    MAX_MATCH_IDS,
    MatchSubstructure,
    MatchSubstructureQuery,
    SubstructureMatchResult,
)
from cellar.domain.shared.errors import NotFoundError, ValidationError
from tests.fakes.fake_auth import FakeAuth

pytestmark = pytest.mark.asyncio

WS = uuid.uuid4()
ONE_ID = (uuid.uuid4(),)


class FakeMatcher:
    def __init__(self, result: SubstructureMatchResult | None = None, error: str | None = None):
        self.calls: list[tuple] = []
        self._result = result or SubstructureMatchResult(
            matched_ids=[], searched=0, without_structure=0
        )
        self._error = error

    async def match(self, workspace_id, molecule_ids, query, query_kind):
        self.calls.append((workspace_id, tuple(molecule_ids), query, query_kind))
        if self._error is not None:
            raise ValueError(self._error)
        return self._result


def _q(ids=ONE_ID, query="c1ccccc1", kind=None, ws=WS) -> MatchSubstructureQuery:
    return MatchSubstructureQuery(
        workspace_id=ws, molecule_ids=tuple(ids), query=query, query_kind=kind
    )


async def test_passes_the_query_to_the_matcher_and_returns_its_result():
    hit = uuid.uuid4()
    found = SubstructureMatchResult(matched_ids=[hit], searched=2, without_structure=1)
    matcher = FakeMatcher(found)
    ids = (hit, uuid.uuid4())

    result = await MatchSubstructure(matcher)(
        _q(ids, query="  c1ccccc1 ", kind="smiles"), auth=FakeAuth(workspace_id=WS)
    )

    assert result == Success(found)
    assert matcher.calls == [(WS, ids, "c1ccccc1", "smiles")]


@pytest.mark.parametrize("query", ["", "   "])
async def test_blank_query_is_a_validation_error(query):
    matcher = FakeMatcher()

    result = await MatchSubstructure(matcher)(_q(query=query), auth=FakeAuth(workspace_id=WS))

    assert isinstance(result, Failure) and isinstance(result.failure(), ValidationError)
    assert "Draw or type a structure" in str(result.failure())
    assert matcher.calls == []


async def test_more_ids_than_the_cap_is_a_validation_error():
    matcher = FakeMatcher()
    ids = [uuid.uuid4() for _ in range(MAX_MATCH_IDS + 1)]

    result = await MatchSubstructure(matcher)(_q(ids), auth=FakeAuth(workspace_id=WS))

    assert isinstance(result, Failure) and isinstance(result.failure(), ValidationError)
    assert f"{MAX_MATCH_IDS:,}" in str(result.failure())
    assert matcher.calls == []


async def test_no_ids_is_an_empty_result_without_asking_the_matcher():
    matcher = FakeMatcher()

    result = await MatchSubstructure(matcher)(_q(ids=()), auth=FakeAuth(workspace_id=WS))

    assert result == Success(
        SubstructureMatchResult(matched_ids=[], searched=0, without_structure=0)
    )
    assert matcher.calls == []


async def test_an_unreadable_query_is_a_validation_error_with_the_matchers_message():
    result = await MatchSubstructure(FakeMatcher(error="bad"))(
        _q(query="C1CC", kind="smiles"), auth=FakeAuth(workspace_id=WS)
    )

    assert isinstance(result, Failure) and isinstance(result.failure(), ValidationError)
    assert "bad" in str(result.failure())


async def test_another_workspace_caller_is_not_found():
    matcher = FakeMatcher()

    with pytest.raises(NotFoundError):
        await MatchSubstructure(matcher)(_q(), auth=FakeAuth(workspace_id=uuid.uuid4()))
    assert matcher.calls == []
