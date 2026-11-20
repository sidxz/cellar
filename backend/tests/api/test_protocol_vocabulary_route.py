"""API test for GET /protocols/vocabulary.

Uses the async ``client`` fixture from tests/api/conftest.py (admin auth via
dependency_overrides, AsyncClient backed by ASGITransport). No auth headers
needed — auth is injected via dependency_overrides.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.api._protocols import protocol_body


async def test_vocabulary_suggests_readout_names_like_the_query(client: AsyncClient) -> None:
    body = await protocol_body(
        client,
        readout_definitions=[
            {"name": "Percent inhibition", "data_type": "numeric", "display_order": 0},
            {"name": "Kd", "data_type": "numeric", "display_order": 1},
        ],
    )
    created = await client.post("/api/v1/protocols", json=body)
    assert created.status_code == 201, created.text

    resp = await client.get(
        "/api/v1/protocols/vocabulary",
        params={"field": "readout_name", "q": "inh"},
    )
    assert resp.status_code == 200
    assert resp.json() == ["Percent inhibition"]


async def test_vocabulary_unknown_field_returns_empty(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/protocols/vocabulary",
        params={"field": "bogus"},
    )
    assert resp.status_code == 200
    assert resp.json() == []
