"""API: POST /api/v1/runs/{run_id}/outliers — flag wells as outliers, then recalculate."""

from __future__ import annotations

import asyncio
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


async def test_a_flag_that_leaves_no_anchor_saves_nothing(client, session_factory, fake_auth):
    run, _, neg = await _run(session_factory, fake_auth.workspace_id)
    assert (await client.post(f"/api/v1/runs/{run}/recompute")).status_code == 200
    before = (await client.get(f"/api/v1/runs/{run}")).json()["qc_metrics"]

    resp = await client.post(_url(run), json={"well_ids": [str(w) for w in neg], "outlier": True})

    assert resp.status_code == 422, resp.text
    assert "Not saved" in resp.text
    rows = (await client.get("/api/v1/readout-data", params={"run_id": str(run)})).json()
    assert not any(r["is_outlier"] for r in rows)
    assert (await client.get(f"/api/v1/runs/{run}")).json()["qc_metrics"] == before


async def test_an_approval_saved_meanwhile_makes_the_flag_a_conflict(
    client, session_factory, fake_auth
):
    run, _, neg = await _run(session_factory, fake_auth.workspace_id, status="completed")
    body = {"well_ids": [str(neg[0])], "outlier": True, "reason": "bubble"}
    async with session_factory() as other:  # another user approves; not committed yet
        await other.execute(
            sa.text("UPDATE runs SET status = 'approved', version = version + 1 WHERE id = :r"),
            {"r": run},
        )
        flagging = asyncio.create_task(client.post(_url(run), json=body))
        await asyncio.sleep(0.5)
        assert not flagging.done()  # waits for the approval
        await other.commit()
    resp = await flagging

    assert resp.status_code == 409, resp.text
    rows = (await client.get("/api/v1/readout-data", params={"run_id": str(run)})).json()
    assert not any(r["is_outlier"] for r in rows)


async def _curves(session_factory, run):  # type: ignore[no-untyped-def]
    async with session_factory() as s:
        q = sa.text(
            "SELECT c.id, c.molecule_id, c.fitted_value, c.excluded_points, c.raw_data, "
            "c.updated_at FROM dose_response_curves c WHERE c.run_id = :r"
        )
        return {r.molecule_id: r for r in (await s.execute(q, {"r": run})).all()}


async def test_a_flag_refits_only_the_curves_it_touches_keeping_the_chemists_exclusion(
    client, session_factory, fake_auth
):
    """Two plates (HIGH: positive = uninhibited). Compound A titrated on plate 1, B on
    plate 2. A chemist excludes one of A's points; then a negative control of plate 1 is
    flagged: plate 1's % values move, A is refitted in place with the exclusion kept on
    the same well, and B — on plate 2 — is not touched."""
    ws = fake_auth.workspace_id
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        s = uow.session
        org = await seed.org(s, ws)
        p = await seed.protocol(s, ws)
        signal = await seed.readout_def(s, p, name="Signal", normalizations=["percent_inhibition"])
        await seed.readout_def(s, p, name="IC50", data_type="dose_response")
        run = await seed.run(s, ws, p, date(2026, 10, 8))
        stray = None
        for n, mol_name in ((1, "A"), (2, "B")):
            plate = await seed.plate(s, run, n)
            for col, (well_type, v) in enumerate(
                [("positive_control", 100.0)] * 3 + [("negative_control", 0.0)] * 3, start=1
            ):
                w = await seed.well(s, plate, "P", col, well_type=well_type)
                await seed.readout(s, ws, run, signal, None, v, well_id=w)  # type: ignore[arg-type]
            if n == 1:
                stray = await seed.well(s, plate, "P", 7, well_type="negative_control")
                await seed.readout(s, ws, run, signal, None, 30.0, well_id=stray)  # type: ignore[arg-type]
            mol = await seed.molecule(s, ws, org, mol_name)
            b = await seed.batch(s, ws, mol, f"B-{mol_name}")
            for col, (dose, v) in enumerate(
                [
                    (0.01, 98.0),
                    (0.1, 90.0),
                    (1.0, 60.0),
                    (10.0, 25.0),
                    (100.0, 8.0),
                    (1000.0, 3.0),
                ],
                start=1,
            ):
                w = await seed.well(s, plate, "A", col, dose=dose, batch_id=b)
                await seed.readout(s, ws, run, signal, mol, v, well_id=w, batch_id=b)
        await uow.commit()
    assert (await client.post(f"/api/v1/runs/{run}/recompute")).status_code == 200
    first = await _curves(session_factory, run)
    async with session_factory() as s:
        q = sa.text("SELECT id, name FROM molecules WHERE id = ANY(:ids)")
        names = {r.name: r.id for r in (await s.execute(q, {"ids": list(first)})).all()}
    a, b = first[names["A"]], first[names["B"]]
    point = sorted(a.raw_data, key=lambda p: p["concentration"])[1]  # dose 0.1
    resp = await client.post(
        f"/api/v1/dose-response-curves/{a.id}/refit",
        json={
            "exclusions": [
                {
                    "idx": 1,
                    "source": "manual",
                    "excluded": True,
                    "reason": "contamination",
                    "note": "precipitate",
                    "concentration": point["concentration"],
                    "response": point["response"],
                }
            ],
            "save_reason": "contamination",
        },
    )
    assert resp.status_code == 200, resp.text
    edited = await _curves(session_factory, run)

    resp = await client.post(
        _url(run), json={"well_ids": [str(stray)], "outlier": True, "reason": "bubble"}
    )

    assert resp.status_code == 200, resp.text
    after = await _curves(session_factory, run)
    a_now, b_now = after[a.molecule_id], after[b.molecule_id]
    assert a_now.id == a.id and b_now.id == b.id
    assert b_now.updated_at == edited[b.molecule_id].updated_at  # not touched
    [hand] = [e for e in a_now.excluded_points if e["source"] == "manual"]
    assert (hand["concentration"], hand["reason"], hand["note"]) == (
        0.1,
        "contamination",
        "precipitate",
    )
    # Plate 1's anchors lost the stray negative (30): the kept point reads its new value.
    assert hand["response"] == pytest.approx(10.0)
    assert hand["response"] != pytest.approx(point["response"])
    assert 0.1 not in [p["concentration"] for p in a_now.raw_data]
