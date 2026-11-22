"""GET /api/v1/orgs returns the Duar org directory (id/slug/name/enabled)."""

from __future__ import annotations

from tests.api.conftest import AUTH_ORG_ID, ORG_ID, OTHER_ORG_ID


async def test_list_orgs(client):
    resp = await client.get("/api/v1/orgs")
    assert resp.status_code == 200
    assert resp.json() == [
        {"id": str(ORG_ID), "slug": "abbvie", "name": "AbbVie", "enabled": True},
        {"id": str(AUTH_ORG_ID), "slug": "tamu", "name": "TAMU", "enabled": True},
        {"id": str(OTHER_ORG_ID), "slug": "partner", "name": "Partner", "enabled": True},
    ]


async def test_orgs_include_disabled_lists_disabled_with_flag(api_app, client):
    import uuid

    from cellar.infrastructure.duar.org_directory import OrgSummary
    from cellar.interface.dependencies import get_org_directory_all

    disabled = uuid.uuid4()

    class _Stub:
        async def list_orgs(self):
            return [
                OrgSummary(id=AUTH_ORG_ID, slug="tamu", name="TAMU", is_public=False),
                OrgSummary(id=disabled, slug="gone", name="Gone", is_public=False, enabled=False),
            ]

    api_app.dependency_overrides[get_org_directory_all] = lambda: _Stub()

    every = (await client.get("/api/v1/orgs", params={"include_disabled": "true"})).json()
    assert {o["id"]: o["enabled"] for o in every} == {str(AUTH_ORG_ID): True, str(disabled): False}

    default = (await client.get("/api/v1/orgs")).json()
    assert [o["id"] for o in default] == [str(AUTH_ORG_ID)]
