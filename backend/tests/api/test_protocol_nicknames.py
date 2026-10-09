"""Nicknames: POST/DELETE /protocols/{id}/nicknames."""

from tests.api._protocols import protocol_body


async def _protocol(client):
    r = await client.post("/api/v1/protocols", json=await protocol_body(client))
    assert r.status_code == 201, r.text
    return r.json()


async def test_add_and_remove_nickname(client):
    p = await _protocol(client)
    r = await client.post(f"/api/v1/protocols/{p['id']}/nicknames", json={"label": "MABA"})
    assert r.status_code == 200, r.text
    alias = r.json()["aliases"][0]
    assert (alias["label"], alias["kind"]) == ("MABA", "nickname")

    dup = await client.post(f"/api/v1/protocols/{p['id']}/nicknames", json={"label": "maba"})
    assert dup.status_code == 409

    r = await client.delete(f"/api/v1/protocols/{p['id']}/nicknames", params={"label": "MABA"})
    assert r.status_code == 200 and r.json()["aliases"] == []


async def test_viewer_cannot_add_nicknames(client, viewer_client):
    p = await _protocol(client)
    r = await viewer_client.post(f"/api/v1/protocols/{p['id']}/nicknames", json={"label": "MABA"})
    assert r.status_code == 403
