"""A protocol records its creator's Duar org and an owner org the creator or an admin can change."""

from __future__ import annotations

from tests.api._protocols import protocol_body
from tests.api.conftest import AUTH_ORG_ID, OTHER_ORG_ID


async def _create(client) -> dict:
    r = await client.post("/api/v1/protocols", json=await protocol_body(client, "owner"))
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_stamps_creator_org_and_owner(client):
    p = await _create(client)
    assert (p["created_by_org_id"], p["owner_org_id"]) == (str(AUTH_ORG_ID),) * 2


async def test_put_owner_on_locked_protocol_succeeds(client):
    p = await _create(client)
    assert (
        await client.post(f"/api/v1/protocols/{p['id']}/lock", json={"reason": "review"})
    ).status_code == 200
    r = await client.put(
        f"/api/v1/protocols/{p['id']}/owner", json={"owner_org_id": str(OTHER_ORG_ID)}
    )
    assert r.status_code == 200, r.text
    assert r.json()["owner_org_id"] == str(OTHER_ORG_ID)


async def test_put_owner_by_non_creator_editor_is_403(client, other_editor_client):
    p = await _create(client)
    r = await other_editor_client.put(
        f"/api/v1/protocols/{p['id']}/owner", json={"owner_org_id": str(OTHER_ORG_ID)}
    )
    assert r.status_code == 403
