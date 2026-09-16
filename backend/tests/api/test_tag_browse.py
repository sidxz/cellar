"""API test: cross-entity tag-browse endpoint."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.api.conftest import OTHER_ORG_ID

pytestmark = pytest.mark.asyncio


async def _register_plate(client: AsyncClient, **overrides):
    body = {
        "barcode": f"PLT-{uuid.uuid4().hex[:8]}",
        "plate_label": "Test Plate",
        "format": "96",
        "plate_type": "assay",
    }
    body.update(overrides)
    return await client.post("/api/v1/plates", json=body)


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

    resp = await client.get("/api/v1/tags/entities", params={"tags": [tag_id]})
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
        "/api/v1/tags/entities", params={"tags": [tag_id], "types": ["Project"]}
    )
    assert only_proj.status_code == 200, only_proj.text
    assert {r["entity_type"] for r in only_proj.json()} == {"Project"}


async def test_browse_multi_tag_any_and_all(client: AsyncClient) -> None:
    c1 = (await client.post("/api/v1/collections", json={"name": "MT-1"})).json()["id"]
    c2 = (await client.post("/api/v1/collections", json={"name": "MT-2"})).json()["id"]
    # Both carry tag A; only c1 also carries tag B (unique keys keep them this test's).
    a = (
        await client.post(f"/api/v1/collections/{c1}/tags", json={"key": "mtany-alpha"})
    ).json()["id"]
    await client.post(f"/api/v1/collections/{c2}/tags", json={"key": "mtany-alpha"})
    b = (
        await client.post(f"/api/v1/collections/{c1}/tags", json={"key": "mtany-beta"})
    ).json()["id"]

    # ANY: A or B → both collections; c1 appears once despite carrying both (GROUP BY).
    any_resp = await client.get(
        "/api/v1/tags/entities", params={"tags": [a, b], "tag_logic": "any"}
    )
    assert any_resp.status_code == 200, any_resp.text
    any_rows = any_resp.json()
    assert {r["entity_id"] for r in any_rows if r["entity_type"] == "Collection"} == {c1, c2}
    assert len([r for r in any_rows if r["entity_id"] == c1]) == 1

    # ALL: A and B → only c1.
    all_resp = await client.get(
        "/api/v1/tags/entities", params={"tags": [a, b], "tag_logic": "all"}
    )
    assert all_resp.status_code == 200, all_resp.text
    assert {r["entity_id"] for r in all_resp.json() if r["entity_type"] == "Collection"} == {c1}


class TestBrowsePlateVisibility:
    """Private-org plate exclusion on the tag-browse hydration query (S2 Task 5c)."""

    async def test_tagged_foreign_org_plate_excluded_for_editor_visible_for_own_org(
        self,
        client: AsyncClient,
        editor_client_own_org: AsyncClient,
        editor_client_other_org: AsyncClient,
    ) -> None:
        reg = await _register_plate(client, owner_org_id=str(OTHER_ORG_ID))
        assert reg.status_code == 201, reg.text
        plate_id = reg.json()["id"]

        # The plate's own org tags it.
        tagged = await editor_client_other_org.post(
            f"/api/v1/plates/{plate_id}/tags", json={"key": "browse-vis"}
        )
        assert tagged.status_code == 201, tagged.text
        tag_id = tagged.json()["id"]

        # An editor in AUTH_ORG_ID is foreign to the plate's org — it must
        # drop out of the browse results entirely, not render unlabeled.
        resp = await editor_client_own_org.get("/api/v1/tags/entities", params={"tags": [tag_id]})
        assert resp.status_code == 200, resp.text
        assert plate_id not in {r["entity_id"] for r in resp.json()}

        # The plate's own org still sees it in the browse.
        resp_own = await editor_client_other_org.get(
            "/api/v1/tags/entities", params={"tags": [tag_id]}
        )
        assert resp_own.status_code == 200, resp_own.text
        rows_own = {r["entity_id"]: r for r in resp_own.json()}
        assert plate_id in rows_own
        assert rows_own[plate_id]["entity_type"] == "Plate"
