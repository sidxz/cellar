"""API tests: tag-filtering the per-protocol run list endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _make_run(client: AsyncClient) -> tuple[str, str]:
    """Create a protocol + run; return (protocol_id, run_id)."""
    proto = await client.post(
        "/api/v1/protocols",
        json={
            "name": "TagRunProto",
            "protocol_type": "biochemical",
            "readout_definitions": [
                {"name": "IC50", "data_type": "numeric", "display_order": 0}
            ],
        },
    )
    assert proto.status_code in (200, 201), proto.text
    protocol_id = proto.json()["id"]
    published = await client.post(f"/api/v1/protocols/{protocol_id}/publish")
    assert published.status_code in (200, 201), published.text
    run = await client.post(
        "/api/v1/runs", json={"protocol_id": protocol_id, "run_date": "2026-06-04"}
    )
    assert run.status_code in (200, 201), run.text
    return protocol_id, run.json()["id"]


class TestRunTagFilter:
    async def test_filter_runs_by_tag(self, client: AsyncClient) -> None:
        protocol_id, run_id = await _make_run(client)
        assign = await client.post(
            f"/api/v1/runs/{run_id}/tags", json={"key": "qc", "value": "pass"}
        )
        assert assign.status_code == 201, assign.text
        tag_id = assign.json()["id"]

        listed = await client.get(
            f"/api/v1/protocols/{protocol_id}/runs", params={"tags": [tag_id]}
        )
        assert listed.status_code == 200, listed.text
        assert [r["id"] for r in listed.json()] == [run_id]

        none = await client.get(
            f"/api/v1/protocols/{protocol_id}/runs",
            params={"tags": ["00000000-0000-0000-0000-000000000000"]},
        )
        assert none.json() == []
