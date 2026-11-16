"""API: GET /api/v1/protocols/{id}/compounds/{molecule_id}/dose-response."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.integration import _screening_seed as seed

pytestmark = pytest.mark.asyncio


async def test_curves_carry_their_readout_and_the_workspaces_batch_number(
    client, session_factory, fake_auth
):
    ws = fake_auth.workspace_id
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        s = uow.session
        mol = await seed.molecule(s, ws, await seed.org(s, ws), "m1")
        p = await seed.protocol(s, ws)
        ic50 = await seed.readout_def(s, p, name="IC50", data_type="dose_response", unit="uM")
        run = await seed.run(s, ws, p, date(2026, 11, 12), status="approved")
        ours = await seed.batch(s, ws, mol, "CEL-000001-01")
        foreign = await seed.batch(s, uuid.uuid4(), mol, "FOREIGN-01")
        await seed.curve(s, ws, p, run, mol, ic50, fitted_value=1.0, batch_id=ours)
        await seed.curve(s, ws, p, run, mol, ic50, fitted_value=2.0, batch_id=foreign)
        await uow.commit()

    resp = await client.get(f"/api/v1/protocols/{p}/compounds/{mol}/dose-response")

    assert resp.status_code == 200, resp.text
    by_value = {c["fitted_value"]: c for c in resp.json()}
    assert {c["readout_definition_id"] for c in by_value.values()} == {str(ic50)}
    assert by_value[1.0]["batch_number"] == "CEL-000001-01"
    assert by_value[2.0]["batch_number"] is None  # another workspace's batch is not read
