"""API test for GET /protocols/vocabulary.

Uses the async ``client`` fixture from tests/api/conftest.py (admin auth via
dependency_overrides, AsyncClient backed by ASGITransport). No auth headers
needed — auth is injected via dependency_overrides.
"""

from __future__ import annotations

from httpx import AsyncClient


async def test_vocabulary_returns_200_list(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/protocols/vocabulary",
        params={"field": "readout_name", "q": "inh"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_vocabulary_unknown_field_returns_empty(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/protocols/vocabulary",
        params={"field": "bogus"},
    )
    assert resp.status_code == 200
    assert resp.json() == []
