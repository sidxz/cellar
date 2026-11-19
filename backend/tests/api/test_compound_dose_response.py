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


async def test_curves_carry_their_intercepts_with_qualifiers_and_their_fitted_layer(
    client, session_factory, fake_auth
):
    """The same shape as every other curve response: the visualization dialog reads an
    n.d. or censored intercept from its qualifier, and frames a % curve on its layer. A
    curve stored before intercepts were stored reads its fitted value as its one."""
    ws = fake_auth.workspace_id
    spec = {"kind": "ic", "level": 50.0, "basis": "relative_percent", "label": None}
    nd_and_bound = [
        {"spec": spec, "value": None, "at_bound": False, "qualifier": "nd"},
        {"spec": {**spec, "level": 90.0}, "value": 1000.0, "at_bound": True, "qualifier": ">"},
    ]
    exact = [{"spec": spec, "value": 2.0, "ci_low": 1.0, "ci_high": 4.0, "qualifier": "="}]
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        s = uow.session
        mol = await seed.molecule(s, ws, await seed.org(s, ws), "m1")
        p = await seed.protocol(s, ws)
        await seed.readout_def(s, p, name="Signal", normalizations=["percent_inhibition"])
        ic50 = await seed.readout_def(s, p, name="IC50", data_type="dose_response", unit="uM")
        run = await seed.run(s, ws, p, date(2026, 11, 12), status="approved")
        for fitted, ivs in ((1.0, nd_and_bound), (2.0, exact), (3.0, None)):
            await seed.curve(s, ws, p, run, mol, ic50, fitted_value=fitted, intercept_values=ivs)
        await uow.commit()

    resp = await client.get(f"/api/v1/protocols/{p}/compounds/{mol}/dose-response")

    assert resp.status_code == 200, resp.text
    curves = {c["fitted_value"]: c for c in resp.json()}
    assert {c["fitted_layer"] for c in curves.values()} == {"percent_inhibition"}
    read = {
        fitted: [
            (iv["value"], iv["qualifier"], iv["at_bound"], iv["confidence_interval_low"])
            for iv in c["intercept_values"]
        ]
        for fitted, c in curves.items()
    }
    assert read == {
        1.0: [(None, "nd", False, None), (1000.0, ">", True, None)],
        2.0: [(2.0, "=", False, 1.0)],
        3.0: [(3.0, None, False, None)],
    }


async def test_the_compound_curves_response_is_typed_as_a_curve_response(client):
    """orval generates the endpoint's type from this schema; an untyped list of objects
    leaves every consumer to hand-write it."""
    schema = (await client.get("/openapi.json")).json()
    route = schema["paths"][
        "/api/v1/protocols/{protocol_id}/compounds/{molecule_id}/dose-response"
    ]
    body = route["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert body["items"] == {"$ref": "#/components/schemas/DoseResponseCurveResponse"}
