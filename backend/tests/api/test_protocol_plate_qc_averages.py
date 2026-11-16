"""API: GET /api/v1/protocols/{id}/plate-qc-averages."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.integration import _screening_seed as seed

pytestmark = pytest.mark.asyncio


def _qc(rd: uuid.UUID, z: float, neg: float) -> dict:
    entry = {"z_prime": z, "pos_mean": 100.0, "neg_mean": neg, "control_fits": []}
    return {"plates": {str(uuid.uuid4()): {str(rd): {"percent_inhibition": entry}}}}


async def test_plate_qc_averages_over_the_protocols_runs(client, session_factory, fake_auth):
    ws = fake_auth.workspace_id
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        s = uow.session
        p = await seed.protocol(s, ws)
        rd = await seed.readout_def(s, p, name="Signal", unit="AU")
        await seed.run(s, ws, p, date(2026, 11, 5), qc_metrics=_qc(rd, 0.8, -2.0))
        await seed.run(s, ws, p, date(2026, 11, 6), qc_metrics=_qc(rd, 0.6, 2.0))
        await seed.run(s, ws, p, date(2026, 11, 7), status="rejected", qc_metrics=_qc(rd, -1, 50))
        await uow.commit()

    resp = await client.get(f"/api/v1/protocols/{p}/plate-qc-averages")
    missing = await client.get(f"/api/v1/protocols/{uuid.uuid4()}/plate-qc-averages")

    assert resp.status_code == 200, resp.text
    [avg] = resp.json()["averages"]
    assert (avg["readout_definition_id"], avg["layer"]) == (str(rd), "percent_inhibition")
    assert avg["z_prime"]["n"] == 2 and avg["z_prime"]["mean"] == pytest.approx(0.7)
    assert avg["neg_mean"] == {"mean": 0.0, "sd": pytest.approx(2.8284, abs=1e-4), "n": 2}
    assert avg["control_fits"] == []
    assert missing.status_code == 404
