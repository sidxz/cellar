"""API: POST /api/v1/runs/{run_id}/outliers — flag wells as outliers, then recalculate."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa

from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.integration import _screening_seed as seed

pytestmark = pytest.mark.asyncio

# NadD-Sumo dose response, 2026-10-08: the platform flags negative controls A01 and B01.
NEG = (0.40, 0.55, 0.65, 0.55, 0.61, 0.61, 0.54, 0.63, 0.63, 0.63, 0.60)
POS = (0.19, 0.19, 0.20, 0.19, 0.19, 0.19, 0.20, 0.20, 0.20, 0.20, 0.20)
ROWS = "ABCDEFGHIJK"


async def _run(session_factory, ws, *, status="draft", locked=False):  # type: ignore[no-untyped-def]
    """One 384-well plate: NEG in column 1, POS in column 24, % inhibition (LOW)."""
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        s = uow.session
        p = await seed.protocol(s, ws)
        await s.execute(
            sa.text("UPDATE protocols SET pos_control_signal = 'low' WHERE id = :p"), {"p": p}
        )
        rd = await seed.readout_def(s, p, name="raw AU", normalizations=["percent_inhibition"])
        run = await seed.run(s, ws, p, date(2026, 10, 8), status=status)
        if locked:
            await s.execute(sa.text("UPDATE runs SET is_locked = true WHERE id = :r"), {"r": run})
        plate = await seed.plate(s, run, 1)
        neg = []
        for row, v in zip(ROWS, NEG, strict=True):
            w = await seed.well(s, plate, row, 1, well_type="negative_control")
            await seed.readout(s, ws, run, rd, None, v, well_id=w)
            neg.append(w)
        for row, v in zip(ROWS, POS, strict=True):
            w = await seed.well(s, plate, row, 24, well_type="positive_control")
            await seed.readout(s, ws, run, rd, None, v, well_id=w)
        await uow.commit()
    return run, rd, neg


def _url(run_id: uuid.UUID) -> str:
    return f"/api/v1/runs/{run_id}/outliers"


async def test_flagging_a01_and_b01_takes_them_out_of_plate_qc(client, session_factory, fake_auth):
    run, rd, neg = await _run(session_factory, fake_auth.workspace_id)
    assert (await client.post(f"/api/v1/runs/{run}/recompute")).status_code == 200
    before = (await client.get(f"/api/v1/runs/{run}")).json()["qc_metrics"]

    body = {"well_ids": [str(neg[0]), str(neg[1])], "outlier": True, "reason": "bubble"}
    resp = await client.post(_url(run), json=body)
    again = await client.post(_url(run), json=body)

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"wells_changed": 2, "recalculated": True, "compute_warning": None}
    assert again.json()["wells_changed"] == 0
    [(plate_id, per_rd)] = before["plates"].items()
    assert per_rd[str(rd)]["raw"]["z_prime"] == pytest.approx(0.408, abs=1e-3)
    after = (await client.get(f"/api/v1/runs/{run}")).json()["qc_metrics"]["plates"][plate_id]
    raw, inh = after[str(rd)]["raw"], after[str(rd)]["percent_inhibition"]
    assert raw["z_prime"] == pytest.approx(0.688, abs=1e-3)
    assert (raw["neg_n"], inh["neg_n"]) == (9, 9)
    assert inh["neg_mean"] == pytest.approx(0.0, abs=1e-9)
    assert inh["neg_sd"] == pytest.approx(9.2, abs=0.1)

    rows = (await client.get("/api/v1/readout-data", params={"run_id": str(run)})).json()
    flagged = {(r["well_id"], r["is_computed"]) for r in rows if r["is_outlier"]}
    # Raw and % inhibition rows of A01 and B01, nothing else.
    assert flagged == {(str(w), c) for w in neg[:2] for c in (False, True)}


async def test_removing_the_flag_restores_every_control(client, session_factory, fake_auth):
    run, rd, neg = await _run(session_factory, fake_auth.workspace_id)
    ids = [str(neg[0])]
    await client.post(_url(run), json={"well_ids": ids, "outlier": True})
    resp = await client.post(_url(run), json={"well_ids": ids, "outlier": False})

    assert resp.json()["wells_changed"] == 1
    qc = (await client.get(f"/api/v1/runs/{run}")).json()["qc_metrics"]["plates"]
    [per_rd] = qc.values()
    assert per_rd[str(rd)]["raw"]["neg_n"] == 11


@pytest.mark.parametrize(("status", "locked"), [("approved", False), ("completed", True)])
async def test_refused_on_an_approved_or_locked_run(
    client, session_factory, fake_auth, status, locked
):
    run, _, neg = await _run(session_factory, fake_auth.workspace_id, status=status, locked=locked)
    resp = await client.post(_url(run), json={"well_ids": [str(neg[0])], "outlier": True})
    assert resp.status_code == 409, resp.text
    rows = (await client.get("/api/v1/readout-data", params={"run_id": str(run)})).json()
    assert not any(r["is_outlier"] for r in rows)


async def test_a_well_of_another_run_is_refused(client, session_factory, fake_auth):
    run, _, _ = await _run(session_factory, fake_auth.workspace_id)
    _, _, other = await _run(session_factory, fake_auth.workspace_id)
    resp = await client.post(_url(run), json={"well_ids": [str(other[0])], "outlier": True})
    assert resp.status_code == 422, resp.text
