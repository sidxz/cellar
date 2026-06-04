"""API test: cross-entity tag-browse endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_browse_returns_entities_across_types(client: AsyncClient) -> None:
    proj = await client.post("/api/v1/projects", json={"name": "BrowseProj"})
    assert proj.status_code in (200, 201), proj.text
    project_id = proj.json()["id"]
    col = await client.post("/api/v1/collections", json={"name": "BrowseCol"})
    assert col.status_code in (200, 201), col.text
    collection_id = col.json()["id"]

    pt = await client.post(
        f"/api/v1/projects/{project_id}/tags", json={"key": "theme", "value": "kinase"}
    )
    assert pt.status_code == 201, pt.text
    tag_id = pt.json()["id"]
    ct = await client.post(
        f"/api/v1/collections/{collection_id}/tags", json={"key": "theme", "value": "kinase"}
    )
    assert ct.status_code == 201, ct.text

    resp = await client.get(f"/api/v1/tags/{tag_id}/entities")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    pairs = {(r["entity_type"], r["entity_id"]) for r in rows}
    assert ("Project", project_id) in pairs
    assert ("Collection", collection_id) in pairs
    assert all(r["label"] for r in rows)

    only_proj = await client.get(
        f"/api/v1/tags/{tag_id}/entities", params={"types": ["Project"]}
    )
    assert only_proj.status_code == 200, only_proj.text
    assert {r["entity_type"] for r in only_proj.json()} == {"Project"}
