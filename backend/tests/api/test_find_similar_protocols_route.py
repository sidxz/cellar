"""API test for POST /protocols/similar.

Uses the async ``client`` fixture from tests/api/conftest.py (admin auth,
AsyncClient backed by ASGITransport). No headers needed — auth is injected
via dependency_overrides.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def test_similar_returns_200_and_list(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/protocols/similar",
        json={"name": "RNAP core IC50", "readout_names": ["IC50"]},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_blank_name_returns_empty_list(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/protocols/similar",
        json={"name": "  "},
    )
    assert resp.status_code == 200
    assert resp.json() == []
