"""API: POST /api/v1/visualization/dataset and GET …/protocols/{id}/run-row-counts."""

from __future__ import annotations

import json
import uuid
from datetime import date

import pytest
import sqlalchemy as sa

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


async def test_wells_carry_the_stored_z_prime_of_their_plates(client, session_factory, fake_auth):
    w = await _seed(session_factory, fake_auth.workspace_id)
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        plate = await uow.session.scalar(
            sa.text("SELECT id FROM plates WHERE run_id = :r"), {"r": w["a"]}
        )
        await uow.session.execute(
            sa.text("UPDATE runs SET qc_metrics = cast(:q as jsonb) WHERE id = :r"),
            {
                "r": w["a"],
                "q": json.dumps(
                    {
                        "z_prime": {str(plate): {"z_prime": 0.712}},
                        "plates": {str(plate): {str(w["rd"]): {"raw": {"z_prime": 0.7}}}},
                    }
                ),
            },
        )
        await uow.commit()

    wells = await client.post(
        URL, json={"source": {"kind": "run", "run_id": str(w["a"])}, "level": "wells"}
    )
    compounds = await client.post(
        URL, json={"source": {"kind": "run", "run_id": str(w["a"])}, "level": "compounds"}
    )

    assert wells.status_code == 200, wells.text
    body = wells.json()
    assert body["values"]["plate_id"] == [str(plate), str(plate)]
    assert body["plate_z_prime"] == {str(plate): 0.712}
    assert body["plate_z_prime_by_column"] == {f"rd:{w['rd']}:raw": {str(plate): 0.7}}
    assert compounds.json()["plate_z_prime"] == {}


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


async def test_control_wells_carry_their_normalized_values_after_a_recompute(
    client, session_factory, fake_auth
):
    """NadD-like plate: DMSO positive controls (high signal) and no-enzyme negative controls
    (low signal) hold no compound. After a recompute their % inhibition is stored beside the
    sample's, so the Wells dataset shows them near 0 % and 100 % with their own spread."""
    ws = fake_auth.workspace_id
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        s = uow.session
        mol = await seed.molecule(s, ws, await seed.org(s, ws), "m1")
        p = await seed.protocol(s, ws)
        rd = await seed.readout_def(
            s, p, name="Signal", unit="AU", normalizations=["percent_inhibition"]
        )
        run = await seed.run(s, ws, p, date(2026, 11, 5))
        plate = await seed.plate(s, run, 1)
        wells = [
            ("sample", 0.3585, mol),
            ("positive_control", 0.64, None),
            ("positive_control", 0.66, None),
            ("negative_control", 0.06, None),
            ("negative_control", 0.074, None),
        ]
        for col, (well_type, value, molecule) in enumerate(wells, start=1):
            w = await seed.well(s, plate, "A", col, well_type=well_type)
            await seed.readout(s, ws, run, rd, molecule, value, well_id=w)  # type: ignore[arg-type]
        await uow.commit()

    recomputed = await client.post(f"/api/v1/runs/{run}/recompute")
    resp = await client.post(
        URL, json={"source": {"kind": "run", "run_id": str(run)}, "level": "wells"}
    )

    assert recomputed.status_code == 200, recomputed.text
    assert resp.status_code == 200, resp.text
    values = resp.json()["values"]
    inhibition = dict(zip(values["well"], values[f"rd:{rd}:percent_inhibition"], strict=True))
    # (0.65 - x) / (0.65 - 0.067): the plate's control means are the anchors.
    assert inhibition == pytest.approx(
        {"A01": 50.0, "A02": 1.715, "A03": -1.715, "A04": 101.2, "A05": 98.8}, abs=0.01
    )


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
    assert len(points) == 3
    assert points[0] == [{"x": 0.001, "y": 50.0}, {"x": 1000.0, "y": 50.0}]


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


