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


async def test_dataset_is_gzipped_for_a_client_that_accepts_it(client, session_factory, fake_auth):
    w = await _seed(session_factory, fake_auth.workspace_id)

    resp = await client.post(
        URL,
        json={"source": {"kind": "protocol", "protocol_id": str(w["p"])}, "level": "wells"},
        headers={"Accept-Encoding": "gzip"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-encoding"] == "gzip"
    assert resp.json()["row_count"] == 4


@pytest.mark.parametrize("level", ["wells", "runs", "batches", "compounds"])
async def test_other_workspace_gets_404(client, session_factory, fake_auth, level):
    w = await _seed(session_factory, uuid.uuid4())  # data lives in another workspace

    run = await client.post(
        URL, json={"source": {"kind": "run", "run_id": str(w["a"])}, "level": level}
    )
    proto = await client.post(
        URL, json={"source": {"kind": "protocol", "protocol_id": str(w["p"])}, "level": level}
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


# --- aggregated levels: Runs / Batches / Compounds ----------------------------------


async def _seed_activity(session_factory, ws: uuid.UUID) -> dict[str, uuid.UUID]:
    """m1: % inhibition 40 / 60 and IC50 curves 0.1 / 1.0 in two approved runs, plus
    1000 and a 100 curve in a draft run. m2: one curve, no readout values."""
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        s = uow.session
        o = await seed.org(s, ws)
        m1 = await seed.molecule(s, ws, o, "m1")
        m2 = await seed.molecule(s, ws, o, "m2")
        p = await seed.protocol(s, ws)
        sig = await seed.readout_def(
            s, p, name="Signal", unit="RFU", normalizations=["percent_inhibition"]
        )
        ic50 = await seed.readout_def(s, p, name="IC50", data_type="dose_response", unit="uM")
        a = await seed.run(s, ws, p, date(2026, 11, 5), status="approved")
        b = await seed.run(s, ws, p, date(2026, 11, 12), status="approved")
        d = await seed.run(s, ws, p, date(2026, 11, 20), status="draft")
        for run, value, fitted in ((a, 40.0, 0.1), (b, 60.0, 1.0), (d, 1000.0, 100.0)):
            await seed.readout(s, ws, run, sig, m1, value, normalization="percent_inhibition")
            await seed.readout(s, ws, run, sig, m1, value * 10)  # raw layer
            await seed.curve(s, ws, p, run, m1, ic50, fitted_value=fitted, with_well=False)
        await seed.curve(s, ws, p, a, m2, ic50, fitted_value=2.0, with_well=False)
        await uow.commit()
    return {"p": p, "sig": sig, "ic50": ic50, "a": a, "b": b, "d": d, "m1": m1, "m2": m2}


async def _level(client, w, level: str, **source) -> dict:
    resp = await client.post(
        URL,
        json={
            "source": source or {"kind": "protocol", "protocol_id": str(w["p"])},
            "level": level,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["level"] == level
    return body


async def _activity(client, protocol_id: uuid.UUID) -> dict:
    resp = await client.get(f"/api/v1/protocols/{protocol_id}/activity-summary")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _cell(body: dict, key: str, molecule_id: uuid.UUID) -> list:
    """The column's values on the rows of one compound."""
    ids = body["values"]["molecule_id"]
    return [v for v, m in zip(body["values"][key], ids, strict=True) if m == str(molecule_id)]


async def test_compounds_match_the_activity_tab(client, session_factory, fake_auth):
    w = await _seed_activity(session_factory, fake_auth.workspace_id)

    body = await _level(client, w, "compounds")
    activity = await _activity(client, w["p"])

    m1 = next(i for i in activity["items"] if i["molecule_id"] == str(w["m1"]))
    sig, dr = f"rd:{w['sig']}:percent_inhibition", f"dr:{w['ic50']}"
    assert _cell(body, sig, w["m1"]) == [pytest.approx(m1["readouts"]["Signal"]["mean"])]
    assert _cell(body, dr, w["m1"]) == [pytest.approx(m1["readouts"]["IC50"]["mean"], abs=1e-6)]
    assert _cell(body, sig, w["m1"]) == [pytest.approx(50.0)]  # the draft's 1000 is not in it
    # A compound with a curve and no readout values is still a row.
    assert _cell(body, dr, w["m2"]) == [pytest.approx(2.0)]
    assert _cell(body, sig, w["m2"]) == [None]
    col = next(c for c in body["columns"] if c["key"] == dr)
    assert col["provenance"]["aggregation"] == "geomean"


async def test_batches_leave_out_a_draft_run_and_runs_show_it(client, session_factory, fake_auth):
    w = await _seed_activity(session_factory, fake_auth.workspace_id)
    sig = f"rd:{w['sig']}:percent_inhibition"

    batches = await _level(client, w, "batches")
    runs = await _level(client, w, "runs")

    assert 1000.0 not in batches["values"][sig]
    statuses_values = zip(
        _cell(runs, "run_status", w["m1"]), _cell(runs, sig, w["m1"]), strict=True
    )
    assert ("draft", 1000.0) in set(statuses_values)
    # One row per (compound, batch, run): m1's readouts and curves carry different batches.
    assert len(set(runs["row_ids"])) == runs["row_count"]
    assert all(r.split(":")[0] in {str(w["a"]), str(w["b"]), str(w["d"])} for r in runs["row_ids"])
    points = [p for p in _cell(runs, f"dr:{w['ic50']}:points", w["m1"]) if p is not None]
    assert len(points) == 3 and points[0] == [{"x": 1.0, "y": 50.0}]


async def test_a_run_source_aggregates_that_run(client, session_factory, fake_auth):
    w = await _seed_activity(session_factory, fake_auth.workspace_id)

    body = await _level(client, w, "compounds", kind="run", run_id=str(w["b"]))

    assert _cell(body, f"rd:{w['sig']}:percent_inhibition", w["m1"]) == [60.0]
    assert _cell(body, f"dr:{w['ic50']}", w["m2"]) == []


async def _seed_aggregation(session_factory, ws, aggregation: str, values) -> dict[str, uuid.UUID]:
    """One compound, one approved run, a potency readout (uM) with ``aggregation``."""
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        s = uow.session
        m = await seed.molecule(s, ws, await seed.org(s, ws), "m1")
        p = await seed.protocol(s, ws)
        rd = await seed.readout_def(s, p, name="Potency", unit="uM", aggregation=aggregation)
        run = await seed.run(s, ws, p, date(2026, 11, 12), status="approved")
        for v in values:
            await seed.readout(s, ws, run, rd, m, v)
        await uow.commit()
    return {"p": p, "rd": rd, "m": m}


@pytest.mark.parametrize(
    ("aggregation", "values", "workbench", "activity"),
    [
        ("geometric_mean", [1.0, 10.0, 100.0], 10.0, 37.0),
        ("median", [1.0, 2.0, 100.0], 2.0, 34.3333),
    ],
)
async def test_compounds_honour_the_readouts_aggregation_and_activity_keeps_the_mean(
    client, session_factory, fake_auth, aggregation, values, workbench, activity
):
    w = await _seed_aggregation(session_factory, fake_auth.workspace_id, aggregation, values)

    body = await _level(client, w, "compounds")
    summary = await _activity(client, w["p"])

    key = f"rd:{w['rd']}:raw"
    assert body["values"][key] == [pytest.approx(workbench)]
    col = next(c for c in body["columns"] if c["key"] == key)
    assert col["provenance"]["aggregation"] == {"geometric_mean": "geomean"}.get(
        aggregation, aggregation
    )
    assert summary["items"][0]["readouts"]["Potency"]["mean"] == activity
