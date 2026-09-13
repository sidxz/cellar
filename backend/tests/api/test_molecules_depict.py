"""API tests for POST /api/v1/molecules/depict.

There were none, which is how the route sat raising TypeError on every call
(it passed a workspace_id the query does not declare) long enough for the
Excel-export structure images to depend on a 500.
"""

from __future__ import annotations

import base64

import pytest
from httpx import AsyncClient

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
CAFFEINE = "CN1C=NC2=C1C(=O)N(C)C(=O)N2C"


@pytest.mark.asyncio
async def test_renders_a_png_per_smiles(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/molecules/depict", json={"smiles_list": [ASPIRIN, CAFFEINE]}
    )

    assert res.status_code == 200, res.text
    images = res.json()["images"]
    assert set(images) == {ASPIRIN, CAFFEINE}
    # Each value is a base64 PNG, not an empty string or a data: URL.
    for smiles, encoded in images.items():
        assert base64.b64decode(encoded)[:8] == b"\x89PNG\r\n\x1a\n", smiles


@pytest.mark.asyncio
async def test_unparseable_smiles_are_skipped_not_fatal(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/molecules/depict", json={"smiles_list": [ASPIRIN, "not-a-molecule"]}
    )

    assert res.status_code == 200, res.text
    assert list(res.json()["images"]) == [ASPIRIN]


@pytest.mark.asyncio
async def test_honours_requested_dimensions(client: AsyncClient) -> None:
    small = await client.post(
        "/api/v1/molecules/depict", json={"smiles_list": [ASPIRIN], "width": 80, "height": 60}
    )
    large = await client.post(
        "/api/v1/molecules/depict", json={"smiles_list": [ASPIRIN], "width": 300, "height": 200}
    )

    assert small.status_code == 200, small.text
    assert large.status_code == 200, large.text
    assert len(large.json()["images"][ASPIRIN]) > len(small.json()["images"][ASPIRIN])


@pytest.mark.asyncio
async def test_an_empty_list_renders_nothing(client: AsyncClient) -> None:
    res = await client.post("/api/v1/molecules/depict", json={"smiles_list": []})

    assert res.status_code == 200, res.text
    assert res.json()["images"] == {}


@pytest.mark.asyncio
async def test_rejects_more_than_the_batch_limit(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/molecules/depict", json={"smiles_list": [ASPIRIN] * 201}
    )

    assert res.status_code == 422, res.text