async def test_an_at_bound_partial_curve_is_greater_than_the_max_dose(
    client, session_factory, fake_auth
):
    """A partial curve (top 40) never reaches its 50 % target in 0.1-10 µM: the
    workbench reads "> 10 µM" / "pIC50 < 5" at every level, not the stored midpoint."""
    ws = fake_auth.workspace_id
    at_bound = [
        {
            "spec": {"kind": "ic", "level": 50.0, "basis": "relative_percent", "label": None},
            "value": None,
            "ci_low": None,
            "ci_high": None,
            "at_bound": True,
        }
    ]
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        s = uow.session
        m = await seed.molecule(s, ws, await seed.org(s, ws), "m1")
        p = await seed.protocol(s, ws)
        ic50 = await seed.readout_def(s, p, name="IC50", data_type="dose_response", unit="uM")
        run = await seed.run(s, ws, p, date(2026, 11, 12), status="approved")
        await seed.curve(
            s, ws, p, run, m, ic50, fitted_value=1.0, top=40.0, max_dose=10.0,
            curve_class="partial", intercept_values=at_bound, with_well=False,
        )  # fmt: skip
        await uow.commit()
    w = {"p": p}

    for level in ("runs", "batches", "compounds"):
        body = await _level(client, w, level)
        key = f"dr:{ic50}"
        assert body["values"][key] == [10.0], level
        assert body["values"][f"{key}:q"] == [">"], level
        assert body["values"][f"{key}:p"] == [pytest.approx(5.0)], level
        assert body["values"][f"{key}:p:q"] == ["<"], level


async def test_value_columns_name_their_runs(client, session_factory, fake_auth):
    w = await _seed_activity(session_factory, fake_auth.workspace_id)

    body = await _level(client, w, "compounds")

    col = next(c for c in body["columns"] if c["key"] == f"dr:{w['ic50']}")
    assert col["provenance"]["run_ids"] == [str(w["a"]), str(w["b"]), str(w["d"])]


# --- compare: a second protocol joined at the Compounds level ------------------------


async def _seed_compare(session_factory, ws: uuid.UUID) -> dict[str, uuid.UUID]:
    """Protocol "Primary" measures m1 (IC50 0.1 µM) and m2, "Counter" m1 (1 µM) and m3:
    both with a readout named "IC50", each in one completed run."""
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        s = uow.session
        o = await seed.org(s, ws)
        w = {m: await seed.molecule(s, ws, o, m) for m in ("m1", "m2", "m3")}
        measures = {"Primary": (("m1", 0.1), ("m2", 2.0)), "Counter": (("m1", 1.0), ("m3", 5.0))}
        for name, measured in measures.items():
            p = await seed.protocol(s, ws, name=name)
            ic50 = await seed.readout_def(s, p, name="IC50", data_type="dose_response", unit="uM")
            run = await seed.run(s, ws, p, date(2026, 11, 12), status="completed")
            for m, fitted in measured:
                await seed.curve(s, ws, p, run, w[m], ic50, fitted_value=fitted, with_well=False)
            w |= {name: p, f"{name} IC50": ic50, f"{name} run": run}
        await uow.commit()
    return w


def _compared(w, level: str = "compounds", *compare: dict) -> dict:
    return {
        "source": {"kind": "protocol", "protocol_id": str(w["Primary"]), "compare": list(compare)},
        "level": level,
    }


async def test_compounds_compare_a_second_protocol(client, session_factory, fake_auth):
    w = await _seed_compare(session_factory, fake_auth.workspace_id)
    counter = {"protocol_id": str(w["Counter"]), "run_ids": [str(w["Counter run"])]}

    resp = await client.post(URL, json=_compared(w, "compounds", counter))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["row_count"] == 2  # Primary's compounds; m3 was never tested there
    tested = f"tested:{w['Counter']}"
    assert body["values"][tested] == [
        {str(w["m1"]): "Tested", str(w["m2"]): "Not tested"}[m]
        for m in body["values"]["molecule_id"]
    ]
    sel = f"sel:dr:{w['Primary IC50']}:p|dr:{w['Counter IC50']}:p"
    assert _cell(body, sel, w["m1"]) == [pytest.approx(1.0)]  # pIC50 7 - 6
    assert _cell(body, sel, w["m2"]) == [None]
    assert [(p["protocol_id"], p["name"]) for p in body["protocols"]] == [
        (str(w["Primary"]), "Primary"),
        (str(w["Counter"]), "Counter"),
    ]
    labels = {c["key"]: c["label"] for c in body["columns"]}
    assert labels[f"dr:{w['Primary IC50']}"].startswith("Primary · ")
    assert labels[f"dr:{w['Counter IC50']}"].startswith("Counter · ")


