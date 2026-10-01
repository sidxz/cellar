"""API tests for register-molecule batch policy (re-registration scenarios)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.api.conftest import _create_test_app
from tests.fakes.fake_auth import FakeAuth


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


# ---------------------------------------------------------------------------
# Registering straight into projects
# ---------------------------------------------------------------------------


async def _project(client: AsyncClient, name: str) -> str:
    resp = await client.post("/api/v1/projects", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _project_ids_of(client: AsyncClient, molecule_id: str) -> set[str]:
    resp = await client.get(f"/api/v1/molecules/{molecule_id}/projects")
    assert resp.status_code == 200, resp.text
    return set(resp.json())  # the route returns a list of project UUIDs


@pytest.mark.asyncio
async def test_register_links_new_compound_to_projects(
    client: AsyncClient, originating_org_id: str
):
    p1, p2 = await _project(client, "Reg P1"), await _project(client, "Reg P2")
    resp = await client.post(
        "/api/v1/molecules",
        json={
            "name": "RegLinked",
            "smiles": "CCCCCCCCCCCCCCN",
            "originating_org_id": originating_org_id,
            "project_ids": [p1, p2, p1],
        },
    )
    assert resp.status_code == 201, resp.text
    assert await _project_ids_of(client, resp.json()["molecule"]["id"]) == {p1, p2}


@pytest.mark.asyncio
async def test_register_duplicate_links_existing_compound(
    client: AsyncClient, originating_org_id: str
):
    first = await client.post(
        "/api/v1/molecules",
        json={
            "name": "DupA",
            "smiles": "CCCCCCCCCCCCCCCN",
            "originating_org_id": originating_org_id,
        },
    )
    proj = await _project(client, "Dup P")
    second = await client.post(
        "/api/v1/molecules",
        json={
            "name": "DupB",
            "smiles": "CCCCCCCCCCCCCCCN",
            "originating_org_id": originating_org_id,
            "project_ids": [proj],
        },
    )
    assert second.status_code == 201, second.text
    assert second.json()["is_new"] is False
    assert await _project_ids_of(client, first.json()["molecule"]["id"]) == {proj}


@pytest.mark.asyncio
async def test_register_with_archived_project_registers_nothing(
    client: AsyncClient, originating_org_id: str
):
    proj = await _project(client, "Archived Reg P")
    assert (await client.post(f"/api/v1/projects/{proj}/archive")).status_code == 200
    resp = await client.post(
        "/api/v1/molecules",
        json={
            "name": "NeverRegistered",
            "smiles": "CCCCCCCCCCCCCCCCN",
            "originating_org_id": originating_org_id,
            "project_ids": [proj],
        },
    )
    assert resp.status_code == 422
    listed = await client.get("/api/v1/molecules", params={"q": "NeverRegistered"})
    assert listed.json()["items"] == []


@pytest.mark.asyncio
async def test_register_into_project_without_editor_role_is_403(
    client: AsyncClient,
    originating_org_id: str,
    database_url: str,
    workspace_id: uuid.UUID,
):
    proj = await _project(client, "Not Yours P")
    app = _create_test_app(
        database_url, FakeAuth(role="editor", workspace_id=workspace_id, user_id=uuid.uuid4())
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as stranger:  # type: ignore[arg-type]
        resp = await stranger.post(
            "/api/v1/molecules",
            json={
                "name": "StrangerCmpd",
                "smiles": "CCCCCCCCCCCCCCCCCCCO",
                "originating_org_id": originating_org_id,
                "project_ids": [proj],
            },
        )
    await app.state.container[AsyncEngine].dispose()
    assert resp.status_code == 403
    listed = await client.get("/api/v1/molecules", params={"q": "StrangerCmpd"})
    assert listed.json()["items"] == []


@pytest.mark.asyncio
async def test_identifier_conflict_links_nothing(client: AsyncClient, originating_org_id: str):
    # The name is an identifier: "Taken" now belongs to a different structure.
    await client.post(
        "/api/v1/molecules",
        json={
            "name": "Taken",
            "smiles": "CCCCCCCCCCCCCCCCCN",
            "originating_org_id": originating_org_id,
        },
    )
    proj = await _project(client, "Conflict P")
    resp = await client.post(
        "/api/v1/molecules",
        json={
            "name": "Taken",
            "smiles": "c1ccccc1CCCCCCCCN",
            "originating_org_id": originating_org_id,
            "project_ids": [proj],
        },
    )
    assert resp.status_code == 409
    stats = await client.get("/api/v1/projects/stats", params={"project_ids": [proj]})
    assert stats.json()[proj]["molecule_count"] == 0


@pytest.mark.asyncio
async def test_disclosing_an_undisclosed_compound_links_it(
    client: AsyncClient, originating_org_id: str
):
    undisclosed = await client.post(
        "/api/v1/molecules",
        json={"name": "UND-PROJ-1", "originating_org_id": originating_org_id},
    )
    assert undisclosed.status_code == 201, undisclosed.text
    proj = await _project(client, "Disclosed P")

    disclosed = await client.post(
        "/api/v1/molecules",
        json={
            "name": "UND-PROJ-1",
            "smiles": "CCCCCCCCCCCCCCCCCCCCN",
            "originating_org_id": originating_org_id,
            "project_ids": [proj],
        },
    )
    assert disclosed.status_code == 201, disclosed.text
    assert disclosed.json()["action"] == "disclosed"
    assert await _project_ids_of(client, undisclosed.json()["molecule"]["id"]) == {proj}
