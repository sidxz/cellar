"""API tests: POST /disclosures — a settable (declared) disclosure date.

The declared date is what the molecule and the request report as the
disclosure date; the observed recorded-at stamps stay alongside it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import uuid

from httpx import AsyncClient

from tests.api.conftest import AUTH_ORG_ID


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


@pytest.mark.asyncio
async def test_submit_disclosure_records_requester_org(
    client: AsyncClient, undisclosed_molecule_id: str
) -> None:
    resp = await client.post(
        "/api/v1/disclosures",
        json={"molecule_id": undisclosed_molecule_id, "disclosed_smiles": "CCCN"},
    )
    assert resp.status_code == 201, resp.text
    dr = resp.json()["disclosure_request"]
    assert (dr["requested_by_org_id"], dr["disclosing_org_id"]) == (str(AUTH_ORG_ID),) * 2
    mol = (await client.get(f"/api/v1/molecules/{undisclosed_molecule_id}")).json()
    assert mol["disclosed_by_org_id"] == str(AUTH_ORG_ID)


@pytest.mark.asyncio
async def test_submit_disclosure_with_disabled_org_is_422(
    client: AsyncClient, undisclosed_molecule_id: str
) -> None:
    resp = await client.post(
        "/api/v1/disclosures",
        json={
            "molecule_id": undisclosed_molecule_id,
            "disclosed_smiles": "CCCCN",
            "disclosing_org_id": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_merge_target_keeps_its_discloser(
    client: AsyncClient, undisclosed_molecule_id: str
) -> None:
    """Disclosing a structure that is already registered merges into that compound; the
    compound keeps the discloser it already had."""
    org = (await client.get(f"/api/v1/molecules/{undisclosed_molecule_id}")).json()[
        "originating_org_id"
    ]
    target = (
        await client.post(
            "/api/v1/molecules",
            json={"name": "Known-target", "smiles": "CCCCCCN", "originating_org_id": org},
        )
    ).json()["molecule"]
    before = (target["disclosed_by"], target["disclosed_by_org_id"])

    resp = await client.post(
        "/api/v1/disclosures",
        json={
            "molecule_id": undisclosed_molecule_id,
            "disclosed_smiles": "CCCCCCN",
            "disclosing_org_id": str(AUTH_ORG_ID),
        },
    )
    assert resp.status_code == 201, resp.text
    after = (await client.get(f"/api/v1/molecules/{target['id']}")).json()
    assert (after["disclosed_by"], after["disclosed_by_org_id"]) == before


@pytest.mark.asyncio
async def test_reregistering_existing_structure_keeps_discloser(
    client: AsyncClient, other_editor_client: AsyncClient, undisclosed_molecule_id: str
) -> None:
    org = (await client.get(f"/api/v1/molecules/{undisclosed_molecule_id}")).json()[
        "originating_org_id"
    ]
    first = (
        await client.post(
            "/api/v1/molecules",
            json={"name": "Once", "smiles": "CCCCCCCN", "originating_org_id": org},
        )
    ).json()["molecule"]
    again = await other_editor_client.post(
        "/api/v1/molecules",
        json={"name": "Twice", "smiles": "CCCCCCCN", "originating_org_id": org},
    )
    assert again.status_code == 201, again.text
    after = (await client.get(f"/api/v1/molecules/{first['id']}")).json()
    assert (after["disclosed_by"], after["disclosed_by_org_id"]) == (
        first["disclosed_by"],
        first["disclosed_by_org_id"],
    )

