"""API tests: tag-filtering the per-protocol run list endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _make_run(client: AsyncClient) -> tuple[str, str]:
    """Create a protocol + run; return (protocol_id, run_id)."""
    proto = await client.post(
        "/api/v1/protocols",
        json={
            "name": "TagRunProto",
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
    return protocol_id, run.json()["id"]


class TestRunTagFilter:
    async def test_filter_runs_by_tag(self, client: AsyncClient) -> None:
        protocol_id, run_id = await _make_run(client)

        # A second run on the same protocol, left untagged — the filter must exclude it.
        run2 = await client.post(
            "/api/v1/runs", json={"protocol_id": protocol_id, "run_date": "2026-06-05"}
        )
        assert run2.status_code in (200, 201), run2.text
        untagged_id = run2.json()["id"]

        assign = await client.post(
            f"/api/v1/runs/{run_id}/tags", json={"key": "qc", "value": "pass"}
        )
        assert assign.status_code == 201, assign.text
        tag_id = assign.json()["id"]

        listed = await client.get(
            f"/api/v1/protocols/{protocol_id}/runs", params={"tags": [tag_id]}
        )
        assert listed.status_code == 200, listed.text
        result_ids = [r["id"] for r in listed.json()]
        assert run_id in result_ids
        assert untagged_id not in result_ids

        none = await client.get(
            f"/api/v1/protocols/{protocol_id}/runs",
            params={"tags": ["00000000-0000-0000-0000-000000000000"]},
        )
        assert none.status_code == 200, none.text
        assert none.json() == []


class TestBatchTagFilter:
    async def test_filter_global_batches_by_tag(self, client: AsyncClient) -> None:
        org = await client.post(
            "/api/v1/organizations", json={"name": "BatchTagOrg", "org_type": "internal"}
        )
        assert org.status_code == 201, org.text
        org_id = org.json()["id"]

        mol = await client.post(
            "/api/v1/molecules",
            json={"smiles": "CCO", "name": "ethanol-tag", "originating_org_id": org_id},
        )
        assert mol.status_code in (200, 201), mol.text
        molecule_id = mol.json()["molecule"]["id"]

        b1 = await client.post(
            "/api/v1/batches",
            json={
                "molecule_id": molecule_id,
                "source": "synthesized",
                "amount_value": 10.0,
                "amount_unit": "mg",
            },
        )
        assert b1.status_code in (200, 201), b1.text
        batch_id = b1.json()["batch"]["id"]

        b2 = await client.post(
            "/api/v1/batches",
            json={
                "molecule_id": molecule_id,
                "source": "synthesized",
                "amount_value": 5.0,
                "amount_unit": "mg",
            },
        )
        assert b2.status_code in (200, 201), b2.text
        untagged_id = b2.json()["batch"]["id"]

        assign = await client.post(
            f"/api/v1/batches/{batch_id}/tags", json={"key": "freezer", "value": "A3"}
        )
        assert assign.status_code == 201, assign.text
        tag_id = assign.json()["id"]

        listed = await client.get("/api/v1/batches", params={"tags": [tag_id]})
        assert listed.status_code == 200, listed.text
        ids = [row["id"] for row in listed.json()["items"]]
        assert batch_id in ids
        assert untagged_id not in ids


class TestCampaignTagFilter:
    async def test_filter_campaigns_by_tag(self, client: AsyncClient) -> None:
        proj = await client.post("/api/v1/projects", json={"name": "TagCampProj"})
        assert proj.status_code in (200, 201), proj.text
        project_id = proj.json()["id"]
        camp = await client.post(
            "/api/v1/campaigns", json={"project_id": project_id, "name": "C-tag"}
        )
        assert camp.status_code in (200, 201), camp.text
        campaign_id = camp.json()["id"]

        # A second campaign in the same project, left untagged — filter must exclude it.
        camp2 = await client.post(
            "/api/v1/campaigns", json={"project_id": project_id, "name": "C-untagged"}
        )
        assert camp2.status_code in (200, 201), camp2.text
        untagged_id = camp2.json()["id"]

        assign = await client.post(
            f"/api/v1/campaigns/{campaign_id}/tags", json={"key": "lead-series"}
        )
        assert assign.status_code == 201, assign.text
        tag_id = assign.json()["id"]

        listed = await client.get(
            "/api/v1/campaigns", params={"project_id": project_id, "tags": [tag_id]}
        )
        assert listed.status_code == 200, listed.text
        result_ids = [c["id"] for c in listed.json()["items"]]
        assert campaign_id in result_ids
        assert untagged_id not in result_ids
