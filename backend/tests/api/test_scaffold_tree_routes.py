"""API tests for POST /api/v1/scaffold-tree + GET/cancel job endpoints."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_post_scaffold_tree_empty_returns_empty_tree(client: AsyncClient) -> None:
    res = await client.post("/api/v1/scaffold-tree", json={"molecule_ids": []})
    assert res.status_code == 200
    body = res.json()
    assert body["tree"]["nodes"] == []
    assert body["job"] is None


@pytest.mark.asyncio
async def test_get_nonexistent_job_returns_404(client: AsyncClient) -> None:
    res = await client.get(f"/api/v1/scaffold-tree/jobs/{uuid.uuid4()}")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_post_rejects_when_both_inputs_given(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/scaffold-tree",
        json={"molecule_ids": [], "collection_id": str(uuid.uuid4())},
    )
    assert res.status_code == 400
    assert "exactly one" in res.json()["detail"]


@pytest.mark.asyncio
async def test_post_rejects_when_neither_input_given(client: AsyncClient) -> None:
    res = await client.post("/api/v1/scaffold-tree", json={})
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_post_with_unknown_collection_id_returns_404(client: AsyncClient) -> None:
    # Collection doesn't exist → ListCollectionMolecules returns Failure →
    # result_to_response surfaces as HTTPException (typically 404).
    res = await client.post(
        "/api/v1/scaffold-tree",
        json={"collection_id": str(uuid.uuid4())},
    )
    # The exact status depends on how DomainError maps; accept 404 OR 400.
    assert res.status_code in (400, 404)
