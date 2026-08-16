"""GET /api/v1/orgs returns the Duar org directory (id/slug/name only)."""

from __future__ import annotations

from tests.api.conftest import ORG_ID


async def test_list_orgs(client):
    resp = await client.get("/api/v1/orgs")
    assert resp.status_code == 200
    assert resp.json() == [{"id": str(ORG_ID), "slug": "abbvie", "name": "AbbVie"}]
