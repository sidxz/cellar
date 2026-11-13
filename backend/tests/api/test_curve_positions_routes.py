"""API tests: curves across runs (positions with curves, curves for a list of positions)
and the protocol's measured-curves flag.

Full HTTP stack with a synthetic raw export imported into two runs of one protocol.
"""

from __future__ import annotations

import uuid
from dataclasses import replace

import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.api.test_instrument_import_routes import Seeded, _import, _seed
from tests.fixtures.dose_response_curves import _insert_protocol, _insert_run

BATCH_URL = "/api/v1/measured-curves:batch"


async def _two_runs(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], ws: uuid.UUID
) -> tuple[Seeded, uuid.UUID, uuid.UUID]:
    """Seed, add a second run of the same protocol, import into both.
    Returns the seed, the protocol id and the second run's id."""
    s = await _seed(session_factory, ws)
    run_2 = uuid.uuid4()
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        protocol_id = (
            await uow.session.execute(
                sa.text("SELECT protocol_id FROM runs WHERE id = :id"), {"id": s.run_id}
            )
        ).scalar_one()
        await _insert_run(uow, run_2, protocol_id, ws)
        await uow.commit()
    await _import(client, s)
    await _import(client, replace(s, run_id=run_2))
    return s, protocol_id, run_2


def _positions_url(protocol_id: uuid.UUID) -> str:
    return f"/api/v1/protocols/{protocol_id}/curve-positions"


async def test_list_runs_then_positions_then_curves(client, session_factory, fake_auth):
    s, protocol_id, run_2 = await _two_runs(client, session_factory, fake_auth.workspace_id)
    run_1 = s.run_id
    positions_url = _positions_url(protocol_id)

    resp = await client.get(positions_url)
    assert resp.status_code == 200, resp.text
    listing = resp.json()
    assert len(listing["runs"]) == 2 and listing["positions"] == []
    assert listing["protocol_id"] == str(protocol_id) and listing["dose_unit"] == "uM"
    run = listing["runs"][0]
    assert run["position_count"] == 3 and run["holder"]["kind"] == "cassette"
    assert [c["key"] for c in run["channels"]] == ["ratio", "f330", "f350", "scattering"]
    assert {"run_date", "operator", "status", "notes"} <= run.keys()

    found = (await client.get(positions_url, params={"run_ids": [str(run_1), str(run_2)]})).json()
    assert len(found["positions"]) == 6
    assert {p["run_id"] for p in found["positions"]} == {str(run_1), str(run_2)}
    assert found["positions"][0]["position_label"]
    ids = [p["well_id"] for p in found["positions"]]

    resp = await client.post(BATCH_URL, json={"well_ids": ids, "channel": "ratio"})
    assert resp.status_code == 200, resp.text
    batch = resp.json()
    assert [c["well_id"] for c in batch["curves"]] == ids
    assert batch["view"] == "measured" and batch["window"] is None and batch["channel"] == "ratio"
    single = (await client.get(f"/api/v1/runs/{run_1}/curves")).json()["curves"][0]
    same = next(c for c in batch["curves"] if c["well_id"] == single["well_id"])
    assert same["x"] == single["x"] and same["reported"] == single["reported"]


async def test_positions_by_compound_span_runs_and_bring_each_runs_references(
    client, session_factory, fake_auth
):
    s, protocol_id, run_2 = await _two_runs(client, session_factory, fake_auth.workspace_id)
    resp = await client.get(
        _positions_url(protocol_id), params={"molecule_ids": [str(s.molecule_id)]}
    )
    assert resp.status_code == 200, resp.text
    found = resp.json()["positions"]
    assert sorted((p["run_id"], p["well_type"]) for p in found) == sorted(
        [
            (str(s.run_id), "reference"),
            (str(s.run_id), "sample"),
            (str(run_2), "reference"),
            (str(run_2), "sample"),
        ]
    )
    samples = [p for p in found if p["well_type"] == "sample"]
    assert {p["molecule_id"] for p in samples} == {str(s.molecule_id)}
    assert {p["batch_id"] for p in samples} == {str(s.batch_id)}


