"""API test: whole-cell and in-silico protocols can be created and read back."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("protocol_type", ["whole_cell", "in_silico"])
async def test_create_protocol_accepts_type(client: AsyncClient, protocol_type: str) -> None:
    resp = await client.post(
        "/api/v1/protocols",
        json={
            "name": f"Type check {protocol_type}",
            "protocol_type": protocol_type,
            "readout_definitions": [
                {"name": "% Inhibition", "data_type": "numeric", "display_order": 0}
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    got = await client.get(f"/api/v1/protocols/{resp.json()['id']}")
    assert got.status_code == 200, got.text
    assert got.json()["protocol_type"] == protocol_type
