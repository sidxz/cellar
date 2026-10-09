"""References through the API: create, POST/DELETE /protocols/{id}/references, mutability."""

from urllib.parse import quote

from tests.api._protocols import protocol_body

CHEMBL = {"kind": "chembl_assay", "value": "CHEMBL1054500"}
DOI = {"kind": "doi", "value": "https://doi.org/10.1021/jm901137j"}


async def _create(client, **fields) -> dict:
    r = await client.post("/api/v1/protocols", json=await protocol_body(client, "refs", **fields))
    assert r.status_code == 201, r.text
    return r.json()


def _refs_url(p: dict, key: str | None = None) -> str:
    base = f"/api/v1/protocols/{p['id']}/references"
    return base if key is None else f"{base}/{quote(key, safe='')}"


async def test_create_round_trips_normalized_references(client):
    p = await _create(client, references=[CHEMBL, DOI])
    expected = [CHEMBL, {"kind": "doi", "value": "10.1021/jm901137j"}]
    assert p["references"] == expected
    fetched = (await client.get(f"/api/v1/protocols/{p['id']}")).json()
    assert fetched["references"] == expected
    listed = (await client.get("/api/v1/protocols")).json()["items"]
    assert next(x for x in listed if x["id"] == p["id"])["references"] == expected


async def test_create_refuses_an_invalid_or_duplicate_reference(client):
    bad = await protocol_body(
        client, "refs", references=[{"kind": "url", "value": "javascript:alert(1)"}]
    )
    assert (await client.post("/api/v1/protocols", json=bad)).status_code == 422
    dup = await protocol_body(
        client, "refs", references=[DOI, {"kind": "doi", "value": "doi:10.1021/jm901137j"}]
    )
    assert (await client.post("/api/v1/protocols", json=dup)).status_code == 409


async def test_add_and_remove_by_key(client):
    p = await _create(client)
    assert p["references"] == []
    r = await client.post(_refs_url(p), json=DOI)
    assert r.status_code == 200, r.text
    assert r.json()["references"] == [{"kind": "doi", "value": "10.1021/jm901137j"}]
    assert (await client.post(_refs_url(p), json=DOI)).status_code == 409
    bad = await client.post(_refs_url(p), json={"kind": "url", "value": "data:text/html,x"})
    assert bad.status_code == 422

    # The key carries a slash (DOI): URL-encoded, it still addresses one reference.
    r = await client.delete(_refs_url(p, "doi:10.1021/jm901137j"))
    assert r.status_code == 200, r.text
    assert r.json()["references"] == []
    assert (await client.delete(_refs_url(p, "doi:10.1021/jm901137j"))).status_code == 404


async def test_active_takes_references_locked_refuses(client):
    p = await _create(client)
    assert (await client.post(f"/api/v1/protocols/{p['id']}/publish")).status_code == 200
    r = await client.post(_refs_url(p), json=CHEMBL)
    assert r.status_code == 200, r.text
    lock = await client.post(f"/api/v1/protocols/{p['id']}/lock", json={"reason": "review"})
    assert lock.status_code == 200
    assert (await client.post(_refs_url(p), json=DOI)).status_code == 409
    assert (await client.delete(_refs_url(p, "chembl_assay:CHEMBL1054500"))).status_code == 409


async def test_viewer_cannot_change_references(client, viewer_client):
    p = await _create(client)
    assert (await viewer_client.post(_refs_url(p), json=CHEMBL)).status_code == 403
