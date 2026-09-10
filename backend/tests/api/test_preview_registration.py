"""API: POST /molecules/preview-registration — advisory forecast, writes nothing."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.fixture
async def org_id(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/organizations", json={"name": "PreviewTestOrg", "org_type": "internal"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_preview_forecasts_the_register_outcomes(client: AsyncClient, org_id: str) -> None:
    known = await client.post(
        "/api/v1/molecules",
        json={"name": "PV-Known", "smiles": "CCO", "originating_org_id": org_id},
    )
    assert known.status_code == 201, known.text
    known_id = known.json()["molecule"]["id"]

    resp = await client.post(
        "/api/v1/molecules/preview-registration",
        json={
            "items": [
                # exact register payloads are accepted as-is (extra keys ignored)
                {"name": "PV-Alias", "smiles": "OCC", "originating_org_id": org_id},
                {"name": "PV-Known", "smiles": "CCCC", "originating_org_id": org_id},
                {"name": "PV-Fresh", "smiles": "CCCCC", "originating_org_id": org_id},
                {"name": "PV-Known", "smiles": None, "originating_org_id": org_id},
                {"name": "PV-Broken", "smiles": "not a smiles", "originating_org_id": org_id},
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    by_index = {i["index"]: i for i in resp.json()["items"]}
    assert by_index[0]["action"] == "deduplicated"
    assert by_index[0]["matched_molecule_id"] == known_id
    assert by_index[1]["action"] == "conflict"
    assert "PV-Known" in by_index[1]["conflict_reason"]
    assert by_index[2]["action"] == "registered"
    assert by_index[3]["action"] == "conflict"
    assert by_index[4]["action"] is None
    assert by_index[4]["error"]

    # Advisory only: nothing was written or reserved, so the fresh one still registers.
    fresh = await client.post(
        "/api/v1/molecules",
        json={"name": "PV-Fresh", "smiles": "CCCCC", "originating_org_id": org_id},
    )
    assert fresh.status_code == 201, fresh.text
    assert fresh.json()["is_new"] is True


@pytest.mark.asyncio
async def test_preview_batch_over_cap_is_422(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/molecules/preview-registration",
        json={"items": [{"name": f"N{i}", "smiles": None} for i in range(501)]},
    )
    assert resp.status_code == 422, resp.text
    assert "500" in resp.text
