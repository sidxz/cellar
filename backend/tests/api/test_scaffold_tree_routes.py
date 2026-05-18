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