async def test_batch_refuses_more_than_100_positions(client):
    resp = await client.post(
        BATCH_URL,
        json={"well_ids": [str(uuid.uuid4()) for _ in range(101)], "channel": "ratio"},
    )
    assert resp.status_code == 422


async def test_unknown_position_is_absent_not_an_error(client, session_factory, fake_auth):
    s, protocol_id, _ = await _two_runs(client, session_factory, fake_auth.workspace_id)
    found = (
        await client.get(_positions_url(protocol_id), params={"run_ids": [str(s.run_id)]})
    ).json()
    real = found["positions"][0]["well_id"]
    resp = await client.post(
        BATCH_URL, json={"well_ids": [real, str(uuid.uuid4())], "channel": "ratio"}
    )
    assert resp.status_code == 200, resp.text
    assert [c["well_id"] for c in resp.json()["curves"]] == [real]


async def test_derivative_window_is_stated_and_can_be_sent_back(
    client, session_factory, fake_auth
):
    s, protocol_id, run_2 = await _two_runs(client, session_factory, fake_auth.workspace_id)
    found = (
        await client.get(
            _positions_url(protocol_id), params={"run_ids": [str(s.run_id), str(run_2)]}
        )
    ).json()
    ids = [p["well_id"] for p in found["positions"]]
    first = (
        await client.post(
            BATCH_URL, json={"well_ids": ids[:3], "channel": "ratio", "view": "derivative"}
        )
    ).json()
    second = (
        await client.post(
            BATCH_URL,
            json={
                "well_ids": ids[3:],
                "channel": "ratio",
                "view": "derivative",
                "window": first["window"],
            },
        )
    ).json()
    assert first["window"] > 0 and second["window"] == first["window"]
    assert first["view"] == second["view"] == "derivative" and len(second["curves"]) == 3
    bad = await client.post(
        BATCH_URL, json={"well_ids": ids, "channel": "ratio", "view": "derivative", "window": 0}
    )
    assert bad.status_code == 422


async def test_more_than_8_runs_returns_422(client, session_factory, fake_auth):
    s = await _seed(session_factory, fake_auth.workspace_id)
    async with session_factory() as session:
        protocol_id = (
            await session.execute(
                sa.text("SELECT protocol_id FROM runs WHERE id = :id"), {"id": s.run_id}
            )
        ).scalar_one()
    resp = await client.get(
        _positions_url(protocol_id), params={"run_ids": [str(uuid.uuid4()) for _ in range(9)]}
    )
    assert resp.status_code == 422
    assert "At most 8 runs can be shown at once" in resp.text


async def test_protocol_reports_has_measured_curves(client, session_factory, fake_auth):
    ws = fake_auth.workspace_id
    _, with_curves, _ = await _two_runs(client, session_factory, ws)
    without = uuid.uuid4()
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await _insert_protocol(uow, without, ws)
        await uow.commit()

    assert (await client.get(f"/api/v1/protocols/{with_curves}")).json()[
        "has_measured_curves"
    ] is True
    assert (await client.get(f"/api/v1/protocols/{without}")).json()[
        "has_measured_curves"
    ] is False
    items = (await client.get("/api/v1/protocols")).json()["items"]
    assert {i["id"]: i["has_measured_curves"] for i in items} == {
        str(with_curves): True,
        str(without): False,
    }


async def test_unknown_protocol_returns_404(client):
    resp = await client.get(_positions_url(uuid.uuid4()))
    assert resp.status_code == 404


async def test_viewer_can_read_both(viewer_client, client, session_factory, workspace_id):
    s, protocol_id, _ = await _two_runs(client, session_factory, workspace_id)
    found = await viewer_client.get(
        _positions_url(protocol_id), params={"run_ids": [str(s.run_id)]}
    )
    assert found.status_code == 200, found.text
    ids = [p["well_id"] for p in found.json()["positions"]]
    batch = await viewer_client.post(BATCH_URL, json={"well_ids": ids, "channel": "ratio"})
    assert batch.status_code == 200, batch.text
    assert len(batch.json()["curves"]) == 3
