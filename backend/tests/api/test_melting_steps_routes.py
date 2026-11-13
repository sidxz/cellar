"""API tests: a run's melting analysis, and adding and reviewing melting steps.

The synthetic run has a reference position whose steps sit at 36.6 and 71.3 °C and a
sample whose ligand merged them into one at 64.0 °C, read in two temperature windows,
Lower (25 to 50) and Main (50 to 85).
"""

from __future__ import annotations

import json
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
from tests.helpers.instrument_workbook import build_raw_workbook

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# 1060 points reach 85.4 °C, so both windows lie inside every trace.
MELT_FILE = {
    "file": (
        "melt.xlsx",
        build_raw_workbook(
            positions={1: "protein alone", 2: "ABC-0000001 (Old)"},
            points=1060,
            reported={
                "Onset #1 for Ratio ": {1: 33.0, 2: 60.0},
                "Inflection Point #1 for Ratio ": {1: 36.6, 2: 64.0},
                "Inflection Point #2 for Ratio ": {1: 71.3},
            },
        ),
        XLSX,
    )
}
NOT_EDITABLE = "Melting steps can be changed only while the run is draft or in progress"


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
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], ws: uuid.UUID
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
            },
        )
        assert resp.status_code == 201, resp.text

    preview = (await client.post(s.preview_url, files=MELT_FILE)).json()
    resp = await client.post(
        s.import_url, files=MELT_FILE, data={"labelling": json.dumps(labelling_from(preview))}
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


async def test_completed_run_returns_409(
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
    add = await client.post(
        f"/api/v1/runs/{s.run_id}/melting-steps",
        json={"well_id": sample["well_id"], "channel_key": "ratio", "value": 40.0},
    )
    for resp in (review, add):
        assert resp.status_code == 409, resp.text
        assert NOT_EDITABLE in resp.text
    after = await _analysis(client, s.run_id)
    assert after["edit_refusal"] == NOT_EDITABLE
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
