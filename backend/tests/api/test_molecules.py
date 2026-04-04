"""API tests for molecule registration and CRUD endpoints."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


@pytest.fixture
def org_id(workspace_id: uuid.UUID) -> uuid.UUID:
    """Pre-created organization ID for molecule registration."""
    return uuid.uuid4()


@pytest.fixture
async def seed_org(client: AsyncClient, org_id: uuid.UUID) -> uuid.UUID:
    """Create an organization so molecules can reference it."""
    resp = await client.post(
        "/api/v1/organizations",
        json={
            "name": "TestOrg",
            "org_type": "internal",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


class TestRegisterMolecule:
    async def test_register_disclosed_molecule(
        self, client: AsyncClient, seed_org: str
    ) -> None:
        resp = await client.post(
            "/api/v1/molecules",
            json={
                "name": "Aspirin",
                "smiles": "CC(=O)Oc1ccccc1C(=O)O",
                "molecule_type": "small_molecule",
                "originating_org_id": seed_org,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["is_new"] is True
        mol = data["molecule"]
        assert mol["name"] == "Aspirin"
        assert mol["structure_status"] == "disclosed"
        assert mol["structure"]["smiles"] is not None
        assert mol["structure"]["inchi_key"] is not None
        assert mol["descriptors"]["molecular_weight"] > 0
        assert mol["registration_number"].startswith("CV-")

    async def test_register_undisclosed_molecule(
        self, client: AsyncClient, seed_org: str
    ) -> None:
        resp = await client.post(
            "/api/v1/molecules",
            json={
                "name": "Partner Compound X",
                "molecule_type": "small_molecule",
                "originating_org_id": seed_org,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["is_new"] is True
        mol = data["molecule"]
        assert mol["structure_status"] == "undisclosed"
        assert mol["structure"] is None
        assert mol["descriptors"] is None

    async def test_register_invalid_smiles(
        self, client: AsyncClient, seed_org: str
    ) -> None:
        resp = await client.post(
            "/api/v1/molecules",
            json={
                "name": "Bad Molecule",
                "smiles": "not_valid_smiles",
                "molecule_type": "small_molecule",
                "originating_org_id": seed_org,
            },
        )
        assert resp.status_code == 422 or resp.status_code == 400

    async def test_register_with_external_ids(
        self, client: AsyncClient, seed_org: str
    ) -> None:
        resp = await client.post(
            "/api/v1/molecules",
            json={
                "name": "Ibuprofen",
                "smiles": "CC(C)Cc1ccc(cc1)C(C)C(O)=O",
                "molecule_type": "small_molecule",
                "originating_org_id": seed_org,
                "external_ids": [
                    {"identifier": "CAS-15687-27-1", "identifier_type": "cas_number"},
                ],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["molecule"]["identifiers"]) == 1
        assert data["molecule"]["identifiers"][0]["identifier"] == "CAS-15687-27-1"

    async def test_duplicate_inchi_key_returns_existing(
        self, client: AsyncClient, seed_org: str
    ) -> None:
        # Register first
        resp1 = await client.post(
            "/api/v1/molecules",
            json={
                "name": "Aspirin",
                "smiles": "CC(=O)Oc1ccccc1C(=O)O",
                "originating_org_id": seed_org,
            },
        )
        assert resp1.status_code == 201
        assert resp1.json()["is_new"] is True

        # Register again with same SMILES
        resp2 = await client.post(
            "/api/v1/molecules",
            json={
                "name": "Aspirin again",
                "smiles": "CC(=O)Oc1ccccc1C(=O)O",
                "originating_org_id": seed_org,
            },
        )
        assert resp2.status_code == 201
        assert resp2.json()["is_new"] is False
        assert resp2.json()["molecule"]["id"] == resp1.json()["molecule"]["id"]


class TestListMolecules:
    async def test_list_returns_registered_molecules(
        self, client: AsyncClient, seed_org: str
    ) -> None:
        # Register a molecule
        await client.post(
            "/api/v1/molecules",
            json={
                "name": "Caffeine",
                "smiles": "Cn1c(=O)c2c(ncn2C)n(C)c1=O",
                "originating_org_id": seed_org,
            },
        )

        resp = await client.get("/api/v1/molecules")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert len(data["items"]) >= 1
        names = [m["name"] for m in data["items"]]
        assert "Caffeine" in names

    async def test_list_empty_workspace(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/molecules")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["next_cursor"] is None

    async def test_list_with_limit(
        self, client: AsyncClient, seed_org: str
    ) -> None:
        # Register two molecules
        await client.post(
            "/api/v1/molecules",
            json={
                "name": "Mol A",
                "smiles": "C",
                "originating_org_id": seed_org,
            },
        )
        await client.post(
            "/api/v1/molecules",
            json={
                "name": "Mol B",
                "smiles": "CC",
                "originating_org_id": seed_org,
            },
        )

        resp = await client.get("/api/v1/molecules", params={"limit": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["next_cursor"] is not None

        # Fetch next page
        resp2 = await client.get(
            "/api/v1/molecules",
            params={"cursor": data["next_cursor"], "limit": 1},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert len(data2["items"]) == 1
        # IDs should be different
        assert data2["items"][0]["id"] != data["items"][0]["id"]


class TestGetMolecule:
    async def test_get_by_id(
        self, client: AsyncClient, seed_org: str
    ) -> None:
        reg_resp = await client.post(
            "/api/v1/molecules",
            json={
                "name": "Benzene",
                "smiles": "c1ccccc1",
                "originating_org_id": seed_org,
            },
        )
        mol_id = reg_resp.json()["molecule"]["id"]

        resp = await client.get(f"/api/v1/molecules/{mol_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Benzene"

    async def test_get_not_found(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/molecules/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestUpdateMolecule:
    async def test_update_tags(
        self, client: AsyncClient, seed_org: str
    ) -> None:
        reg_resp = await client.post(
            "/api/v1/molecules",
            json={
                "name": "Paracetamol",
                "smiles": "CC(=O)Nc1ccc(O)cc1",
                "originating_org_id": seed_org,
            },
        )
        mol_id = reg_resp.json()["molecule"]["id"]

        resp = await client.patch(
            f"/api/v1/molecules/{mol_id}",
            json={"add_tags": ["tool_compound", "probe"]},
        )
        assert resp.status_code == 200
        assert "tool_compound" in resp.json()["tags"]
        assert "probe" in resp.json()["tags"]

    async def test_update_lifecycle_stage(
        self, client: AsyncClient, seed_org: str
    ) -> None:
        reg_resp = await client.post(
            "/api/v1/molecules",
            json={
                "name": "Test Mol",
                "smiles": "CCCC",
                "originating_org_id": seed_org,
            },
        )
        mol_id = reg_resp.json()["molecule"]["id"]

        resp = await client.patch(
            f"/api/v1/molecules/{mol_id}",
            json={"lifecycle_stage": "active"},
        )
        assert resp.status_code == 200
        assert resp.json()["lifecycle_stage"] == "active"
