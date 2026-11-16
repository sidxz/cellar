"""API: POST /api/v1/visualization/dataset and GET …/protocols/{id}/run-row-counts."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.integration import _screening_seed as seed

pytestmark = pytest.mark.asyncio

URL = "/api/v1/visualization/dataset"


async def _seed(session_factory, ws: uuid.UUID) -> dict[str, uuid.UUID]:
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        s = uow.session
        o = await seed.org(s, ws)
        mol = await seed.molecule(s, ws, o, "m1")
        p = await seed.protocol(s, ws)
        rd = await seed.readout_def(s, p, name="Signal", unit="AU")
        run_a = await seed.run(s, ws, p, date(2026, 11, 5), status="approved")
        run_b = await seed.run(s, ws, p, date(2026, 11, 12), status="approved")
        for run in (run_a, run_b):
            plate = await seed.plate(s, run, 1)
            for col in (1, 2):
                w = await seed.well(s, plate, "A", col)
                await seed.readout(s, ws, run, rd, mol, 0.1 * col, well_id=w)
        await uow.commit()
    return {"p": p, "rd": rd, "a": run_a, "b": run_b}


async def test_dataset_for_a_run(client, session_factory, fake_auth):
    w = await _seed(session_factory, fake_auth.workspace_id)

    resp = await client.post(
        URL, json={"source": {"kind": "run", "run_id": str(w["a"])}, "level": "wells"}
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["level"] == "wells" and body["row_count"] == 2 and len(body["row_ids"]) == 2
    keys = {c["key"] for c in body["columns"]}
    assert {"well_order", "compound", "plate", f"rd:{w['rd']}:raw"} <= keys
    assert body["values"]["well_order"] == [1, 2]
    assert body["values"][f"rd:{w['rd']}:raw"] == [0.1, 0.2]
    for key in ("run", "plate", "compound", "well"):
        for v in body["values"][key]:
            with pytest.raises(ValueError):
                uuid.UUID(str(v))


async def test_dataset_for_a_protocol_run_subset(client, session_factory, fake_auth):
    w = await _seed(session_factory, fake_auth.workspace_id)

    resp = await client.post(
        URL,
        json={
            "source": {"kind": "protocol", "protocol_id": str(w["p"]), "run_ids": [str(w["b"])]},
            "level": "wells",
        },
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["values"]["run"] == ["2026-11-12", "2026-11-12"]


async def test_other_workspace_gets_404(client, session_factory, fake_auth):
    w = await _seed(session_factory, uuid.uuid4())  # data lives in another workspace

    run = await client.post(
        URL, json={"source": {"kind": "run", "run_id": str(w["a"])}, "level": "wells"}
    )
    proto = await client.post(
        URL, json={"source": {"kind": "protocol", "protocol_id": str(w["p"])}, "level": "wells"}
    )
    counts = await client.get(f"/api/v1/visualization/protocols/{w['p']}/run-row-counts")

    assert (run.status_code, proto.status_code, counts.status_code) == (404, 404, 404)


async def test_over_the_cap_is_422_with_the_count(client, session_factory, fake_auth, monkeypatch):
    from cellar.application.visualization import get_dataset

    monkeypatch.setattr(get_dataset, "MAX_DATASET_ROWS", 3)
    w = await _seed(session_factory, fake_auth.workspace_id)

    resp = await client.post(
        URL, json={"source": {"kind": "protocol", "protocol_id": str(w["p"])}, "level": "wells"}
    )

    assert resp.status_code == 422, resp.text
    assert "4 rows" in resp.text and "limit is 3" in resp.text


async def test_run_row_counts(client, session_factory, fake_auth):
    w = await _seed(session_factory, fake_auth.workspace_id)

    resp = await client.get(f"/api/v1/visualization/protocols/{w['p']}/run-row-counts")

    assert resp.status_code == 200, resp.text
    assert resp.json()["counts"] == {str(w["a"]): 2, str(w["b"]): 2}


async def test_unknown_level_is_rejected(client, session_factory, fake_auth):
    w = await _seed(session_factory, fake_auth.workspace_id)
    resp = await client.post(
        URL, json={"source": {"kind": "run", "run_id": str(w["a"])}, "level": "planets"}
    )
    assert resp.status_code == 422
