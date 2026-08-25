"""GET /api/v1/orgs returns the Duar org directory (id/slug/name only)."""

from __future__ import annotations

from tests.api.conftest import AUTH_ORG_ID, ORG_ID, OTHER_ORG_ID


async def test_list_orgs(client):
    resp = await client.get("/api/v1/orgs")
    assert resp.status_code == 200
    assert resp.json() == [
        {"id": str(ORG_ID), "slug": "abbvie", "name": "AbbVie"},
        {"id": str(AUTH_ORG_ID), "slug": "tamu", "name": "TAMU"},
        {"id": str(OTHER_ORG_ID), "slug": "partner", "name": "Partner"},
    ]
