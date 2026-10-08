"""Admin: re-derive every protocol name (dry run, then apply) and the name flags list."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.api._protocols import protocol_body


async def _sql(api_app, sql, **params):
    factory = api_app.state.container[async_sessionmaker]
    async with factory() as session, session.begin():
        await session.execute(text(sql), params)


async def test_dry_run_then_apply(client, api_app):
    broken = (await client.post("/api/v1/protocols", json=await protocol_body(client))).json()
    no_category = (await client.post("/api/v1/protocols", json=await protocol_body(client))).json()
    await _sql(
        api_app,
        "UPDATE protocols SET name = 'Old hand-typed name', name_base = 'Old hand-typed name' "
        "WHERE id = :id",
        id=broken["id"],
    )
    await _sql(api_app, "UPDATE protocols SET category = NULL WHERE id = :id", id=no_category["id"])

    dry = (
        await client.post("/api/v1/protocol-names/rederive", json={"dry_run": True, "reason": "check"})
    ).json()
    change = next(c for c in dry["changes"] if c["protocol_id"] == broken["id"])
    assert (change["before"], change["after"]) == ("Old hand-typed name", broken["name"])
    assert dry["report"] is None
    unchanged = (await client.get(f"/api/v1/protocols/{broken['id']}")).json()
    assert unchanged["name"] == "Old hand-typed name"

    applied = (
        await client.post(
            "/api/v1/protocol-names/rederive",
            json={"dry_run": False, "reason": "Names generated from fields"},
        )
    ).json()
    assert applied["report"]["renamed"] == 1
    fixed = (await client.get(f"/api/v1/protocols/{broken['id']}")).json()
    assert fixed["name"] == broken["name"]
    assert "Old hand-typed name" in [a["label"] for a in fixed["aliases"]]

    flags = (await client.get("/api/v1/protocol-names/flags")).json()
    assert [(f["code"], f["flag"]) for f in flags] == [(no_category["code"], "needs_facts")]


async def test_editors_cannot_rederive(editor_client):
    r = await editor_client.post(
        "/api/v1/protocol-names/rederive", json={"dry_run": True, "reason": "check"}
    )
    assert r.status_code == 403
