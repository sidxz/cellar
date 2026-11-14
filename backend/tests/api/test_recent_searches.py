"""API contract tests for the recent-search endpoints."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def _query(protocol: str, aggregation: str = "latest_run") -> dict:
    return {
        "logic": "and",
        "criteria": [{"type": "activity", "protocol_id": protocol, "where": []}],
        "aggregation": aggregation,
    }


async def test_record_list_clear_roundtrip(client) -> None:
    columns = {"protocolColumns": ["drc:x"], "reportConfig": {"imageSize": "small"}}
    resp = await client.post(
        "/api/v1/recent-searches",
        json={"query": _query("p1"), "columns": columns, "result_count": 27},
    )
    assert resp.status_code == 201
    assert resp.json()["result_count"] == 27

    await client.post("/api/v1/recent-searches", json={"query": _query("p2")})
    # The same criteria under another aggregation rule are the same search.
    await client.post("/api/v1/recent-searches", json={"query": _query("p1", "geometric_mean")})

    resp = await client.get("/api/v1/recent-searches")
    assert resp.status_code == 200
    body = resp.json()
    assert [s["query"]["criteria"][0]["protocol_id"] for s in body] == ["p1", "p2"]
    assert body[0]["query"]["aggregation"] == "geometric_mean"

    resp = await client.get("/api/v1/recent-searches", params={"limit": 1})
    assert len(resp.json()) == 1

    resp = await client.delete("/api/v1/recent-searches")
    assert resp.status_code == 204
    assert (await client.get("/api/v1/recent-searches")).json() == []


async def test_a_search_without_criteria_is_rejected(client) -> None:
    resp = await client.post("/api/v1/recent-searches", json={"query": {"criteria": []}})
    assert resp.status_code == 422
