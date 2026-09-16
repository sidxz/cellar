"""API tests for GET /api/v1/plates/insights."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.api.conftest import AUTH_ORG_ID, OTHER_ORG_ID, _create_test_app
from tests.fakes.fake_auth import FakeAuth

_INSIGHTS_FIELDS = {
    "org_id",
    "total_plates",
    "open_loans",
    "overdue_count",
    "by_status",
    "by_type",
    "by_location",
    "group_sizes",
    "loan_activity_weekly",
}


async def _mk_plate(client: AsyncClient, barcode: str, **overrides) -> dict:
    body = {
        "barcode": barcode,
        "plate_label": barcode,
        "format": "96",
        "plate_type": "assay",
        **overrides,
    }
    resp = await client.post("/api/v1/plates", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _mk_loan(client: AsyncClient, **body) -> dict:
    resp = await client.post("/api/v1/plate-loans", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


@asynccontextmanager
async def _client_as(
    database_url: str, workspace_id: uuid.UUID, **auth_kwargs
) -> AsyncIterator[AsyncClient]:
    """An ad-hoc client for an identity distinct from the standard fixtures
    (mirrors ``tests/api/test_plate_loans.py::_client_as``) — needed here for
    the orgless-caller case, which no standard fixture produces."""
    auth_kwargs.setdefault("role", "editor")
    auth = FakeAuth(workspace_id=workspace_id, **auth_kwargs)
    app = _create_test_app(database_url, auth)
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await app.state.container[AsyncEngine].dispose()


class TestShape:
    async def test_all_fields_present_org_defaults_to_caller(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        await _mk_loan(client, plate_ids=[plate["id"]])

        resp = await client.get("/api/v1/plates/insights")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body) == _INSIGHTS_FIELDS
        assert body["org_id"] == str(AUTH_ORG_ID)
        assert body["total_plates"] == 1
        assert body["open_loans"] == 1
        assert len(body["loan_activity_weekly"]) == 12


class TestOrgScoping:
    async def test_explicit_org_id_scopes_counts(self, client: AsyncClient) -> None:
        await _mk_plate(client, f"PL-A-{uuid.uuid4().hex[:8]}")
        await _mk_plate(client, f"PL-B-{uuid.uuid4().hex[:8]}", owner_org_id=str(OTHER_ORG_ID))

        mine = (await client.get("/api/v1/plates/insights")).json()
        theirs = (await client.get(f"/api/v1/plates/insights?org_id={OTHER_ORG_ID}")).json()

        assert mine["org_id"] == str(AUTH_ORG_ID)
        assert mine["total_plates"] == 1
        assert theirs["org_id"] == str(OTHER_ORG_ID)
        assert theirs["total_plates"] == 1


class TestPrivateOrg:
    async def test_foreign_org_insights_forbidden_for_editor_ok_for_admin_and_member(
        self,
        client: AsyncClient,
        editor_client_own_org: AsyncClient,
        editor_client_other_org: AsyncClient,
    ) -> None:
        await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}", owner_org_id=str(OTHER_ORG_ID))
        # Editor of another org -> 403
        resp = await editor_client_own_org.get(f"/api/v1/plates/insights?org_id={OTHER_ORG_ID}")
        assert resp.status_code == 403
        # Workspace admin -> bypass
        resp = await client.get(f"/api/v1/plates/insights?org_id={OTHER_ORG_ID}")
        assert resp.status_code == 200
        # Member still sees it
        resp = await editor_client_other_org.get(f"/api/v1/plates/insights?org_id={OTHER_ORG_ID}")
        assert resp.status_code == 200


class TestOrglessCaller:
    async def test_orgless_caller_without_org_id_param_422(
        self, database_url: str, _run_migrations: None, workspace_id: uuid.UUID
    ) -> None:
        async with _client_as(database_url, workspace_id, org_id=None) as anon:
            resp = await anon.get("/api/v1/plates/insights")
            assert resp.status_code == 422
            assert "org_id" in resp.json()["message"]


class TestRouteOrder:
    async def test_insights_does_not_shadow_plate_by_id(self, client: AsyncClient) -> None:
        """Route-order canary: /insights must be registered before /{plate_id}
        or FastAPI would try (and fail) to parse "insights" as a plate UUID."""
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")

        resp = await client.get("/api/v1/plates/insights")
        assert resp.status_code == 200, resp.text

        resp = await client.get(f"/api/v1/plates/{plate['id']}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == plate["id"]
