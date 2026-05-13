"""API tests for register-molecule batch policy (re-registration scenarios)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


ETHANOL_SMILES = "CCO"


@pytest.fixture
async def originating_org_id(client: AsyncClient) -> str:
    """Create an organization and return its ID string."""
    resp = await client.post(
        "/api/v1/organizations",
        json={"name": "BatchPolicyTestOrg", "org_type": "internal"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_re_register_same_compound_does_not_create_second_batch_by_default(
    client: AsyncClient, originating_org_id: str
):
    body = {
        "name": "Ethanol-A",
        "smiles": ETHANOL_SMILES,
        "originating_org_id": originating_org_id,
        "batch": {"source": "synthesized", "amount_value": 100, "amount_unit": "mg"},
    }
    first = await client.post("/api/v1/molecules", json=body)
    assert first.status_code == 201
    assert first.json()["batch"] is not None

    body["name"] = "Ethanol-B"  # different alias
    second = await client.post("/api/v1/molecules", json=body)
    assert second.status_code == 201
    payload = second.json()
    assert payload["is_new"] is False
    assert payload["batch"] is None
    assert payload["batch_skipped"] is True
    assert payload["molecule"]["id"] == first.json()["molecule"]["id"]


@pytest.mark.asyncio
async def test_re_register_with_create_batch_on_duplicate_true_creates_second_batch(
    client: AsyncClient, originating_org_id: str
):
    body = {
        "name": "Acetone-A",
        "smiles": "CC(=O)C",
        "originating_org_id": originating_org_id,
        "batch": {"source": "synthesized", "amount_value": 50, "amount_unit": "mg"},
    }
    first = await client.post("/api/v1/molecules", json=body)
    assert first.status_code == 201

    body["name"] = "Acetone-B"
    body["create_batch_on_duplicate"] = True
    second = await client.post("/api/v1/molecules", json=body)
    assert second.status_code == 201
    assert second.json()["is_new"] is False
    assert second.json()["batch"] is not None
    assert second.json()["batch_skipped"] is False
