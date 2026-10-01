"""API tests for project endpoints."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from cellar.application.chemical_registration.merge_side_effect_registry import (
    MergeSideEffectRegistry,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

# Force screening_assay models so protocol_projects / runs join targets resolve.
import cellar.infrastructure.persistence.sqlalchemy.screening_assay.models  # noqa: F401
from tests.api.conftest import _create_test_app
from tests.fakes.fake_auth import FakeAuth


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
        stats = body[project_id]
        # No linked scope entities yet.
        assert stats["molecule_count"] == 0
        assert stats["protocol_count"] == 0
        assert stats["run_count"] == 0
        assert stats["campaign_count"] == 0
        # Creator is auto-added as a member on project creation.
        assert stats["member_count"] == 1
        assert isinstance(stats["member_ids"], list)
        assert len(stats["member_ids"]) == 1

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

    async def test_stats_response_includes_new_fields(
        self, client: AsyncClient
    ) -> None:
        create = await client.post("/api/v1/projects", json={"name": "Stats v2"})
        pid = create.json()["id"]
        resp = await client.get(
            "/api/v1/projects/stats", params={"project_ids": pid}
        )
        assert resp.status_code == 200
        body = resp.json()[pid]
        assert body["campaign_count"] == 0
        assert "last_activity_at" in body
        assert "member_count" in body
        assert isinstance(body["member_ids"], list)


async def _org(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/organizations",
        json={"name": f"BulkProjOrg-{uuid.uuid4().hex[:6]}", "org_type": "internal"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _mol(client: AsyncClient, org_id: str, name: str, smiles: str) -> dict:
    resp = await client.post(
        "/api/v1/molecules",
        json={"name": name, "smiles": smiles, "originating_org_id": org_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["molecule"]


@asynccontextmanager
async def _client_as(
    database_url: str, workspace_id: uuid.UUID, **auth_kwargs
) -> AsyncIterator[AsyncClient]:
    app = _create_test_app(database_url, FakeAuth(workspace_id=workspace_id, **auth_kwargs))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:  # type: ignore[arg-type]
        yield ac
    await app.state.container[AsyncEngine].dispose()


class TestBulkAddMoleculesToProject:
    async def test_mixed_references_resolve_and_report(self, client: AsyncClient) -> None:
        org = await _org(client)
        a = await _mol(client, org, "BulkA", "CCCCCCCCCCO")
        b = await _mol(client, org, "BulkB", "CCCCCCCCCCCO")
        proj = (await client.post("/api/v1/projects", json={"name": "Bulk P"})).json()["id"]

        resp = await client.post(
            f"/api/v1/projects/{proj}/molecules",
            json={
                "references": [
                    {"value": a["registration_number"], "ref_type": "registration_number"},
                    {"value": b["id"], "ref_type": "uuid"},
                    {"value": "NO-SUCH-CMPD", "ref_type": "registration_number"},
                ]
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["added_count"] == 2
        assert body["already_present"] == 0
        assert [u["value"] for u in body["unresolved"]] == ["NO-SUCH-CMPD"]

        stats = await client.get("/api/v1/projects/stats", params={"project_ids": [proj]})
        assert stats.json()[proj]["molecule_count"] == 2

    async def test_repeats_count_as_already_present(self, client: AsyncClient) -> None:
        org = await _org(client)
        a = await _mol(client, org, "RepeatA", "CCCCCCCCCCCCO")
        proj = (await client.post("/api/v1/projects", json={"name": "Repeat P"})).json()["id"]
        ref = {"references": [{"value": a["id"], "ref_type": "uuid"}]}

        first = (await client.post(f"/api/v1/projects/{proj}/molecules", json=ref)).json()
        assert first["added_count"] == 1
        again = (await client.post(f"/api/v1/projects/{proj}/molecules", json=ref)).json()
        assert again["added_count"] == 0
        assert again["already_present"] == 1

    async def test_unknown_project_404(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"/api/v1/projects/{uuid.uuid4()}/molecules", json={"references": []}
        )
        assert resp.status_code == 404
        assert resp.json()["error"] == "NotFoundError"

    async def test_archived_project_422(self, client: AsyncClient) -> None:
        proj = (await client.post("/api/v1/projects", json={"name": "Old P"})).json()["id"]
        assert (await client.post(f"/api/v1/projects/{proj}/archive")).status_code == 200
        resp = await client.post(f"/api/v1/projects/{proj}/molecules", json={"references": []})
        assert resp.status_code == 422

    async def test_non_member_editor_403(
        self, client: AsyncClient, database_url: str, workspace_id: uuid.UUID
    ) -> None:
        proj = (await client.post("/api/v1/projects", json={"name": "Private P"})).json()["id"]
        async with _client_as(
            database_url, workspace_id, role="editor", user_id=uuid.uuid4()
        ) as stranger:
            resp = await stranger.post(
                f"/api/v1/projects/{proj}/molecules", json={"references": []}
            )
        assert resp.status_code == 403

    async def test_single_add_route_keeps_its_contract(self, client: AsyncClient) -> None:
        org = await _org(client)
        a = await _mol(client, org, "SingleA", "CCCCCCCCCCCCCO")
        proj = (await client.post("/api/v1/projects", json={"name": "Single P"})).json()["id"]

        added = await client.post(f"/api/v1/projects/{proj}/molecules/{a['id']}")
        assert added.status_code == 204
        missing = await client.post(f"/api/v1/projects/{proj}/molecules/{uuid.uuid4()}")
        assert missing.status_code == 404


async def test_molecule_merge_carries_project_links(
    database_url: str, _run_migrations: None, workspace_id: uuid.UUID
) -> None:
    """The app's merge registry moves the merged-away compound's project links."""
    app = _create_test_app(database_url, FakeAuth(role="admin", workspace_id=workspace_id))
    container = app.state.container
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:  # type: ignore[arg-type]
        org = await _org(c)
        src = await _mol(c, org, "MergeSrc", "CCCCCCCCCCCCCCCO")
        tgt = await _mol(c, org, "MergeTgt", "CCCCCCCCCCCCCCCCO")
        proj = (await c.post("/api/v1/projects", json={"name": "Merge P"})).json()["id"]
        assert (await c.post(f"/api/v1/projects/{proj}/molecules/{src['id']}")).status_code == 204

        uow = AsyncUnitOfWork(container[async_sessionmaker])
        async with uow:
            await container[MergeSideEffectRegistry].execute_all(
                uow, uuid.UUID(src["id"]), uuid.UUID(tgt["id"])
            )
            await uow.commit()

        linked = await c.get(f"/api/v1/molecules/{tgt['id']}/projects")
        assert proj in set(linked.json())
    await container[AsyncEngine].dispose()
