"""API tests for molecule registration and CRUD endpoints."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from httpx import AsyncClient

from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


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
        # The name is auto-promoted to a "custom" identifier alongside the explicit CAS.
        identifiers = {(i["identifier"], i["identifier_type"]) for i in data["molecule"]["identifiers"]}
        assert ("CAS-15687-27-1", "cas_number") in identifiers
        assert ("Ibuprofen", "custom") in identifiers

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


class TestListMoleculesByIds:
    async def test_bulk_by_ids_returns_matching_molecules(
        self, client: AsyncClient, seed_org: str
    ) -> None:
        """GET /api/v1/molecules?ids=<csv> returns exactly the requested molecules."""
        resp1 = await client.post(
            "/api/v1/molecules",
            json={"name": "Mol-BulkA", "smiles": "C", "originating_org_id": seed_org},
        )
        resp2 = await client.post(
            "/api/v1/molecules",
            json={"name": "Mol-BulkB", "smiles": "CC", "originating_org_id": seed_org},
        )
        # Third molecule that should NOT appear in results
        resp3 = await client.post(
            "/api/v1/molecules",
            json={"name": "Mol-BulkC", "smiles": "CCC", "originating_org_id": seed_org},
        )
        id1 = resp1.json()["molecule"]["id"]
        id2 = resp2.json()["molecule"]["id"]
        id3 = resp3.json()["molecule"]["id"]

        resp = await client.get("/api/v1/molecules", params={"ids": f"{id1},{id2}"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "items" in data
        returned_ids = {m["id"] for m in data["items"]}
        assert returned_ids == {id1, id2}
        assert id3 not in returned_ids
        assert data["next_cursor"] is None

    async def test_bulk_by_ids_workspace_scoped(self, client: AsyncClient, seed_org: str) -> None:
        """An unknown (or wrong-workspace) id in the csv is silently omitted."""
        resp = await client.post(
            "/api/v1/molecules",
            json={"name": "Mol-Scope", "smiles": "c1ccccc1", "originating_org_id": seed_org},
        )
        real_id = resp.json()["molecule"]["id"]
        fake_id = str(uuid.uuid4())

        resp2 = await client.get("/api/v1/molecules", params={"ids": f"{real_id},{fake_id}"})
        assert resp2.status_code == 200, resp2.text
        returned_ids = {m["id"] for m in resp2.json()["items"]}
        assert real_id in returned_ids
        assert fake_id not in returned_ids


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


# ---------------------------------------------------------------------------
# POST /api/v1/molecules/test-counts
# ---------------------------------------------------------------------------

_SEED_USER = uuid.UUID("eeeeeeee-0000-0000-0000-000000000002")


async def _seed_protocol_run_curve(
    uow: AsyncUnitOfWork,
    workspace_id: uuid.UUID,
    molecule_id: uuid.UUID,
    *,
    project_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert a protocol, run, and one DR curve for molecule_id. Returns protocol_id."""
    protocol_id = uuid.uuid4()
    run_id = uuid.uuid4()
    rd_id = uuid.uuid4()
    curve_id = uuid.uuid4()

    async with uow:
        await uow.session.execute(
            sa.text(
                "INSERT INTO protocols "
                "(id, workspace_id, name, protocol_type, status, "
                "is_locked, dose_unit, pos_control_signal, version, protocol_version, created_by) "
                "VALUES (:id, :ws, :name, 'biochemical', 'active', "
                "false, 'uM', 'high', 1, 1, :user) ON CONFLICT DO NOTHING"
            ),
            {"id": protocol_id, "ws": workspace_id, "name": f"Proto-{str(protocol_id)[:8]}", "user": _SEED_USER},
        )
        if project_id is not None:
            await uow.session.execute(
                sa.text(
                    "INSERT INTO protocol_projects (protocol_id, project_id) "
                    "VALUES (:proto, :proj) ON CONFLICT DO NOTHING"
                ),
                {"proto": protocol_id, "proj": project_id},
            )
        await uow.session.execute(
            sa.text(
                "INSERT INTO readout_definitions "
                "(id, protocol_id, name, data_type, display_order, is_calculated) "
                "VALUES (:id, :proto, :name, 'numeric', 0, false)"
            ),
            {"id": rd_id, "proto": protocol_id, "name": "EC50"},
        )
        await uow.session.execute(
            sa.text(
                "INSERT INTO runs "
                "(id, workspace_id, protocol_id, run_date, operator, "
                "status, is_locked, version, notes) "
                "VALUES (:id, :ws, :proto, current_date, :user, 'draft', false, 1, null)"
            ),
            {"id": run_id, "ws": workspace_id, "proto": protocol_id, "user": _SEED_USER},
        )
        await uow.session.execute(
            sa.text(
                "INSERT INTO dose_response_curves "
                "(id, workspace_id, molecule_id, protocol_id, run_id, "
                "readout_definition_id, curve_type, fitted_value, hill_slope, "
                "top, bottom, r_squared, num_points) "
                "VALUES (:id, :ws, :mol, :proto, :run, :rd, "
                "'ic50', 5.0, 1.0, 100.0, 0.0, 0.9, 5)"
            ),
            {
                "id": curve_id,
                "ws": workspace_id,
                "mol": molecule_id,
                "proto": protocol_id,
                "run": run_id,
                "rd": rd_id,
            },
        )
        await uow.commit()

    return protocol_id


