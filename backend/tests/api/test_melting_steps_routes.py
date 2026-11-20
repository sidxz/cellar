"""API tests: a run's melting analysis, adding, reviewing and accepting melting steps, and
reading the candidate peaks of a position.

The synthetic run has a reference position whose steps sit at 36.6 and 71.3 °C and a
sample whose ligand merged them into one at 64.0 °C, read in two temperature windows,
Lower (25 to 50) and Main (50 to 85).
"""

from __future__ import annotations

import json
import math
import random
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.api.conftest import _create_test_app
from tests.api.test_instrument_import_routes import Seeded, _seed, labelling_from
from tests.fakes.fake_auth import FakeAuth
from tests.helpers.instrument_workbook import build_raw_workbook, temperature

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
POINTS = 1060  # they reach 85.4 °C, so both windows lie inside every trace


def _melt_file(cells: dict[tuple[str, int, int, str], object] | None = None) -> dict[str, Any]:
    return {
        "file": (
            "melt.xlsx",
            build_raw_workbook(
                positions={1: "protein alone", 2: "ABC-0000001 (Old)"},
                points=POINTS,
                reported={
                    "Onset #1 for Ratio ": {1: 33.0, 2: 60.0},
                    "Inflection Point #1 for Ratio ": {1: 36.6, 2: 64.0},
                    "Inflection Point #2 for Ratio ": {1: 71.3},
                },
                cells=cells,
            ),
            XLSX,
        )
    }


MELT_FILE = _melt_file()


async def _sql(session_factory: async_sessionmaker[AsyncSession], stmt: str, **params: Any) -> Any:
    async with session_factory() as session:
        result = await session.execute(sa.text(stmt), params)
        await session.commit()
        return result


async def _analysis(client: AsyncClient, run_id: uuid.UUID) -> dict[str, Any]:
    resp = await client.get(f"/api/v1/runs/{run_id}/melting-analysis")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _setup(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    ws: uuid.UUID,
    main_extra: dict[str, Any] | None = None,
    files: dict[str, Any] = MELT_FILE,
) -> tuple[Seeded, dict[str, Any]]:
    """Seed, add the two windows through the protocol route, import the melt file."""
    s = await _seed(session_factory, ws)
    protocol_id = (
        await _sql(session_factory, "SELECT protocol_id FROM runs WHERE id = :id", id=s.run_id)
    ).scalar_one()
    for name, low, high in (("Main", 50.0, 85.0), ("Lower", 25.0, 50.0)):
        resp = await client.post(
            f"/api/v1/protocols/{protocol_id}/temperature-windows",
            json={
                "window": name,
                "channel_key": "ratio",
                "low": low,
                "high": high,
                "measures": ["tm", "delta_tm"],
            }
            | (main_extra or {} if name == "Main" else {}),
        )
        assert resp.status_code == 201, resp.text

    preview = (await client.post(s.preview_url, files=files)).json()
    resp = await client.post(
        s.import_url, files=files, data={"labelling": json.dumps(labelling_from(preview))}
    )
    assert resp.status_code == 201, resp.text
    return s, await _analysis(client, s.run_id)


def _step(analysis: dict[str, Any], value: float) -> dict[str, Any]:
    return next(st for st in analysis["steps"] if st["value"] == value)


def _window(analysis: dict[str, Any], name: str) -> dict[str, Any]:
    return next(w for w in analysis["windows"] if w["window"] == name)


def _position(window: dict[str, Any], well_id: str) -> dict[str, Any]:
    return next(p for p in window["positions"] if p["well_id"] == well_id)


async def _rows(
    session_factory: async_sessionmaker[AsyncSession], well_id: str, readout_id: str
) -> list[float]:
    result = await _sql(
        session_factory,
        "SELECT value_numeric FROM readout_data "
        "WHERE well_id = :w AND readout_definition_id = :rd AND is_computed = true",
        w=uuid.UUID(well_id),
        rd=uuid.UUID(readout_id),
    )
    return [row[0] for row in result]


