"""API: POST /molecules/{id}/identifiers returns mirror_summary."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.fixture
async def org_id(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/organizations",
        json={"name": "MirrorTestOrg", "org_type": "internal"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.fixture
async def molecule_with_2_batches(client: AsyncClient, org_id: str) -> str:
    """Register a molecule and add 2 batches; return the molecule_id."""
    mol_resp = await client.post(
        "/api/v1/molecules",
        json={
            "name": "MirrorMol",
            "smiles": "c1ccccc1",  # benzene
            "originating_org_id": org_id,
        },
    )
    assert mol_resp.status_code == 201
    mol_id = mol_resp.json()["molecule"]["id"]

    # Create batch 1
    b1 = await client.post(
        "/api/v1/batches",
        json={
            "molecule_id": mol_id,
            "source": "synthesized",
            "amount_value": 10,
            "amount_unit": "mg",
        },
    )
    assert b1.status_code == 201, b1.text

    # Create batch 2
    b2 = await client.post(
        "/api/v1/batches",
        json={
            "molecule_id": mol_id,
            "source": "synthesized",
            "amount_value": 20,
            "amount_unit": "mg",
        },
    )
    assert b2.status_code == 201, b2.text

    return mol_id


@pytest.mark.asyncio
async def test_add_identifier_returns_mirror_summary(
    client: AsyncClient,
    molecule_with_2_batches: str,
) -> None:
    """POST /molecules/{id}/identifiers returns envelope with identifiers + mirror_summary."""
    mol_id = molecule_with_2_batches
    resp = await client.post(
        f"/api/v1/molecules/{mol_id}/identifiers",
        json={
            "identifier": "VENDOR-FOO",
            "identifier_type": "custom",
            "source": "lab notebook",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "identifiers" in body, f"Expected 'identifiers' key in response, got: {list(body.keys())}"
    assert "mirror_summary" in body, f"Expected 'mirror_summary' key in response, got: {list(body.keys())}"
    assert isinstance(body["identifiers"], list)
    assert body["mirror_summary"]["created"] == 2
    assert body["mirror_summary"]["skipped"] == []
