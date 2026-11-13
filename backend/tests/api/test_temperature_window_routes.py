"""API tests: adding a temperature window's Tm and ΔTm readouts to a protocol."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.api.test_instrument_import_routes import _seed
from tests.fakes.fake_auth import FakeAuth


async def _protocol_id(
    session_factory: async_sessionmaker[AsyncSession], ws: uuid.UUID
) -> uuid.UUID:
    s = await _seed(session_factory, ws)
    async with session_factory() as session:
        return (
            await session.execute(
                sa.text("SELECT protocol_id FROM runs WHERE id = :id"), {"id": s.run_id}
            )
        ).scalar_one()


def _window(**over: object) -> dict[str, object]:
    body: dict[str, object] = {
        "window": "Main",
        "channel_key": "ratio",
        "low": 50.0,
        "high": 85.0,
        "measures": ["tm", "delta_tm"],
    }
    return body | over


async def test_add_window_route_adds_two_readouts_with_melt_config(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    protocol_id = await _protocol_id(session_factory, fake_auth.workspace_id)
    resp = await client.post(
        f"/api/v1/protocols/{protocol_id}/temperature-windows", json=_window()
    )
    assert resp.status_code == 201, resp.text

    got = (await client.get(f"/api/v1/protocols/{protocol_id}")).json()
    by_name = {rd["name"]: rd for rd in got["readout_definitions"]}
    assert by_name["Onset #1 for Ratio"]["melt_config"] is None
    for name, measure in (("Tm (Main)", "tm"), ("ΔTm (Main)", "delta_tm")):
        rd = by_name[name]
        assert (rd["unit"], rd["data_type"], rd["aggregation"]) == ("°C", "numeric", "mean")
        assert rd["melt_config"] == {
            "window": "Main",
            "measure": measure,
            "channel_key": "ratio",
            "low": 50.0,
            "high": 85.0,
        }
    assert {rd["name"] for rd in resp.json()["readout_definitions"]} == set(by_name)


async def test_add_window_with_bad_bounds_returns_422(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    protocol_id = await _protocol_id(session_factory, fake_auth.workspace_id)
    url = f"/api/v1/protocols/{protocol_id}/temperature-windows"
    for body in (_window(low=85.0, high=50.0), _window(low=60.0, high=60.0), _window(measures=[])):
        resp = await client.post(url, json=body)
        assert resp.status_code == 422, resp.text

    got = (await client.get(f"/api/v1/protocols/{protocol_id}")).json()
    assert [rd["name"] for rd in got["readout_definitions"]] == ["Onset #1 for Ratio"]


async def test_viewer_cannot_add_a_window(
    viewer_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    protocol_id = await _protocol_id(session_factory, fake_auth.workspace_id)
    resp = await viewer_client.post(
        f"/api/v1/protocols/{protocol_id}/temperature-windows", json=_window()
    )
    assert resp.status_code == 403, resp.text


async def test_update_readout_sets_and_clears_melt_config(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    protocol_id = await _protocol_id(session_factory, fake_auth.workspace_id)
    # A window's limits change only on a draft protocol.
    async with session_factory() as session:
        await session.execute(
            sa.text("UPDATE protocols SET status = 'draft' WHERE id = :id"), {"id": protocol_id}
        )
        await session.commit()
    added = await client.post(
        f"/api/v1/protocols/{protocol_id}/temperature-windows", json=_window(measures=["tm"])
    )
    rd = next(r for r in added.json()["readout_definitions"] if r["name"] == "Tm (Main)")
    url = f"/api/v1/protocols/{protocol_id}/readout-definitions/{rd['id']}"

    moved = rd["melt_config"] | {"low": 55.0}
    resp = await client.put(url, json={"melt_config": moved})
    assert resp.status_code == 200, resp.text
    updated = next(r for r in resp.json()["readout_definitions"] if r["id"] == rd["id"])
    assert updated["melt_config"]["low"] == 55.0

    resp = await client.put(url, json={"melt_config": None})
    assert resp.status_code == 200, resp.text
    cleared = next(r for r in resp.json()["readout_definitions"] if r["id"] == rd["id"])
    assert cleared["melt_config"] is None


async def test_update_readout_with_malformed_melt_config_returns_422(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    protocol_id = await _protocol_id(session_factory, fake_auth.workspace_id)
    async with session_factory() as session:
        await session.execute(
            sa.text("UPDATE protocols SET status = 'draft' WHERE id = :id"), {"id": protocol_id}
        )
        await session.commit()
    added = await client.post(
        f"/api/v1/protocols/{protocol_id}/temperature-windows", json=_window(measures=["tm"])
    )
    rd = next(r for r in added.json()["readout_definitions"] if r["name"] == "Tm (Main)")
    url = f"/api/v1/protocols/{protocol_id}/readout-definitions/{rd['id']}"
    good = rd["melt_config"]
    missing_low = {k: v for k, v in good.items() if k != "low"}
    for bad in (missing_low, good | {"measure": "tmax"}, good | {"high": "hot"}):
        resp = await client.put(url, json={"melt_config": bad})
        assert resp.status_code == 422, resp.text
