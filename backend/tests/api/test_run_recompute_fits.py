"""API: POST /api/v1/runs/{run_id}/recompute — what the dose-response refit reports and keeps."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa

from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.integration import _screening_seed as seed

pytestmark = pytest.mark.asyncio


async def _curves(session_factory, run: uuid.UUID) -> int:  # type: ignore[no-untyped-def]
    async with session_factory() as s:
        q = sa.text("SELECT count(*) FROM dose_response_curves WHERE run_id = :r")
        return (await s.execute(q, {"r": run})).scalar_one()


async def test_single_dose_compounds_are_a_neutral_count(client, session_factory, fake_auth):
    """Run 394e4741's shape: one compound titrated at four doses, two screened at one dose.
    The two get no curve, counted in a note — not reported as fit issues, and no UUID."""
    ws = fake_auth.workspace_id
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        s = uow.session
        org = await seed.org(s, ws)
        p = await seed.protocol(s, ws)
        signal = await seed.readout_def(s, p, name="Signal", normalizations=["percent_inhibition"])
        await seed.readout_def(s, p, name="IC50", data_type="dose_response")
        run = await seed.run(s, ws, p, date(2026, 10, 8))
        plate = await seed.plate(s, run, 1)
        controls = [("positive_control", 1.0)] * 2 + [("negative_control", 0.0)] * 2
        for col, (well_type, value) in enumerate(controls, start=1):
            w = await seed.well(s, plate, "P", col, well_type=well_type)
            await seed.readout(s, ws, run, signal, None, value, well_id=w)  # type: ignore[arg-type]
        titrated = await seed.molecule(s, ws, org, "titrated")
        series = await seed.batch(s, ws, titrated, "B-1")
        for col, (dose, value) in enumerate(
            [(0.1, 0.9), (1.0, 0.7), (10.0, 0.3), (100.0, 0.1)], 1
        ):
            w = await seed.well(s, plate, "A", col, dose=dose, batch_id=series)
            await seed.readout(s, ws, run, signal, titrated, value, well_id=w, batch_id=series)
        for row in "BC":
            mol = await seed.molecule(s, ws, org, f"single-{row}")
            b = await seed.batch(s, ws, mol, f"B-{row}")
            for col in (1, 2):
                w = await seed.well(s, plate, row, col, dose=50.0, batch_id=b)
                await seed.readout(s, ws, run, signal, mol, 0.5, well_id=w, batch_id=b)
        await uow.commit()

    resp = await client.post(f"/api/v1/runs/{run}/recompute")

    assert resp.status_code == 200, resp.text
    assert resp.json()["fit_warnings"] == []
    assert resp.json()["fit_notes"] == ["2 compounds tested at fewer than 4 doses — no curve"]
    assert await _curves(session_factory, run) == 1


async def test_curves_of_rows_on_no_well_of_the_run_survive_a_recompute(
    client, session_factory, fake_auth
):
    """The [E2E demo] InhA-by-ATP runs: 40 curves, readout rows naming wells the run does not
    have. A recompute cannot rebuild them, so it keeps them."""
    ws = fake_auth.workspace_id
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        s = uow.session
        org = await seed.org(s, ws)
        p = await seed.protocol(s, ws)
        signal = await seed.readout_def(s, p, name="Signal", normalizations=["percent_inhibition"])
        ic50 = await seed.readout_def(s, p, name="IC50", data_type="dose_response")
        run = await seed.run(s, ws, p, date(2026, 10, 8))
        mol = await seed.molecule(s, ws, org, "demo")
        for v in (0.9, 0.7, 0.3, 0.1):
            await seed.readout(s, ws, run, signal, mol, v)  # a well id the run does not have
        await seed.curve(s, ws, p, run, mol, ic50, with_well=False)
        await uow.commit()

    resp = await client.post(f"/api/v1/runs/{run}/recompute")

    assert resp.status_code == 200, resp.text
    assert await _curves(session_factory, run) == 1


async def _plain_run(session_factory, ws, *, status="completed", locked=False):  # type: ignore[no-untyped-def]
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        s = uow.session
        p = await seed.protocol(s, ws)
        rd = await seed.readout_def(s, p, name="Signal")
        run = await seed.run(s, ws, p, date(2026, 10, 8), status=status)
        if locked:
            await s.execute(sa.text("UPDATE runs SET is_locked = true WHERE id = :r"), {"r": run})
        plate = await seed.plate(s, run, 1)
        w = await seed.well(s, plate, "A", 1)
        await seed.readout(s, ws, run, rd, None, 1.0, well_id=w)  # type: ignore[arg-type]
        await uow.commit()
    return run


async def test_a_viewer_cannot_recompute(viewer_client, session_factory, workspace_id):
    run = await _plain_run(session_factory, workspace_id)
    resp = await viewer_client.post(f"/api/v1/runs/{run}/recompute")
    assert resp.status_code == 403, resp.text


@pytest.mark.parametrize(("status", "locked"), [("approved", False), ("completed", True)])
async def test_a_locked_or_approved_run_is_not_recomputed(
    client, session_factory, fake_auth, status, locked
):
    run = await _plain_run(session_factory, fake_auth.workspace_id, status=status, locked=locked)
    resp = await client.post(f"/api/v1/runs/{run}/recompute")
    assert resp.status_code == 409, resp.text
    async with session_factory() as s:
        q = sa.text("SELECT count(*) FROM readout_data WHERE run_id = :r AND is_computed")
        assert (await s.execute(q, {"r": run})).scalar_one() == 0


async def test_a_recompute_says_how_many_edited_curves_it_reset(
    client, session_factory, fake_auth
):
    ws = fake_auth.workspace_id
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        s = uow.session
        org = await seed.org(s, ws)
        p = await seed.protocol(s, ws)
        signal = await seed.readout_def(s, p, name="Signal", normalizations=["percent_inhibition"])
        await seed.readout_def(s, p, name="IC50", data_type="dose_response")
        run = await seed.run(s, ws, p, date(2026, 10, 8))
        plate = await seed.plate(s, run, 1)
        for col, (well_type, v) in enumerate(
            [("positive_control", 100.0)] * 2 + [("negative_control", 0.0)] * 2, start=1
        ):
            w = await seed.well(s, plate, "P", col, well_type=well_type)
            await seed.readout(s, ws, run, signal, None, v, well_id=w)  # type: ignore[arg-type]
        mol = await seed.molecule(s, ws, org, "titrated")
        b = await seed.batch(s, ws, mol, "B-1")
        for col, (dose, v) in enumerate(
            [(0.01, 98.0), (0.1, 90.0), (1.0, 60.0), (10.0, 25.0), (100.0, 8.0)], start=1
        ):
            w = await seed.well(s, plate, "A", col, dose=dose, batch_id=b)
            await seed.readout(s, ws, run, signal, mol, v, well_id=w, batch_id=b)
        await uow.commit()
    assert (await client.post(f"/api/v1/runs/{run}/recompute")).json()["fit_notes"] == []
    async with session_factory() as s:
        q = sa.text("SELECT id, raw_data FROM dose_response_curves WHERE run_id = :r")
        curve = (await s.execute(q, {"r": run})).one()
    point = sorted(curve.raw_data, key=lambda p: p["concentration"])[0]
    edit = {"idx": 0, "source": "manual", "excluded": True, "reason": "other", **point}
    resp = await client.post(
        f"/api/v1/dose-response-curves/{curve.id}/refit",
        json={"exclusions": [edit], "save_reason": "other"},
    )
    assert resp.status_code == 200, resp.text

    resp = await client.post(f"/api/v1/runs/{run}/recompute")

    assert resp.json()["fit_notes"] == [
        "1 curve with excluded points or fit settings of their own refitted with these "
        "settings; those edits were reset"
    ]