@pytest.mark.asyncio
class TestMoleculeTestCounts:
    async def test_empty_body_returns_empty(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/molecules/test-counts",
            json={"molecule_ids": []},
        )
        assert resp.status_code == 200
        assert resp.json()["counts"] == {}

    async def test_untested_molecule_returns_zero(
        self, client: AsyncClient, workspace_id: uuid.UUID
    ) -> None:
        mol_id = uuid.uuid4()
        resp = await client.post(
            "/api/v1/molecules/test-counts",
            json={"molecule_ids": [str(mol_id)]},
        )
        assert resp.status_code == 200
        assert resp.json()["counts"][str(mol_id)] == 0

    async def test_tested_molecule_returns_count(
        self, client: AsyncClient, workspace_id: uuid.UUID, uow: AsyncUnitOfWork
    ) -> None:
        mol_id = uuid.uuid4()
        # Seed two protocols for the same molecule
        await _seed_protocol_run_curve(uow, workspace_id, mol_id)
        await _seed_protocol_run_curve(uow, workspace_id, mol_id)

        resp = await client.post(
            "/api/v1/molecules/test-counts",
            json={"molecule_ids": [str(mol_id)]},
        )
        assert resp.status_code == 200
        assert resp.json()["counts"][str(mol_id)] == 2

    async def test_project_scoped_count(
        self, client: AsyncClient, workspace_id: uuid.UUID, uow: AsyncUnitOfWork
    ) -> None:
        mol_id = uuid.uuid4()
        project_id = uuid.uuid4()

        # Insert project row so FK from protocol_projects is satisfied
        async with uow:
            await uow.session.execute(
                sa.text(
                    "INSERT INTO projects "
                    "(id, workspace_id, name, version, created_by, visibility) "
                    "VALUES (:id, :ws, :name, 1, :user, 'workspace') ON CONFLICT DO NOTHING"
                ),
                {"id": project_id, "ws": workspace_id, "name": f"Proj-{str(project_id)[:8]}", "user": _SEED_USER},
            )
            await uow.commit()

        await _seed_protocol_run_curve(uow, workspace_id, mol_id, project_id=project_id)
        await _seed_protocol_run_curve(uow, workspace_id, mol_id)  # protocol NOT in project

        # Workspace-scoped count = 2
        resp_all = await client.post(
            "/api/v1/molecules/test-counts",
            json={"molecule_ids": [str(mol_id)]},
        )
        assert resp_all.status_code == 200
        assert resp_all.json()["counts"][str(mol_id)] == 2

        # Project-scoped count = 1 (only the protocol in the project)
        resp_proj = await client.post(
            "/api/v1/molecules/test-counts",
            json={"molecule_ids": [str(mol_id)], "project_id": str(project_id)},
        )
        assert resp_proj.status_code == 200
        assert resp_proj.json()["counts"][str(mol_id)] == 1
