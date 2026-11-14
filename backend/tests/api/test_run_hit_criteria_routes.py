"""API tests: a run's hit rule on thermal shift readouts."""

from __future__ import annotations

import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.api.test_instrument_import_routes import _seed
from tests.api.test_temperature_window_routes import _window
from tests.fakes.fake_auth import FakeAuth


async def test_run_hit_rule_accepts_outside_and_refuses_series_values(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    seeded = await _seed(session_factory, fake_auth.workspace_id)
    async with session_factory() as session:
        protocol_id = (
            await session.execute(
                sa.text("SELECT protocol_id FROM runs WHERE id = :id"), {"id": seeded.run_id}
            )
        ).scalar_one()
    resp = await client.post(
        f"/api/v1/protocols/{protocol_id}/temperature-windows",
        json=_window(measures=["delta_tm", "max_delta_tm"]),
    )
    assert resp.status_code == 201, resp.text
    run_id = seeded.run_id
    url = f"/api/v1/runs/{run_id}/hit-criteria"

    outside = {"readout_name": "ΔTm (Main)", "operator": "not_between", "value": [-2.0, 2.0]}
    resp = await client.put(url, json={"criteria": [outside]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["hit_criteria"][0]["operator"] == "not_between"

    series = {"readout_name": "Max ΔTm (Main)", "operator": "lt", "value": -2.0}
    resp = await client.put(url, json={"criteria": [series]})
    assert resp.status_code == 422, resp.text
    assert "Max ΔTm (Main)" in resp.text
