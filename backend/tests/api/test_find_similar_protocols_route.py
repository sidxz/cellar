"""API test for POST /protocols/similar.

Uses the async ``client`` fixture from tests/api/conftest.py (admin auth,
AsyncClient backed by ASGITransport). No headers needed — auth is injected
via dependency_overrides.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.api._protocols import protocol_body


async def test_similar_returns_a_protocol_with_the_same_name_and_readout(
    client: AsyncClient,
) -> None:
    created = await client.post("/api/v1/protocols", json=await protocol_body(client))
    assert created.status_code == 201, created.text
    existing = created.json()

    resp = await client.post(
        "/api/v1/protocols/similar",
        json={"name": existing["name"], "readout_names": ["IC50"]},
    )
    assert resp.status_code == 200
    assert existing["id"] in [m["id"] for m in resp.json()]


async def test_blank_name_returns_empty_list(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/protocols/similar",
        json={"name": "  "},
    )
    assert resp.status_code == 200
    assert resp.json() == []