async def test_without_compare_the_dataset_names_its_one_protocol(
    client, session_factory, fake_auth
):
    w = await _seed_compare(session_factory, fake_auth.workspace_id)

    body = (await client.post(URL, json=_compared(w))).json()

    assert [p["name"] for p in body["protocols"]] == ["Primary"]
    assert not any(k.startswith("tested:") or k.startswith("sel:") for k in body["values"])
    assert body["row_count"] == 2


@pytest.mark.parametrize(
    ("level", "repeat"), [("wells", False), ("runs", False), ("compounds", True)]
)
async def test_compare_is_refused_off_compounds_or_for_a_repeated_protocol(
    client, session_factory, fake_auth, level, repeat
):
    w = await _seed_compare(session_factory, fake_auth.workspace_id)
    compare = [{"protocol_id": str(w["Primary" if repeat else "Counter"])}]

    resp = await client.post(URL, json=_compared(w, level, *compare))

    assert resp.status_code == 422, resp.text


async def test_a_compared_protocol_of_another_workspace_is_404(client, session_factory, fake_auth):
    w = await _seed_compare(session_factory, fake_auth.workspace_id)
    other = await _seed_compare(session_factory, uuid.uuid4())

    resp = await client.post(
        URL, json=_compared(w, "compounds", {"protocol_id": str(other["Counter"])})
    )

    assert resp.status_code == 404, resp.text


async def test_at_most_four_protocols_are_compared(client, session_factory, fake_auth):
    w = await _seed_compare(session_factory, fake_auth.workspace_id)
    five = [{"protocol_id": str(uuid.uuid4())} for _ in range(5)]

    resp = await client.post(URL, json=_compared(w, "compounds", *five))

    assert resp.status_code == 422, resp.text


async def test_aggregated_levels_read_a_compounds_sample_wells_and_wells_show_every_well(
    client, session_factory, fake_auth
):
    """Rifampicin titrated on sample wells and used as the positive control on the same
    plate. After a recompute every well has its % inhibition at Wells; the Runs, Batches and
    Compounds rows of rifampicin read its two sample wells only (mean 40, not 20)."""
    ws = fake_auth.workspace_id
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        s = uow.session
        rif = await seed.molecule(s, ws, await seed.org(s, ws), "rifampicin")
        p = await seed.protocol(s, ws)
        rd = await seed.readout_def(
            s, p, name="Signal", unit="AU", normalizations=["percent_inhibition"]
        )
        run = await seed.run(s, ws, p, date(2026, 11, 5), status="completed")
        plate = await seed.plate(s, run, 1)
        wells = [
            ("sample", 0.3585, rif),  # 50 %
            ("sample", 0.4751, rif),  # 30 %
            ("positive_control", 0.64, rif),
            ("positive_control", 0.66, rif),
            ("negative_control", 0.06, None),
            ("negative_control", 0.074, None),
        ]
        for col, (well_type, value, molecule) in enumerate(wells, start=1):
            w = await seed.well(s, plate, "A", col, well_type=well_type)
            await seed.readout(s, ws, run, rd, molecule, value, well_id=w)  # type: ignore[arg-type]
        await uow.commit()
    recomputed = await client.post(f"/api/v1/runs/{run}/recompute")
    assert recomputed.status_code == 200, recomputed.text
    async with session_factory() as s:  # approved once computed: a recompute is refused after
        await s.execute(sa.text("UPDATE runs SET status = 'approved' WHERE id = :r"), {"r": run})
        await s.commit()
    key, source = f"rd:{rd}:percent_inhibition", {"kind": "protocol", "protocol_id": str(p)}

    wells_body = await _level(client, {}, "wells", **source)
    assert sum(v is not None for v in wells_body["values"][key]) == 6
    for level in ("runs", "batches", "compounds"):
        body = await _level(client, {}, level, **source)
        assert _cell(body, key, rif) == [pytest.approx(40.0, abs=0.01)], level
        assert _cell(body, f"{key}:n", rif) == [2], level
