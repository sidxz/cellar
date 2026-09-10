"""API tests for register-molecule batch policy (re-registration scenarios)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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


@pytest.mark.asyncio
@pytest.mark.parametrize("smiles", [ETHANOL_SMILES, None], ids=["disclosed", "undisclosed"])
async def test_scientist_name_round_trips(
    client: AsyncClient, originating_org_id: str, smiles: str | None
):
    """The person half of provenance is captured at registration and read back."""
    body = {
        "name": f"Prov-{smiles or 'undisclosed'}",
        "smiles": smiles,
        "originating_org_id": originating_org_id,
        "scientist_name": "A. Chemist",
    }
    created = await client.post("/api/v1/molecules", json=body)
    assert created.status_code == 201, created.text
    mol = created.json()["molecule"]
    assert mol["scientist_name"] == "A. Chemist"

    read = await client.get(f"/api/v1/molecules/{mol['id']}")
    assert read.status_code == 200
    assert read.json()["scientist_name"] == "A. Chemist"


@pytest.mark.asyncio
async def test_declared_disclosure_date_round_trips_on_registration(
    client: AsyncClient, originating_org_id: str
):
    body = {
        "name": "Declared-1",
        "smiles": "CCN",
        "originating_org_id": originating_org_id,
        "disclosure_date": "2024-03-15",
    }
    created = await client.post("/api/v1/molecules", json=body)
    assert created.status_code == 201, created.text
    mol = created.json()["molecule"]
    assert mol["disclosure_date"] == "2024-03-15"
    read = await client.get(f"/api/v1/molecules/{mol['id']}")
    assert read.json()["disclosure_date"] == "2024-03-15"


@pytest.mark.asyncio
async def test_future_disclosure_date_on_registration_is_rejected(
    client: AsyncClient, originating_org_id: str
):
    body = {
        "name": "Declared-future",
        "smiles": "CCCN",
        "originating_org_id": originating_org_id,
        "disclosure_date": (datetime.now(UTC).date() + timedelta(days=1)).isoformat(),
    }
    resp = await client.post("/api/v1/molecules", json=body)
    assert resp.status_code == 422, resp.text
