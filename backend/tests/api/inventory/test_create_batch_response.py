"""API: POST /batches returns CreateBatchResponse envelope with mirror_summary."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.fixture
async def org_id(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/organizations",
        json={"name": "BatchMirrorTestOrg", "org_type": "internal"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.fixture
async def molecule_with_2_identifiers(client: AsyncClient, org_id: str) -> str:
    """Register a molecule and add 2 identifiers; return the molecule_id."""
    mol_resp = await client.post(
        "/api/v1/molecules",
        json={
            "name": "BatchMirrorMol",
            "smiles": "c1ccccc1",  # benzene
            "originating_org_id": org_id,
        },
    )
    assert mol_resp.status_code == 201, mol_resp.text
    mol_id = mol_resp.json()["molecule"]["id"]

    # Add identifier 1
    r1 = await client.post(
        f"/api/v1/molecules/{mol_id}/identifiers",
        json={
            "identifier": "MIRROR-FOO",
            "identifier_type": "custom",
            "source": "lab notebook",
        },
    )
    assert r1.status_code == 201, r1.text

    # Add identifier 2
    r2 = await client.post(
        f"/api/v1/molecules/{mol_id}/identifiers",
        json={
            "identifier": "MIRROR-BAR",
            "identifier_type": "external_lot",
            "source": "vendor",
        },
    )
    assert r2.status_code == 201, r2.text

    return mol_id


@pytest.mark.asyncio
async def test_create_batch_returns_envelope_with_mirror_summary(
    client: AsyncClient,
    molecule_with_2_identifiers: str,
) -> None:
    """POST /batches returns {batch, mirror_summary} envelope — not a flat BatchResponse."""
    mol_id = molecule_with_2_identifiers
    resp = await client.post(
        "/api/v1/batches",
        json={
            "molecule_id": mol_id,
            "source": "synthesized",
            "amount_value": 10.0,
            "amount_unit": "mg",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "batch" in body, f"Expected 'batch' key in response, got: {list(body.keys())}"
    assert "mirror_summary" in body, (
        f"Expected 'mirror_summary' key in response, got: {list(body.keys())}"
    )
    # batch sub-object has standard BatchResponse fields
    assert "id" in body["batch"]
    assert "batch_number" in body["batch"]
    # mirror_summary reports 3 mirrors created:
    # 1 auto-promoted from molecule name + 2 explicitly added identifiers
    assert body["mirror_summary"]["created"] == 3
    assert body["mirror_summary"]["skipped"] == []


@pytest.mark.asyncio
async def test_create_batch_mirror_summary_empty_when_no_identifiers(
    client: AsyncClient,
    org_id: str,
) -> None:
    """POST /batches returns mirror_summary with created=0 when molecule has no identifiers."""
    mol_resp = await client.post(
        "/api/v1/molecules",
        json={
            "name": "NoIdentifierMol",
            "smiles": "CCO",  # ethanol
            "originating_org_id": org_id,
        },
    )
    assert mol_resp.status_code == 201, mol_resp.text
    mol_id = mol_resp.json()["molecule"]["id"]

    resp = await client.post(
        "/api/v1/batches",
        json={
            "molecule_id": mol_id,
            "source": "synthesized",
            "amount_value": 5.0,
            "amount_unit": "mg",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "batch" in body
    assert "mirror_summary" in body
    # 1 mirror created from the auto-promoted molecule name identifier
    assert body["mirror_summary"]["created"] == 1
    assert body["mirror_summary"]["skipped"] == []
