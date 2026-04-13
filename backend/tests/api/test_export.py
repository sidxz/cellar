"""API tests for SDF export endpoint."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


@pytest.fixture
async def org_id(client: AsyncClient) -> str:
    """Create an organization so molecules can reference it."""
    resp = await client.post(
        "/api/v1/organizations",
        json={
            "name": "ExportTestOrg",
            "org_type": "internal",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


class TestExportSDF:
    async def test_export_empty_list_returns_empty(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/molecules/export/sdf",
            json={"molecule_ids": []},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "chemical/x-sdf"
        assert resp.text == ""

    async def test_export_nonexistent_ids_returns_empty(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/molecules/export/sdf",
            json={"molecule_ids": [str(uuid.uuid4())]},
        )
        assert resp.status_code == 200
        assert resp.text == ""

    async def test_export_registered_molecule(
        self, client: AsyncClient, org_id: str
    ) -> None:
        """Register a molecule, then export it as SDF."""
        reg = await client.post(
            "/api/v1/molecules",
            json={
                "name": "Aspirin",
                "smiles": "CC(=O)Oc1ccccc1C(=O)O",
                "originating_org_id": org_id,
            },
        )
        assert reg.status_code == 201
        mol_id = reg.json()["molecule"]["id"]

        resp = await client.post(
            "/api/v1/molecules/export/sdf",
            json={"molecule_ids": [mol_id]},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "chemical/x-sdf"
        body = resp.text
        assert "$$$$" in body
        assert "> <Name>" in body
        assert "Aspirin" in body
        assert "> <Registration_Number>" in body

    async def test_export_max_limit_exceeded(self, client: AsyncClient) -> None:
        ids = [str(uuid.uuid4()) for _ in range(10001)]
        resp = await client.post(
            "/api/v1/molecules/export/sdf",
            json={"molecule_ids": ids},
        )
        assert resp.status_code == 422
