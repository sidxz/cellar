"""API tests: POST /disclosures — a settable (declared) disclosure date.

The declared date is what the molecule and the request report as the
disclosure date; the observed recorded-at stamps stay alongside it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient


@pytest.fixture
async def undisclosed_molecule_id(client: AsyncClient) -> str:
    org = await client.post(
        "/api/v1/organizations", json={"name": "DisclosureTestOrg", "org_type": "internal"}
    )
    assert org.status_code == 201, org.text
    mol = await client.post(
        "/api/v1/molecules",
        json={"name": "Partner-X", "originating_org_id": org.json()["id"]},
    )
    assert mol.status_code == 201, mol.text
    assert mol.json()["molecule"]["structure_status"] == "undisclosed"
    return mol.json()["molecule"]["id"]


@pytest.mark.asyncio
async def test_declared_disclosure_date_round_trips(
    client: AsyncClient, undisclosed_molecule_id: str
) -> None:
    resp = await client.post(
        "/api/v1/disclosures",
        json={
            "molecule_id": undisclosed_molecule_id,
            "disclosed_smiles": "CCO",
            "disclosure_date": "2024-03-15",
        },
    )
    assert resp.status_code == 201, resp.text
    dr = resp.json()["disclosure_request"]
    assert dr["disclosure_date"] == "2024-03-15"
    assert dr["requested_at"] is not None

    stored = await client.get(f"/api/v1/disclosures/{dr['id']}")
    assert stored.status_code == 200
    assert stored.json()["disclosure_date"] == "2024-03-15"

    mol = await client.get(f"/api/v1/molecules/{undisclosed_molecule_id}")
    assert mol.status_code == 200
    body = mol.json()
    assert body["structure_status"] == "disclosed"
    assert body["disclosure_date"] == "2024-03-15"
    assert body["disclosed_at"] is not None


@pytest.mark.asyncio
async def test_future_disclosure_date_is_rejected(
    client: AsyncClient, undisclosed_molecule_id: str
) -> None:
    resp = await client.post(
        "/api/v1/disclosures",
        json={
            "molecule_id": undisclosed_molecule_id,
            "disclosed_smiles": "CCO",
            "disclosure_date": (datetime.now(UTC).date() + timedelta(days=1)).isoformat(),
        },
    )
    assert resp.status_code == 422, resp.text