async def test_analysis_after_import_lists_steps_and_window_results(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, analysis = await _setup(client, session_factory, fake_auth.workspace_id)
    assert analysis["run_id"] == str(s.run_id)
    assert analysis["edit_refusal"] is None
    assert sorted(st["value"] for st in analysis["steps"]) == [36.6, 64.0, 71.3]
    sample = _step(analysis, 64.0)
    assert sample | {"id": None, "well_id": None} == {
        "id": None,
        "well_id": None,
        "channel_key": "ratio",
        "source": "instrument",
        "value": 64.0,
        "instrument_value": 64.0,
        "instrument_label": sample["instrument_label"],
        "status": "unreviewed",
        "reason": None,
        "changed_by": None,
        "changed_at": None,
        "assigned_window": None,
        "assignment_reason": None,
        "assigned_by": None,
        "assigned_at": None,
        "version": 1,
    }
    assert sample["instrument_label"]
    reference_well = _step(analysis, 36.6)["well_id"]

    assert [w["window"] for w in analysis["windows"]] == ["Lower", "Main"]
    main = _window(analysis, "Main")
    assert (main["channel_key"], main["low"], main["high"]) == ("ratio", 50.0, 85.0)
    assert main["tm_readout_id"] and main["delta_tm_readout_id"]
    assert (main["reference_tm"], main["reference_count"], main["flags"]) == (71.3, 1, [])
    in_main = _position(main, sample["well_id"])
    assert in_main["tm"] == 64.0
    assert in_main["delta_tm"] == pytest.approx(-7.3)
    assert _position(main, reference_well)["delta_tm"] is None
    lower = _window(analysis, "Lower")
    assert _position(lower, sample["well_id"]) == {
        "well_id": sample["well_id"],
        "tm": None,
        "delta_tm": None,
        "flags": ["no_step_in_window"],
        "named_by": None,
        "step_id": None,
    }
    assert analysis["step_checks"] == [
        {"channel_key": "ratio", "differs": [sample["well_id"]], "references_differ": False}
    ]
    assert await _rows(session_factory, sample["well_id"], main["delta_tm_readout_id"]) == [
        pytest.approx(-7.3)
    ]


async def test_reject_removes_window_rows_and_keeps_the_step(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    _, analysis = await _setup(client, session_factory, fake_auth.workspace_id)
    sample, main = _step(analysis, 64.0), _window(analysis, "Main")
    assert len(await _rows(session_factory, sample["well_id"], main["tm_readout_id"])) == 1

    resp = await client.patch(
        f"/api/v1/melting-steps/{sample['id']}",
        json={"expected_version": 1, "status": "rejected", "value": 64.0, "reason": "bubble"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["recalculated"], body["compute_warning"]) == (True, None)
    assert (body["step"]["status"], body["step"]["version"]) == ("rejected", 2)

    assert await _rows(session_factory, sample["well_id"], main["delta_tm_readout_id"]) == []
    assert await _rows(session_factory, sample["well_id"], main["tm_readout_id"]) == []
    kept = _step(await _analysis(client, analysis["run_id"]), 64.0)
    assert (kept["status"], kept["reason"], kept["instrument_value"]) == (
        "rejected",
        "bubble",
        64.0,
    )
    assert kept["changed_by"] == str(fake_auth.user_id)


async def test_correct_value_updates_delta_row(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    _, analysis = await _setup(client, session_factory, fake_auth.workspace_id)
    sample, main = _step(analysis, 64.0), _window(analysis, "Main")

    resp = await client.patch(
        f"/api/v1/melting-steps/{sample['id']}",
        json={"expected_version": 1, "status": "accepted", "value": 65.0, "reason": "re-read"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["step"]["value"] == 65.0
    assert await _rows(session_factory, sample["well_id"], main["delta_tm_readout_id"]) == [
        pytest.approx(-6.3)
    ]


async def test_add_manual_step_returns_201(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, analysis = await _setup(client, session_factory, fake_auth.workspace_id)
    sample_well = _step(analysis, 64.0)["well_id"]

    resp = await client.post(
        f"/api/v1/runs/{s.run_id}/melting-steps",
        json={"well_id": sample_well, "channel_key": "ratio", "value": 40.0},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["recalculated"] is True
    assert body["step"]["source"] == "manual"
    assert body["step"]["status"] == "accepted"
    assert (body["step"]["instrument_value"], body["step"]["instrument_label"]) == (None, None)

    lower = _window(await _analysis(client, s.run_id), "Lower")
    assert _position(lower, sample_well)["delta_tm"] == pytest.approx(3.4)
    assert await _rows(session_factory, sample_well, lower["delta_tm_readout_id"]) == [
        pytest.approx(3.4)
    ]


async def test_stale_review_returns_409_and_writes_nothing(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    _, analysis = await _setup(client, session_factory, fake_auth.workspace_id)
    sample = _step(analysis, 64.0)
    url = f"/api/v1/melting-steps/{sample['id']}"
    first = await client.patch(
        url, json={"expected_version": 1, "status": "accepted", "value": 64.0}
    )
    assert first.status_code == 200, first.text

    stale = await client.patch(
        url,
        json={"expected_version": 1, "status": "rejected", "value": 64.0, "reason": "late"},
    )
    assert stale.status_code == 409, stale.text
    now = _step(await _analysis(client, analysis["run_id"]), 64.0)
    assert (now["status"], now["reason"], now["version"]) == ("accepted", None, 2)
    audited = await _sql(
        session_factory,
        "SELECT count(*) FROM audit_operations WHERE entity_id = :id",
        id=uuid.UUID(sample["id"]),
    )
    assert audited.scalar_one() == 1


async def test_completed_run_allows_step_changes(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, analysis = await _setup(client, session_factory, fake_auth.workspace_id)
    sample = _step(analysis, 64.0)
    await _sql(session_factory, "UPDATE runs SET status = 'completed' WHERE id = :id", id=s.run_id)

    review = await client.patch(
        f"/api/v1/melting-steps/{sample['id']}",
        json={"expected_version": 1, "status": "accepted", "value": 64.0},
    )
    assert review.status_code == 200, review.text
    add = await client.post(
        f"/api/v1/runs/{s.run_id}/melting-steps",
        json={"well_id": sample["well_id"], "channel_key": "ratio", "value": 40.0},
    )
    assert add.status_code == 201, add.text
    assert review.json()["recalculated"] and add.json()["recalculated"]
    after = await _analysis(client, s.run_id)
    assert after["edit_refusal"] is None
    assert len(after["steps"]) == 4 and _step(after, 64.0)["status"] == "accepted"


async def test_approved_run_returns_409(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, analysis = await _setup(client, session_factory, fake_auth.workspace_id)
    sample = _step(analysis, 64.0)
    await _sql(session_factory, "UPDATE runs SET status = 'approved' WHERE id = :id", id=s.run_id)

    review = await client.patch(
        f"/api/v1/melting-steps/{sample['id']}",
        json={"expected_version": 1, "status": "accepted", "value": 64.0},
    )
    add = await client.post(
        f"/api/v1/runs/{s.run_id}/melting-steps",
        json={"well_id": sample["well_id"], "channel_key": "ratio", "value": 40.0},
    )
    for resp in (review, add):
        assert resp.status_code == 409, resp.text
    after = await _analysis(client, s.run_id)
    assert after["edit_refusal"] is not None
    assert [(st["status"], st["version"]) for st in after["steps"]] == [("unreviewed", 1)] * 3


async def test_manual_value_outside_trace_returns_422(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, analysis = await _setup(client, session_factory, fake_auth.workspace_id)
    resp = await client.post(
        f"/api/v1/runs/{s.run_id}/melting-steps",
        json={"well_id": _step(analysis, 64.0)["well_id"], "channel_key": "ratio", "value": 90.0},
    )
    assert resp.status_code == 422, resp.text
    assert len((await _analysis(client, s.run_id))["steps"]) == 3


async def test_reject_without_reason_returns_422(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    _, analysis = await _setup(client, session_factory, fake_auth.workspace_id)
    sample = _step(analysis, 64.0)
    resp = await client.patch(
        f"/api/v1/melting-steps/{sample['id']}",
        json={"expected_version": 1, "status": "rejected", "value": 64.0},
    )
    assert resp.status_code == 422, resp.text
    assert _step(await _analysis(client, analysis["run_id"]), 64.0)["status"] == "unreviewed"


async def test_viewer_can_read_but_not_write(
    client: AsyncClient,
    viewer_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, analysis = await _setup(client, session_factory, fake_auth.workspace_id)
    sample = _step(analysis, 64.0)

    assert (
        await viewer_client.get(f"/api/v1/runs/{s.run_id}/melting-analysis")
    ).status_code == 200
    add = await viewer_client.post(
        f"/api/v1/runs/{s.run_id}/melting-steps",
        json={"well_id": sample["well_id"], "channel_key": "ratio", "value": 40.0},
    )
    review = await viewer_client.patch(
        f"/api/v1/melting-steps/{sample['id']}",
        json={"expected_version": 1, "status": "accepted", "value": 64.0},
    )
    assert (add.status_code, review.status_code) == (403, 403)


@asynccontextmanager
async def _client_as(database_url: str, auth: FakeAuth) -> AsyncIterator[AsyncClient]:
    app = _create_test_app(database_url, auth)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:  # type: ignore[arg-type]
        yield ac
    await app.state.container[AsyncEngine].dispose()


async def test_other_workspace_step_returns_404(
    client: AsyncClient,
    database_url: str,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, analysis = await _setup(client, session_factory, fake_auth.workspace_id)
    sample = _step(analysis, 64.0)
    stranger = FakeAuth(role="admin", workspace_id=uuid.uuid4(), user_id=uuid.uuid4())
    async with _client_as(database_url, stranger) as other:
        read = await other.get(f"/api/v1/runs/{s.run_id}/melting-analysis")
        review = await other.patch(
            f"/api/v1/melting-steps/{sample['id']}",
            json={"expected_version": 1, "status": "accepted", "value": 64.0},
        )
        add = await other.post(
            f"/api/v1/runs/{s.run_id}/melting-steps",
            json={"well_id": sample["well_id"], "channel_key": "ratio", "value": 40.0},
        )
    assert (read.status_code, review.status_code, add.status_code) == (404, 404, 404)
    assert _step(await _analysis(client, s.run_id), 64.0)["version"] == 1


async def test_analysis_lists_series_values_with_their_qualifier(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    extra = {
        "measures": ["tm", "delta_tm", "max_delta_tm", "lowest_shift_concentration"],
        "lowest_shift_threshold": 8.0,
    }
    s, analysis = await _setup(client, session_factory, fake_auth.workspace_id, main_extra=extra)
    series = {x["readout_name"]: x for x in _window(analysis, "Main")["series"]}
    assert _window(analysis, "Lower")["series"] == []

    [mx] = series["Max ΔTm (Main)"]["values"]
    assert (mx["batch_id"], mx["qualifier"], mx["concentration"]) == (str(s.batch_id), "=", 10.0)
    assert mx["value"] == pytest.approx(-7.3)
    low = series["Lowest shifting conc. (Main, ±8 °C)"]
    assert (low["measure"], low["threshold"], low["concentration"]) == (
        "lowest_shift_concentration",
        8.0,
        None,
    )
    assert [(v["value"], v["qualifier"]) for v in low["values"]] == [(10.0, ">")]

    stored = await _sql(
        session_factory,
        "SELECT well_id, batch_id, value_numeric FROM readout_data "
        "WHERE readout_definition_id = :rd AND is_computed = true",
        rd=uuid.UUID(series["Max ΔTm (Main)"]["readout_id"]),
    )
    [(well_id, batch_id, value)] = list(stored)
    assert (well_id, batch_id) == (None, s.batch_id) and value == pytest.approx(-7.3)


async def _assign(
    client: AsyncClient, step: dict[str, Any], window: str | None, **extra: Any
) -> Any:
    return await client.put(
        f"/api/v1/melting-steps/{step['id']}/assignment",
        json={"expected_version": step["version"], "window": window} | extra,
    )


def _named(analysis: dict[str, Any], window: str, well_id: str) -> tuple[Any, Any, Any]:
    p = _position(_window(analysis, window), well_id)
    return (p["tm"], p["named_by"], p["step_id"])


async def test_assign_and_clear(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, analysis = await _setup(client, session_factory, fake_auth.workspace_id)
    sample, well = _step(analysis, 64.0), _step(analysis, 64.0)["well_id"]
    main, lower = _window(analysis, "Main"), _window(analysis, "Lower")

    resp = await _assign(client, sample, "Lower", reason="merged peak")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["recalculated"], body["compute_warning"]) == (True, None)
    assigned = body["step"]
    assert (assigned["assigned_window"], assigned["assignment_reason"]) == ("Lower", "merged peak")
    assert assigned["assigned_by"] == str(fake_auth.user_id) and assigned["assigned_at"]
    # Assigning is a judgment on the peak: it is accepted. The review's own reason is untouched.
    assert (assigned["status"], assigned["reason"], assigned["version"]) == ("accepted", None, 2)

    after = await _analysis(client, s.run_id)
    assert _named(after, "Lower", well) == (64.0, "assignment", sample["id"])
    assert _position(_window(after, "Lower"), well)["delta_tm"] == pytest.approx(27.4)
    assert _named(after, "Main", well) == (None, None, None)
    assert await _rows(session_factory, well, lower["delta_tm_readout_id"]) == [
        pytest.approx(27.4)
    ]
    assert await _rows(session_factory, well, main["tm_readout_id"]) == []

    resp = await _assign(client, assigned, None)
    assert resp.status_code == 200, resp.text
    cleared = resp.json()["step"]
    assert [
        cleared[k] for k in ("assigned_window", "assignment_reason", "assigned_by", "assigned_at")
    ] == [None] * 4
    assert (cleared["status"], cleared["version"]) == ("accepted", 3)

    after = await _analysis(client, s.run_id)
    assert _named(after, "Main", well) == (64.0, "range", sample["id"])
    assert _named(after, "Lower", well) == (None, None, None)
    assert await _rows(session_factory, well, main["delta_tm_readout_id"]) == [pytest.approx(-7.3)]
    assert await _rows(session_factory, well, lower["tm_readout_id"]) == []


async def test_assign_on_completed_run_ok(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, analysis = await _setup(client, session_factory, fake_auth.workspace_id)
    sample = _step(analysis, 64.0)
    await _sql(session_factory, "UPDATE runs SET status = 'completed' WHERE id = :id", id=s.run_id)

    resp = await _assign(client, sample, "Lower")
    assert resp.status_code == 200, resp.text
    assert resp.json()["recalculated"] is True
    after = await _analysis(client, s.run_id)
    assert _named(after, "Lower", sample["well_id"]) == (64.0, "assignment", sample["id"])


async def _assign_refused(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    ws: uuid.UUID,
    state: str,
) -> None:
    s, analysis = await _setup(client, session_factory, ws)
    sample = _step(analysis, 64.0)
    await _sql(session_factory, f"UPDATE runs SET {state} WHERE id = :id", id=s.run_id)

    resp = await _assign(client, sample, "Lower")
    assert resp.status_code == 409, resp.text
    after = await _analysis(client, s.run_id)
    assert after["edit_refusal"] is not None
    assert (_step(after, 64.0)["assigned_window"], _step(after, 64.0)["version"]) == (None, 1)


async def test_assign_on_approved_run_409(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    await _assign_refused(client, session_factory, fake_auth.workspace_id, "status = 'approved'")


async def test_assign_on_locked_run_409(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    await _assign_refused(
        client,
        session_factory,
        fake_auth.workspace_id,
        "status = 'completed', is_locked = true",
    )


async def test_assign_unknown_window_422(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, analysis = await _setup(client, session_factory, fake_auth.workspace_id)
    sample = _step(analysis, 64.0)

    resp = await _assign(client, sample, "Upper")
    assert resp.status_code == 422, resp.text
    too_long = await _assign(client, sample, "Lower", reason="x" * 501)
    assert too_long.status_code == 422, too_long.text
    assert _step(await _analysis(client, s.run_id), 64.0)["version"] == 1


async def test_assign_stale_version_409(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, analysis = await _setup(client, session_factory, fake_auth.workspace_id)
    sample = _step(analysis, 64.0)
    assert (await _assign(client, sample, "Lower")).status_code == 200

    stale = await _assign(client, sample, None)  # still carries version 1
    assert stale.status_code == 409, stale.text
    now = _step(await _analysis(client, s.run_id), 64.0)
    assert (now["assigned_window"], now["version"]) == ("Lower", 2)


async def test_assign_viewer_403(
    client: AsyncClient,
    viewer_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, analysis = await _setup(client, session_factory, fake_auth.workspace_id)
    sample = _step(analysis, 64.0)

    resp = await _assign(viewer_client, sample, "Lower")
    assert resp.status_code == 403, resp.text
    assert _step(await _analysis(client, s.run_id), 64.0)["assigned_window"] is None


async def test_assign_other_workspace_404(
    client: AsyncClient,
    database_url: str,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, analysis = await _setup(client, session_factory, fake_auth.workspace_id)
    sample = _step(analysis, 64.0)
    stranger = FakeAuth(role="admin", workspace_id=uuid.uuid4(), user_id=uuid.uuid4())
    async with _client_as(database_url, stranger) as other:
        resp = await _assign(other, sample, "Lower")
    assert resp.status_code == 404, resp.text
    missing = await _assign(client, sample | {"id": str(uuid.uuid4())}, "Lower")
    assert missing.status_code == 404, missing.text
    assert _step(await _analysis(client, s.run_id), 64.0)["version"] == 1


async def test_add_with_assigned_window(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, analysis = await _setup(client, session_factory, fake_auth.workspace_id)
    well, main = _step(analysis, 64.0)["well_id"], _window(analysis, "Main")

    resp = await client.post(
        f"/api/v1/runs/{s.run_id}/melting-steps",
        json={
            "well_id": well,
            "channel_key": "ratio",
            "value": 40.0,
            "reason": "shoulder",
            "assigned_window": "Main",
        },
    )
    assert resp.status_code == 201, resp.text
    added = resp.json()["step"]
    # The form's one reason serves the peak and its assignment.
    assert (added["reason"], added["assigned_window"], added["assignment_reason"]) == (
        "shoulder",
        "Main",
        "shoulder",
    )
    assert added["assigned_by"] == str(fake_auth.user_id) and added["assigned_at"]

    after = await _analysis(client, s.run_id)
    assert _named(after, "Main", well) == (40.0, "assignment", added["id"])
    assert _named(after, "Lower", well) == (None, None, None)
    assert await _rows(session_factory, well, main["delta_tm_readout_id"]) == [
        pytest.approx(-31.3)
    ]

    unknown = await client.post(
        f"/api/v1/runs/{s.run_id}/melting-steps",
        json={"well_id": well, "channel_key": "ratio", "value": 41.0, "assigned_window": "Upper"},
    )
    assert unknown.status_code == 422, unknown.text
    assert len((await _analysis(client, s.run_id))["steps"]) == 4


async def test_analysis_carries_assignment_fields(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, analysis = await _setup(client, session_factory, fake_auth.workspace_id)
    sample, reference = _step(analysis, 64.0), _step(analysis, 71.3)
    assert analysis["outside_every_window"] == []
    assert _named(analysis, "Main", sample["well_id"]) == (64.0, "range", sample["id"])
    assert _named(analysis, "Main", reference["well_id"]) == (71.3, "range", reference["id"])

    # 85.2 °C is on the trace but above Main's upper limit: in no window.
    add = await client.post(
        f"/api/v1/runs/{s.run_id}/melting-steps",
        json={"well_id": sample["well_id"], "channel_key": "ratio", "value": 85.2},
    )
    assert add.status_code == 201, add.text
    unplaced = add.json()["step"]
    assert (await _analysis(client, s.run_id))["outside_every_window"] == [unplaced["id"]]

    assert (await _assign(client, unplaced, "Lower", reason="late melt")).status_code == 200
    after = await _analysis(client, s.run_id)
    assert after["outside_every_window"] == []
    read = _step(after, 85.2)
    assert (read["assigned_window"], read["assignment_reason"]) == ("Lower", "late melt")
    assert read["assigned_by"] == str(fake_auth.user_id) and read["assigned_at"]
    assert _named(after, "Lower", sample["well_id"]) == (85.2, "assignment", unplaced["id"])


def _step_file() -> dict[str, Any]:
    """The melt file, with a step at 60 °C in the sample's 350 nm trace (synthetic: a sigmoid
    on the file's straight line plus seeded noise). Every other trace stays a straight line."""
    rng = random.Random(7)
    return _melt_file(
        {
            ("350nm", 2, i, "value"): round(
                0.8
                + i * 0.001
                + 1 / (1 + math.exp(-(temperature(i) - 60.0) / 1.2))
                + rng.gauss(0, 0.01),
                6,
            )
            for i in range(POINTS)
        }
    )


WIDEST = temperature(POINTS - 1) - temperature(0)  # every trace of the run: 60.363 °C


async def test_viewer_reads_the_candidate_peaks_of_a_position(
    client: AsyncClient,
    viewer_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, analysis = await _setup(client, session_factory, fake_auth.workspace_id, files=_step_file())
    sample = _step(analysis, 64.0)["well_id"]

    resp = await viewer_client.get(f"/api/v1/runs/{s.run_id}/wells/{sample}/peak-candidates")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert list(body) == ["signals"]
    # One entry per signal of the position, in the run's signal order.
    assert [sg["channel_key"] for sg in body["signals"]] == ["ratio", "f330", "f350", "scattering"]
    for signal in body["signals"]:
        assert set(signal) == {"channel_key", "smoothing_window", "candidates"}
        # By default what the Traces view uses for the derivative: 5% of the widest trace.
        assert signal["smoothing_window"] == pytest.approx(0.05 * WIDEST)
    found = {sg["channel_key"]: sg["candidates"] for sg in body["signals"]}
    assert found["ratio"] == found["f330"] == found["scattering"] == []  # straight lines
    (peak,) = found["f350"]
    assert set(peak) == {"value", "direction", "strength"}
    assert peak["value"] == pytest.approx(60.0, abs=0.3) and peak["direction"] == "rising"
    assert peak["strength"] >= 10
    # Reading stores nothing: the run's peaks are the instrument's three, as before.
    assert len((await _analysis(client, s.run_id))["steps"]) == 3


async def test_peak_candidates_smoothing_is_used_capped_or_refused(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, analysis = await _setup(client, session_factory, fake_auth.workspace_id)
    url = f"/api/v1/runs/{s.run_id}/wells/{_step(analysis, 64.0)['well_id']}/peak-candidates"

    given = await client.get(url, params={"smoothing_window": 2})
    assert given.status_code == 200, given.text
    assert {sg["smoothing_window"] for sg in given.json()["signals"]} == {2.0}

    wide = await client.get(url, params={"smoothing_window": 1e6})
    assert wide.status_code == 200, wide.text
    assert [sg["smoothing_window"] for sg in wide.json()["signals"]] == [pytest.approx(WIDEST)] * 4

    # Refused as the derivative view of GET /runs/{run_id}/curves refuses it.
    curves = await client.get(
        f"/api/v1/runs/{s.run_id}/curves", params={"view": "derivative", "window": 0}
    )
    for refused in (0, -1, "nan"):
        resp = await client.get(url, params={"smoothing_window": refused})
        assert resp.status_code == curves.status_code == 422, resp.text


async def test_peak_candidates_of_an_unknown_run_or_position_return_404(
    client: AsyncClient,
    database_url: str,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, analysis = await _setup(client, session_factory, fake_auth.workspace_id)
    sample = _step(analysis, 64.0)["well_id"]

    unknown_well = await client.get(
        f"/api/v1/runs/{s.run_id}/wells/{uuid.uuid4()}/peak-candidates"
    )
    unknown_run = await client.get(f"/api/v1/runs/{uuid.uuid4()}/wells/{sample}/peak-candidates")
    stranger = FakeAuth(role="admin", workspace_id=uuid.uuid4(), user_id=uuid.uuid4())
    async with _client_as(database_url, stranger) as other:
        other_workspace = await other.get(
            f"/api/v1/runs/{s.run_id}/wells/{sample}/peak-candidates"
        )
    assert (
        unknown_well.status_code,
        unknown_run.status_code,
        other_workspace.status_code,
    ) == (404, 404, 404)
    assert (await client.get(f"/api/v1/runs/{s.run_id}/wells/{sample}/peak-candidates")).is_success


def _accept_url(run_id: Any) -> str:
    return f"/api/v1/runs/{run_id}/melting-steps/accept"


def _items(analysis: dict[str, Any], **versions: int) -> dict[str, Any]:
    """Every peak of the run at the version read; ``versions`` overrides one by its id."""
    return {
        "steps": [
            {"id": st["id"], "expected_version": versions.get(st["id"], st["version"])}
            for st in analysis["steps"]
        ]
    }


def _states(analysis: dict[str, Any]) -> dict[float, tuple[str, int]]:
    return {st["value"]: (st["status"], st["version"]) for st in analysis["steps"]}


async def test_editor_accepts_the_unreviewed_peaks_of_a_run_in_one_request(
    client: AsyncClient,
    database_url: str,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, analysis = await _setup(client, session_factory, fake_auth.workspace_id)
    rejected = await client.patch(
        f"/api/v1/melting-steps/{_step(analysis, 71.3)['id']}",
        json={"expected_version": 1, "status": "rejected", "value": 71.3, "reason": "bubble"},
    )
    assert rejected.status_code == 200, rejected.text
    analysis = await _analysis(client, s.run_id)
    sample = _step(analysis, 64.0)

    editor = FakeAuth(role="editor", workspace_id=fake_auth.workspace_id, user_id=uuid.uuid4())
    async with _client_as(database_url, editor) as as_editor:
        resp = await as_editor.post(_accept_url(s.run_id), json=_items(analysis))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"steps", "skipped", "recalculated", "compute_warning"}
    assert (body["skipped"], body["recalculated"], body["compute_warning"]) == (1, True, None)
    assert sorted(st["value"] for st in body["steps"]) == [36.6, 64.0]
    for st in body["steps"]:
        assert (st["status"], st["version"], st["reason"]) == ("accepted", 2, None)
        assert st["changed_by"] == str(editor.user_id)
        assert set(st) == set(sample)  # the same model as the single review returns

    after = await _analysis(client, s.run_id)
    assert _states(after) == {36.6: ("accepted", 2), 64.0: ("accepted", 2), 71.3: ("rejected", 2)}
    # Asking again changes nothing and recalculates nothing.
    again = await client.post(_accept_url(s.run_id), json=_items(after))
    assert again.status_code == 200, again.text
    assert again.json() == {
        "steps": [],
        "skipped": 3,
        "recalculated": False,
        "compute_warning": None,
    }


async def test_accept_many_as_viewer_returns_403(
    client: AsyncClient,
    viewer_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, analysis = await _setup(client, session_factory, fake_auth.workspace_id)
    resp = await viewer_client.post(_accept_url(s.run_id), json=_items(analysis))
    assert resp.status_code == 403, resp.text
    assert set(_states(await _analysis(client, s.run_id)).values()) == {("unreviewed", 1)}


async def test_accept_many_is_all_or_nothing(
    client: AsyncClient,
    database_url: str,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, analysis = await _setup(client, session_factory, fake_auth.workspace_id)
    url, items = _accept_url(s.run_id), _items(analysis)

    # A peak that is not the run's: the usual not-found.
    foreign = {"steps": [*items["steps"], {"id": str(uuid.uuid4()), "expected_version": 1}]}
    not_found = await client.post(url, json=foreign)
    assert not_found.status_code == 404, not_found.text
    # A stale version on the last peak, after the others were written in the same save.
    stale = _items(analysis, **{analysis["steps"][-1]["id"]: 5})
    conflict = await client.post(url, json=stale)
    assert conflict.status_code == 409, conflict.text
    # Another workspace's run.
    stranger = FakeAuth(role="admin", workspace_id=uuid.uuid4(), user_id=uuid.uuid4())
    async with _client_as(database_url, stranger) as other:
        elsewhere = await other.post(url, json=items)
    assert elsewhere.status_code == 404, elsewhere.text
    assert set(_states(await _analysis(client, s.run_id)).values()) == {("unreviewed", 1)}

    # An approved run refuses as the single review does.
    await _sql(session_factory, "UPDATE runs SET status = 'approved' WHERE id = :id", id=s.run_id)
    approved = await client.post(url, json=items)
    assert approved.status_code == 409, approved.text
    assert set(_states(await _analysis(client, s.run_id)).values()) == {("unreviewed", 1)}


async def test_accept_many_refuses_a_malformed_list(client: AsyncClient) -> None:
    url = _accept_url(uuid.uuid4())
    one = {"id": str(uuid.uuid4()), "expected_version": 1}
    too_many = [{"id": str(uuid.uuid4()), "expected_version": 1} for _ in range(2001)]
    for steps in (too_many, [one, one], [], [{"id": one["id"], "expected_version": 0}]):
        resp = await client.post(url, json={"steps": steps})
        assert resp.status_code == 422, resp.text
    # 2,000 is allowed: it gets as far as looking for the run.
    assert (await client.post(url, json={"steps": too_many[:2000]})).status_code == 404
