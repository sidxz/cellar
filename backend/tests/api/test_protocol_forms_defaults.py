"""Add default forms: once per category form, idempotent."""


async def test_default_categories_bring_their_forms_and_reseeding_adds_nothing(client):
    r = await client.post("/api/v1/protocol-categories/defaults")
    assert r.status_code in (200, 201), r.text
    forms = (await client.get("/api/v1/protocol-forms")).json()
    enzyme = [f for f in forms if f["name"] in ("IC50 dose-response", "% inhibition single point")]
    assert enzyme and all(f["category_id"] for f in forms)
    again = await client.post("/api/v1/protocol-forms/defaults")
    assert again.status_code == 200, again.text
    assert len((await client.get("/api/v1/protocol-forms")).json()) == len(forms)
