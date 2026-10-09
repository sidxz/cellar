"""A condition's fixed value through the API: create, add, edit a draft, correct a published one,
and runs that give no value take it."""

from tests.api._protocols import protocol_body

TIME = {"name": "Incubation time", "data_type": "numeric", "unit": "h", "fixed_value": "72"}
HYPOXIA = {
    "name": "Hypoxia",
    "data_type": "pick_list",
    "pick_list_values": ["yes", "no"],
    "fixed_value": "yes",
}


def _by_name(protocol: dict) -> dict:
    return {cd["name"]: cd for cd in protocol["condition_definitions"]}


async def _create(client, **fields) -> dict:
    r = await client.post("/api/v1/protocols", json=await protocol_body(client, "fixed", **fields))
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_round_trips_the_fixed_value(client):
    p = await _create(
        client, condition_definitions=[TIME, HYPOXIA, {"name": "Medium", "data_type": "text"}]
    )
    got = {n: cd["fixed_value"] for n, cd in _by_name(p).items()}
    assert got == {"Incubation time": "72", "Hypoxia": "yes", "Medium": None}
    fetched = (await client.get(f"/api/v1/protocols/{p['id']}")).json()
    assert _by_name(fetched)["Incubation time"]["fixed_value"] == "72"


async def test_create_refuses_a_value_that_does_not_fit_the_type(client):
    body = await protocol_body(
        client, "fixed", condition_definitions=[TIME | {"fixed_value": "3 days"}]
    )
    assert (await client.post("/api/v1/protocols", json=body)).status_code == 422


async def test_add_and_edit_on_a_draft(client):
    p = await _create(client)
    r = await client.post(f"/api/v1/protocols/{p['id']}/condition-definitions", json=TIME)
    assert r.status_code == 201, r.text
    cd = _by_name(r.json())["Incubation time"]
    assert cd["fixed_value"] == "72"
    r = await client.put(
        f"/api/v1/protocols/{p['id']}/condition-definitions/{cd['id']}",
        json={"fixed_value": " 48 "},
    )
    assert r.status_code == 200, r.text
    assert _by_name(r.json())["Incubation time"]["fixed_value"] == "48"
    r = await client.put(
        f"/api/v1/protocols/{p['id']}/condition-definitions/{cd['id']}",
        json={"fixed_value": "two"},
    )
    assert r.status_code == 422


async def test_a_published_protocol_changes_it_only_by_correction(client):
    p = await _create(client, condition_definitions=[TIME])
    cd_id = _by_name(p)["Incubation time"]["id"]
    assert (await client.post(f"/api/v1/protocols/{p['id']}/publish")).status_code == 200
    r = await client.put(
        f"/api/v1/protocols/{p['id']}/condition-definitions/{cd_id}", json={"fixed_value": "48"}
    )
    assert r.status_code == 409
    r = await client.post(
        f"/api/v1/protocols/{p['id']}/correct",
        json={"reason": "It was always 48 h", "condition_fixed_values": {cd_id: "48"}},
    )
    assert r.status_code == 200, r.text
    assert _by_name(r.json())["Incubation time"]["fixed_value"] == "48"
    r = await client.post(
        f"/api/v1/protocols/{p['id']}/correct",
        json={"reason": "Not fixed after all", "condition_fixed_values": {cd_id: None}},
    )
    assert _by_name(r.json())["Incubation time"]["fixed_value"] is None


async def test_a_published_protocol_refuses_adding_a_fixed_condition(client):
    p = await _create(client)
    assert (await client.post(f"/api/v1/protocols/{p['id']}/publish")).status_code == 200
    url = f"/api/v1/protocols/{p['id']}/condition-definitions"
    r = await client.post(url, json=TIME)
    assert r.status_code == 409 and "Correct details" in r.text
    r = await client.post(url, json=TIME | {"fixed_value": None})
    assert r.status_code == 201, r.text
    assert _by_name(r.json())["Incubation time"]["fixed_value"] is None


async def test_a_locked_protocol_refuses_the_correction(client):
    p = await _create(client, condition_definitions=[TIME])
    cd_id = _by_name(p)["Incubation time"]["id"]
    assert (await client.post(f"/api/v1/protocols/{p['id']}/publish")).status_code == 200
    assert (
        await client.post(f"/api/v1/protocols/{p['id']}/lock", json={"reason": "review"})
    ).status_code == 200
    r = await client.post(
        f"/api/v1/protocols/{p['id']}/correct",
        json={"reason": "x", "condition_fixed_values": {cd_id: "48"}},
    )
    assert r.status_code == 409


async def test_a_run_without_the_condition_stores_the_fixed_value(client):
    p = await _create(client, condition_definitions=[TIME, HYPOXIA])
    assert (await client.post(f"/api/v1/protocols/{p['id']}/publish")).status_code == 200
    r = await client.post(
        "/api/v1/runs",
        json={"protocol_id": p["id"], "run_date": "2026-10-08", "conditions": {"Hypoxia": "no"}},
    )
    assert r.status_code == 201, r.text
    assert r.json()["conditions"] == {"Hypoxia": "no", "Incubation time": "72 h"}
