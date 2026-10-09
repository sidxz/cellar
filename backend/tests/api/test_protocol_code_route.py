"""POST /protocols returns a minted code; the next create gets the next number."""

import re

from tests.api._protocols import protocol_body


async def test_create_mints_sequential_codes(client):
    a = (await client.post("/api/v1/protocols", json=await protocol_body(client))).json()
    b = (await client.post("/api/v1/protocols", json=await protocol_body(client))).json()
    assert re.fullmatch(r"PRT-\d{5}", a["code"])
    assert int(b["code"][4:]) == int(a["code"][4:]) + 1
