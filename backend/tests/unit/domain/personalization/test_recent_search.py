"""RecentSearch — what makes two runs the same search, and what can be kept."""

from __future__ import annotations

import uuid

import pytest

from cellar.domain.personalization.recent_search import RecentSearch, recent_search_key
from cellar.domain.shared.errors import ValidationError

_ASSAY = {"type": "activity", "protocol_id": "p1", "where": []}


def _record(**over) -> RecentSearch:
    return RecentSearch.record(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        query=over.pop("query", {"logic": "and", "criteria": [_ASSAY]}),
        **over,
    )


def test_the_aggregation_rule_does_not_make_a_new_search() -> None:
    base = {"logic": "and", "criteria": [_ASSAY]}
    assert recent_search_key({**base, "aggregation": "latest_run"}) == recent_search_key(
        {**base, "aggregation": "geometric_mean"}
    )


def test_key_and_criteria_order_do_not_matter_but_criteria_do() -> None:
    other = {**_ASSAY, "protocol_id": "p2"}
    assert recent_search_key({"logic": "and", "criteria": [_ASSAY, other]}) == recent_search_key(
        {"criteria": [other, _ASSAY]}
    )
    assert recent_search_key({"criteria": [_ASSAY]}) != recent_search_key({"criteria": [other]})
    assert recent_search_key({"logic": "and", "criteria": [_ASSAY, other]}) != recent_search_key(
        {"logic": "or", "criteria": [_ASSAY, other]}
    )


def test_record_keeps_the_query_columns_and_count() -> None:
    columns = {"protocolColumns": ["drc:abc"], "reportConfig": {"imageSize": "small"}}
    search = _record(columns=columns, result_count=27)
    assert search.query["criteria"] == [_ASSAY]
    assert search.columns == columns
    assert search.result_count == 27
    assert search.ran_at.tzinfo is not None


@pytest.mark.parametrize("query", [{}, {"criteria": []}, {"criteria": "x"}])
def test_a_search_with_no_criteria_is_not_recorded(query: dict) -> None:
    with pytest.raises(ValidationError):
        _record(query=query)


def test_a_negative_count_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _record(result_count=-1)
