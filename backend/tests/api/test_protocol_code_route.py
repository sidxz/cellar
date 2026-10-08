"""POST /protocols returns a minted code; the next create gets the next number."""

import re

BODY = {"name": "x", "protocol_type": "biochemical", "readout_definitions": [{"name": "Signal", "data_type": "numeric"}]}


async def test_create_mints_sequential_codes(client):
    a = (await client.post("/api/v1/protocols", json=BODY | {"name": "A"})).json()
    b = (await client.post("/api/v1/protocols", json=BODY | {"name": "B"})).json()
    assert re.fullmatch(r"PRT-\d{5}", a["code"])
    assert int(b["code"][4:]) == int(a["code"][4:]) + 1
