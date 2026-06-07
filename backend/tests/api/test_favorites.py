"""API contract tests for the favorites endpoints."""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration


async def test_add_list_remove_roundtrip(client) -> None:
    entity = str(uuid.uuid4())

    # add
    resp = await client.post(
        "/api/v1/favorites", json={"entity_type": "project", "entity_id": entity}
    )
    assert resp.status_code == 200
    assert resp.json()["entity_id"] == entity

    # list
    resp = await client.get("/api/v1/favorites", params={"entity_type": "project"})
    assert resp.status_code == 200
    assert entity in [f["entity_id"] for f in resp.json()]

    # remove
    resp = await client.delete(f"/api/v1/favorites/project/{entity}")
    assert resp.status_code == 204

    # gone
    resp = await client.get("/api/v1/favorites", params={"entity_type": "project"})
    assert entity not in [f["entity_id"] for f in resp.json()]


async def test_add_is_idempotent(client) -> None:
    entity = str(uuid.uuid4())
    await client.post("/api/v1/favorites", json={"entity_type": "project", "entity_id": entity})
    await client.post("/api/v1/favorites", json={"entity_type": "project", "entity_id": entity})
    resp = await client.get("/api/v1/favorites", params={"entity_type": "project"})
    assert [f["entity_id"] for f in resp.json()].count(entity) == 1
