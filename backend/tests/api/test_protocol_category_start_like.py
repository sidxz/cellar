"""A new category can start its protocols like an existing one: its forms are copied."""


async def test_new_category_copies_the_sources_forms(client):
    await client.post("/api/v1/protocol-categories/defaults")
    cats = (await client.get("/api/v1/protocol-categories")).json()
    growth = next(c for c in cats if c["label"] == "Growth inhibition")
    r = await client.post(
        "/api/v1/protocol-categories",
        json={"label": "Gametocytocidal activity", "start_like_category_id": growth["id"]},
    )
    assert r.status_code == 201, r.text
    new_id = r.json()["id"]
    forms = (await client.get("/api/v1/protocol-forms")).json()
    copied = sorted(f["name"] for f in forms if f["category_id"] == new_id)
    source = sorted(f["name"] for f in forms if f["category_id"] == growth["id"])
    assert copied == source and copied


async def test_unknown_source_category_is_404(client):
    r = await client.post(
        "/api/v1/protocol-categories",
        json={"label": "X", "start_like_category_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert r.status_code == 404, r.text
