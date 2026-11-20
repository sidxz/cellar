"""Integration: recompute_all_runs writes plate QC, keeps a chemist's curve exclusion and
the curve's id, and leaves approved runs alone."""

from __future__ import annotations

import json
from datetime import date

import pytest
import sqlalchemy as sa

from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from scripts.recompute_all_runs import _recompute, _runs
from tests.integration import _screening_seed as seed

pytestmark = pytest.mark.asyncio
DOSES = ((0.01, 98.0), (0.1, 90.0), (1.0, 60.0), (10.0, 25.0), (100.0, 8.0))


async def _dr_run(session_factory, ws, status):  # type: ignore[no-untyped-def]
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        s = uow.session
        org = await seed.org(s, ws)
        p = await seed.protocol(s, ws)
        signal = await seed.readout_def(s, p, name="Signal")  # curves fit the raw layer
        ic50 = await seed.readout_def(s, p, name="IC50", data_type="dose_response")
        run = await seed.run(s, ws, p, date(2026, 10, 8), status=status)
        plate = await seed.plate(s, run, 1)
        for col, (well_type, v) in enumerate(
            [("positive_control", 100.0)] * 2 + [("negative_control", 0.0)] * 2, start=1
        ):
            w = await seed.well(s, plate, "P", col, well_type=well_type)
            await seed.readout(s, ws, run, signal, None, v, well_id=w)  # type: ignore[arg-type]
        mol = await seed.molecule(s, ws, org, f"titrated-{status}")
        b = await seed.batch(s, ws, mol, f"B-{status}")
        for col, (dose, v) in enumerate(DOSES, start=1):
            w = await seed.well(s, plate, "A", col, dose=dose, batch_id=b)
            await seed.readout(s, ws, run, signal, mol, v, well_id=w, batch_id=b)
        # A curve as an earlier release left it: a chemist excluded the 0.1 point.
        curve = await seed.curve(s, ws, p, run, mol, ic50, with_well=False, batch_id=b)
        excluded = {
            "idx": 1,
            "source": "manual",
            "excluded": True,
            "reason": "contamination",
            "author_id": str(seed.USER),
            "ts": "2026-11-01T00:00:00+00:00",
            "note": None,
            "concentration": 0.1,
            "response": 90.0,
        }
        await s.execute(
            sa.text(
                "UPDATE dose_response_curves SET excluded_points = cast(:e as jsonb) WHERE id = :c"
            ),
            {"e": json.dumps([excluded]), "c": curve},
        )
        await uow.commit()
    return run, curve


async def test_a_run_is_recomputed_keeping_its_curve_and_the_exclusion(
    session_factory, workspace_id
):
    run, curve = await _dr_run(session_factory, workspace_id, "completed")
    approved, _ = await _dr_run(session_factory, workspace_id, "approved")

    assert {r for _, r in await _runs(session_factory, workspace_id)} == {run, approved}
    line = await _recompute(session_factory, workspace_id, run)
    skipped = await _recompute(session_factory, workspace_id, approved)

    assert line.startswith("ok: 1 curves refitted"), line
    assert skipped.startswith("skipped:"), skipped
    async with session_factory() as s:
        qc = (
            await s.execute(sa.text("SELECT qc_metrics FROM runs WHERE id = :r"), {"r": run})
        ).scalar_one()
        [(cid, points, raw)] = (
            await s.execute(
                sa.text(
                    "SELECT id, excluded_points, raw_data FROM dose_response_curves "
                    "WHERE run_id = :r"
                ),
                {"r": run},
            )
        ).all()
        untouched = (
            await s.execute(sa.text("SELECT qc_metrics FROM runs WHERE id = :r"), {"r": approved})
        ).scalar_one()
    assert qc["plates"] and untouched is None
    assert cid == curve
    [hand] = [e for e in points if e["source"] == "manual"]
    assert (hand["concentration"], hand["reason"]) == (0.1, "contamination")
    assert len(raw) == len(DOSES) - 1
