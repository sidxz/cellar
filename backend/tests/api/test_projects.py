"""API tests for project endpoints."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

# Force screening_assay models so protocol_projects / runs join targets resolve.
import cellar.infrastructure.persistence.sqlalchemy.screening_assay.models  # noqa: F401


class TestListProjects:
    async def test_empty_list(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/projects")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_list_after_create(self, client: AsyncClient) -> None:
        await client.post(
            "/api/v1/projects",
            json={"name": "Kinase Screening"},
        )
        resp = await client.get("/api/v1/projects")
        assert resp.status_code == 200
        data = resp.json()["items"]
        assert len(data) == 1
        assert data[0]["name"] == "Kinase Screening"


class TestCreateProject:
    async def test_create_success(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/projects",
            json={"name": "GPCR Discovery", "description": "GPCR target family"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "GPCR Discovery"
        assert data["description"] == "GPCR target family"
        assert data["status"] == "active"
        assert data["version"] == 1
        assert "id" in data
        assert "workspace_id" in data
        assert "created_by" in data

    async def test_create_minimal(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/projects",
            json={"name": "Minimal Project"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Minimal Project"
        assert data["description"] is None

    async def test_create_duplicate_name_409(self, client: AsyncClient) -> None:
        await client.post(
            "/api/v1/projects",
            json={"name": "Unique Project"},
        )
        resp = await client.post(
            "/api/v1/projects",
            json={"name": "Unique Project"},
        )
        assert resp.status_code == 409
        assert "already exists" in resp.json()["message"]

    async def test_create_empty_name_422(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/projects",
            json={"name": ""},
        )
        assert resp.status_code == 422


class TestGetProject:
    async def test_get_success(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/projects",
            json={"name": "GetTest Project"},
        )
        project_id = create.json()["id"]
        resp = await client.get(f"/api/v1/projects/{project_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "GetTest Project"

    async def test_get_not_found_404(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/projects/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestUpdateProject:
    async def test_update_name(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/projects",
            json={"name": "Old Name", "description": "original"},
        )
        project_id = create.json()["id"]
        resp = await client.patch(
            f"/api/v1/projects/{project_id}",
            json={"name": "New Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"
        assert resp.json()["description"] == "original"  # unchanged
        assert resp.json()["version"] == 2

    async def test_update_not_found_404(self, client: AsyncClient) -> None:
        resp = await client.patch(
            f"/api/v1/projects/{uuid.uuid4()}",
            json={"name": "Whatever"},
        )
        assert resp.status_code == 404


class TestArchiveProject:
    async def test_archive_success(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/projects",
            json={"name": "To Archive"},
        )
        project_id = create.json()["id"]
        resp = await client.post(f"/api/v1/projects/{project_id}/archive")
        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"

    async def test_archive_already_archived_422(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/projects",
            json={"name": "Already Archived"},
        )
        project_id = create.json()["id"]
        await client.post(f"/api/v1/projects/{project_id}/archive")
        resp = await client.post(f"/api/v1/projects/{project_id}/archive")
        assert resp.status_code == 422

    async def test_update_after_archive_422(self, client: AsyncClient) -> None:
        create = await client.post(
            "/api/v1/projects",
            json={"name": "Frozen Project"},
        )
        project_id = create.json()["id"]
        await client.post(f"/api/v1/projects/{project_id}/archive")
        resp = await client.patch(
            f"/api/v1/projects/{project_id}",
            json={"name": "Should Fail"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Project scope stats (chip counts)
# ---------------------------------------------------------------------------


async def _session(api_app: FastAPI) -> AsyncSession:
    engine: AsyncEngine = api_app.state.container[AsyncEngine]
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return factory()


_USER_ID = uuid.UUID("dddddddd-0000-0000-0000-000000000099")


async def _seed_protocol_with_run(
    api_app: FastAPI, project_id: uuid.UUID, workspace_id: uuid.UUID
) -> uuid.UUID:
    """Insert a protocol linked to project_id, plus one run on it. Returns protocol id."""
    protocol_id = uuid.uuid4()
    run_id = uuid.uuid4()
    async with await _session(api_app) as session:
        await session.execute(
            sa.text(
                "INSERT INTO protocols "
                "(id, workspace_id, name, protocol_type, status, "
                "is_locked, dose_unit, pos_control_signal, version, protocol_version, created_by) "
                "VALUES (:id, :ws, :name, 'biochemical', 'active', "
                "false, 'uM', 'high', 1, 1, :user)"
            ),
            {
                "id": protocol_id,
                "ws": workspace_id,
                "name": f"stats-proto-{protocol_id.hex[:6]}",
                "user": _USER_ID,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO protocol_projects (protocol_id, project_id) "
                "VALUES (:p, :prj)"
            ),
            {"p": protocol_id, "prj": project_id},
        )
        await session.execute(
            sa.text(
                "INSERT INTO runs "
                "(id, workspace_id, protocol_id, run_date, operator, status, "
                "is_locked, version) "
                "VALUES (:id, :ws, :p, :run_date, :op, 'active', false, 1)"
            ),
            {
                "id": run_id,
                "ws": workspace_id,
                "p": protocol_id,
                "run_date": date(2025, 1, 1),
                "op": _USER_ID,
            },
        )
        await session.commit()
    return protocol_id


async def _seed_molecule_in_project(
    api_app: FastAPI, project_id: uuid.UUID, client: AsyncClient
) -> uuid.UUID:
    """Create a molecule via the API and link it to the project."""
    org = await client.post(
        "/api/v1/organizations",
        json={"name": f"StatsOrg-{uuid.uuid4().hex[:6]}", "org_type": "internal"},
    )
    assert org.status_code == 201
    org_id = org.json()["id"]
    mol = await client.post(
        "/api/v1/molecules",
        json={"name": "StatMol", "smiles": "CC", "originating_org_id": org_id},
    )
    assert mol.status_code == 201, mol.text
    molecule_id = uuid.UUID(mol.json()["molecule"]["id"])
    link = await client.post(f"/api/v1/projects/{project_id}/molecules/{molecule_id}")
    assert link.status_code == 204, link.text
    return molecule_id


class TestProjectScopeStats:
    async def test_empty_query_returns_empty(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/projects/stats")
        assert resp.status_code == 200
        assert resp.json() == {}

    async def test_unknown_id_omitted(self, client: AsyncClient) -> None:
        resp = await client.get(
            "/api/v1/projects/stats", params={"project_ids": str(uuid.uuid4())}
        )
        assert resp.status_code == 200
        assert resp.json() == {}

    async def test_project_with_no_links_returns_zeros(
        self, client: AsyncClient
    ) -> None:
        create = await client.post(
            "/api/v1/projects", json={"name": "Empty Stats Project"}
        )
        project_id = create.json()["id"]
        resp = await client.get(
            "/api/v1/projects/stats", params={"project_ids": project_id}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert project_id in body
        assert body[project_id] == {
            "molecule_count": 0,
            "protocol_count": 0,
            "run_count": 0,
        }

    async def test_counts_real_links(
        self,
        client: AsyncClient,
        api_app: FastAPI,
        workspace_id: uuid.UUID,
    ) -> None:
        create = await client.post(
            "/api/v1/projects", json={"name": "Linked Stats Project"}
        )
        project_id = uuid.UUID(create.json()["id"])

        await _seed_molecule_in_project(api_app, project_id, client)
        await _seed_protocol_with_run(api_app, project_id, workspace_id)

        resp = await client.get(
            "/api/v1/projects/stats", params={"project_ids": str(project_id)}
        )
        assert resp.status_code == 200
        body = resp.json()[str(project_id)]
        assert body["molecule_count"] == 1
        assert body["protocol_count"] == 1
        assert body["run_count"] == 1
