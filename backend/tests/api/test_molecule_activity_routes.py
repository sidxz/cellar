"""API tests: a compound's Activity summary shows plain readouts and the hit marker."""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.api.test_melting_steps_routes import _setup, _sql
from tests.fakes.fake_auth import FakeAuth


async def test_thermal_shift_values_and_hit_reach_the_compound_page(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    extra = {"measures": ["tm", "delta_tm", "max_delta_tm"]}
    s, _ = await _setup(client, session_factory, fake_auth.workspace_id, main_extra=extra)
    url = f"/api/v1/molecules/{s.molecule_id}/activity"

    resp = await client.get(url)
    assert resp.status_code == 200, resp.text
    [card] = resp.json()["protocols"]
    by_name = {r["readout_name"]: r for r in card["plain_readouts"]}
    assert by_name["Max ΔTm (Main)"]["value"] == pytest.approx(-7.3)
    assert by_name["ΔTm (Main)"]["value"] == pytest.approx(-7.3)
    assert (by_name["ΔTm (Main)"]["run_count"], by_name["ΔTm (Main)"]["draft_run_count"]) == (1, 1)
    assert card["hit"] is None and card["hit_criteria"] == []
    assert by_name["ΔTm (Main)"]["best_direction"] == "magnitude"
    assert [r["run_id"] for r in card["runs"]] == [str(s.run_id)]
    assert card["results_tab"] == "curves"

    rule = {"readout_name": "Max ΔTm (Main)", "operator": "not_between", "value": [-2.0, 2.0]}
    await _sql(
        session_factory,
        "UPDATE protocols SET recommended_hit_criteria = CAST(:c AS jsonb) "
        "WHERE id = (SELECT protocol_id FROM runs WHERE id = :r)",
        c=json.dumps([rule]),
        r=s.run_id,
    )
    [card] = (await client.get(url)).json()["protocols"]
    assert card["hit"] is True
    assert card["hit_criteria"][0]["operator"] == "not_between"
