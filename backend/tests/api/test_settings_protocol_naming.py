"""PATCH /settings protocol_naming: merged, validated as 422."""


async def test_patch_protocol_naming_round_trips(client):
    r = await client.patch(
        "/api/v1/settings", json={"protocol_naming": {"code_prefix": "ASY-", "code_width": 4}}
    )
    assert r.status_code == 200, r.text
    assert r.json()["protocol_naming"] == {"code_prefix": "ASY-", "code_width": 4}


async def test_patch_protocol_naming_bad_prefix_is_422(client):
    r = await client.patch("/api/v1/settings", json={"protocol_naming": {"code_prefix": "bad"}})
    assert r.status_code == 422, r.text
