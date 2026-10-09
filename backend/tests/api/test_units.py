"""The unit picker's suggestions."""


async def test_lists_common_units_grouped(client):
    r = await client.get("/api/v1/units")
    assert r.status_code == 200, r.text
    body = r.json()
    assert {"unit": "µM", "group": "Concentration"} in body
    assert {"unit": "mg/kg", "group": "Dose"} in body
