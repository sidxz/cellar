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

    # A Run, to exercise the browse query's non-trivial Run-branch label SQL
    # (protocol name || ' · ' || run_date cast) at runtime — the other branches
    # use a plain name/number column.
    proto = await client.post(
        "/api/v1/protocols",
        json={
            "name": "BrowseProto",
            "protocol_type": "biochemical",
            "readout_definitions": [
                {"name": "IC50", "data_type": "numeric", "display_order": 0}
            ],
        },
    )
    assert proto.status_code in (200, 201), proto.text
    protocol_id = proto.json()["id"]
    published = await client.post(f"/api/v1/protocols/{protocol_id}/publish")
    assert published.status_code in (200, 201), published.text
    run = await client.post(
        "/api/v1/runs", json={"protocol_id": protocol_id, "run_date": "2026-06-04"}
    )
    assert run.status_code in (200, 201), run.text
    run_id = run.json()["id"]

    # Tag project, collection, and run with the SAME (key, value).
    pt = await client.post(
        f"/api/v1/projects/{project_id}/tags", json={"key": "theme", "value": "kinase"}
    )
    assert pt.status_code == 201, pt.text
    tag_id = pt.json()["id"]
    ct = await client.post(
        f"/api/v1/collections/{collection_id}/tags", json={"key": "theme", "value": "kinase"}
    )
    assert ct.status_code == 201, ct.text
    rt = await client.post(
        f"/api/v1/runs/{run_id}/tags", json={"key": "theme", "value": "kinase"}
    )
    assert rt.status_code == 201, rt.text

    resp = await client.get(f"/api/v1/tags/{tag_id}/entities")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    pairs = {(r["entity_type"], r["entity_id"]) for r in rows}
    assert ("Project", project_id) in pairs
    assert ("Collection", collection_id) in pairs
    assert ("Run", run_id) in pairs
    assert all(r["label"] for r in rows)
    # Every row carries the assignment timestamp (drives the "Tagged on" column).
    assert all(r["assigned_at"] for r in rows)
    # Run-branch label SQL executed: "<protocol name> · <run_date>".
    run_label = next(r["label"] for r in rows if r["entity_type"] == "Run")
    assert "BrowseProto" in run_label
    assert " · " in run_label

    only_proj = await client.get(
        f"/api/v1/tags/{tag_id}/entities", params={"types": ["Project"]}
    )
    assert only_proj.status_code == 200, only_proj.text
    assert {r["entity_type"] for r in only_proj.json()} == {"Project"}
