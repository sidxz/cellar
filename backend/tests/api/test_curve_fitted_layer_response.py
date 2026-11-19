"""API test: every payload that returns a dose-response curve says which layer it fits.

``fitted_layer`` is resolved from the curve's protocol as it is now, by the rule the fit
uses, so a curve stored before it existed resolves too; null for raw values. Every curve
seeded here is such a stored curve (no qualifiers, no layer of its own).
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from httpx import AsyncClient

from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.integration import _screening_seed as seed

pytestmark = pytest.mark.asyncio

# The seed's DR config fits "Signal" on percent_inhibition: raw when Signal has no layer.
_LAYERS = {"percent": ["percent_inhibition"], "raw": []}
_EXPECTED = {"percent": "percent_inhibition", "raw": None}


async def _seed(uow: AsyncUnitOfWork, ws: uuid.UUID) -> dict[str, dict[str, uuid.UUID]]:
    out: dict[str, dict[str, uuid.UUID]] = {}
    async with uow:
        s = uow.session
        org = await seed.org(s, ws)
        for kind, layers in _LAYERS.items():
            mol = await seed.molecule(s, ws, org, f"m-{kind}")
            p = await seed.protocol(s, ws)
            await seed.readout_def(s, p, name="Signal", normalizations=layers)
            rd = await seed.readout_def(s, p, name="IC50", data_type="dose_response", unit="uM")
            run = await seed.run(s, ws, p, date(2026, 11, 19), status="completed")
            curve = await seed.curve(s, ws, p, run, mol, rd, fitted_value=1.0)
            out[kind] = {"p": p, "rd": rd, "run": run, "mol": mol, "curve": curve}
        await uow.commit()
    return out


@pytest.mark.parametrize("kind", list(_LAYERS))
async def test_run_curves_and_curves_by_id_carry_the_fitted_layer(
    client: AsyncClient, uow: AsyncUnitOfWork, workspace_id: uuid.UUID, kind: str
) -> None:
    w = (await _seed(uow, workspace_id))[kind]

    listed = await client.get("/api/v1/dose-response-curves", params={"run_id": str(w["run"])})
    batch = await client.post(
        "/api/v1/dose-response/curves:batch", json={"curve_ids": [str(w["curve"])]}
    )
    classified = await client.patch(
        f"/api/v1/dose-response-curves/{w['curve']}/classify", json={"curve_class": "partial"}
    )

    assert listed.status_code == batch.status_code == classified.status_code == 200
    (curve,) = listed.json()
    (by_id,) = batch.json()["curves"]
    expected = _EXPECTED[kind]
    assert (curve["fitted_layer"], by_id["fitted_layer"]) == (expected, expected)
    assert classified.json()["fitted_layer"] == expected


@pytest.mark.parametrize("kind", list(_LAYERS))
async def test_compound_activity_detail_carries_the_fitted_layer(
    client: AsyncClient, uow: AsyncUnitOfWork, workspace_id: uuid.UUID, kind: str
) -> None:
    w = (await _seed(uow, workspace_id))[kind]

    response = await client.get(f"/api/v1/molecules/{w['mol']}/activity-detail")

    assert response.status_code == 200, response.text
    (group,) = response.json()["protocols"]
    (detail,) = group["curves"]
    assert detail["fitted_layer"] == _EXPECTED[kind]


@pytest.mark.parametrize("kind", list(_LAYERS))
async def test_protocol_activity_names_each_dose_response_readouts_layer(
    client: AsyncClient, uow: AsyncUnitOfWork, workspace_id: uuid.UUID, kind: str
) -> None:
    w = (await _seed(uow, workspace_id))[kind]

    response = await client.get(f"/api/v1/protocols/{w['p']}/activity-summary")

    assert response.status_code == 200, response.text
    layers = {d["name"]: d["fitted_layer"] for d in response.json()["readout_definitions"]}
    assert layers == {"IC50": _EXPECTED[kind], "Signal": None}


@pytest.mark.parametrize("kind", list(_LAYERS))
async def test_visualization_curve_columns_carry_the_fitted_layer(
    client: AsyncClient, uow: AsyncUnitOfWork, workspace_id: uuid.UUID, kind: str
) -> None:
    w = (await _seed(uow, workspace_id))[kind]

    response = await client.post(
        "/api/v1/visualization/dataset",
        json={"source": {"kind": "run", "run_id": str(w["run"])}, "level": "runs"},
    )

    assert response.status_code == 200, response.text
    curve_columns = [
        c
        for c in response.json()["columns"]
        if c["provenance"]["readout_definition_id"] == str(w["rd"])
    ]
    assert curve_columns
    assert {c["provenance"]["fitted_layer"] for c in curve_columns} == {_EXPECTED[kind]}
