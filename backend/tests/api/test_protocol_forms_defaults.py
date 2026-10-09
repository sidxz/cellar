"""Add default forms: once per category form, idempotent."""


async def test_default_categories_bring_their_forms_and_reseeding_adds_nothing(client):
    r = await client.post("/api/v1/protocol-categories/defaults")
    assert r.status_code in (200, 201), r.text
    forms = (await client.get("/api/v1/protocol-forms")).json()
    enzyme = [f for f in forms if f["name"] in ("IC50 dose-response", "% inhibition single point")]
    assert enzyme and all(f["category_id"] for f in forms)
    again = await client.post("/api/v1/protocol-forms/defaults")
    assert again.status_code == 200, again.text
    assert again.json() == []  # only what it created
    assert len((await client.get("/api/v1/protocol-forms")).json()) == len(forms)


async def test_adding_default_forms_returns_the_ones_it_created(client):
    await client.post("/api/v1/protocol-categories/defaults")
    forms = (await client.get("/api/v1/protocol-forms")).json()
    mbc = next(f for f in forms if f["name"] == "MBC")
    assert (await client.delete(f"/api/v1/protocol-forms/{mbc['id']}")).status_code == 204
    r = await client.post("/api/v1/protocol-forms/defaults")
    assert r.status_code == 200, r.text
    assert [(f["name"], f["category_id"]) for f in r.json()] == [("MBC", mbc["category_id"])]
