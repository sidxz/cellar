"""The instrument boundary proof: a fake reader for a plate holder flows through preview,
import and curve reading. Nothing outside this file changes for it to pass."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.application.screening.instrument_export import (
    ExportChannel,
    ExportCurve,
    ExportPosition,
    HolderLayout,
    InstrumentExport,
    InstrumentReaders,
    ReportedValue,
)
from cellar.domain.screening_assay.enums import HolderKind
from cellar.domain.screening_assay.holder import holder_label
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from cellar.interface.dependencies import get_container
from tests.fakes.fake_auth import FakeAuth
from tests.fixtures.dose_response_curves import _insert_org, _insert_protocol, _insert_run

FILE = {"file": ("f.bin", b"FAKE", "application/octet-stream")}


class FakePlateReader:
    id = "fake-plate"
    label = "Fake plate format"

    def recognises(self, content: bytes, filename: str) -> bool:
        return content.startswith(b"FAKE")

    def read(self, content: bytes, filename: str) -> InstrumentExport:
        positions = (ExportPosition(1, 1, "alpha"), ExportPosition(2, 3, "beta"))
        channels = (
            ExportChannel("signal_a", "Signal A", "s", "AU"),
            ExportChannel("signal_b", "Signal B", "s", None),
        )
        x = (0.0, 1.0, 2.0, 3.0, 4.0)
        return InstrumentExport(
            reader=self.id,
            holder=HolderLayout(HolderKind.PLATE, 2, 3),
            positions=positions,
            channels=channels,
            curves=tuple(
                ExportCurve(p.row, p.column, c.key, x, tuple(v * p.column for v in x))
                for p in positions
                for c in channels
            ),
            reported=(
                ReportedValue(
                    row=1,
                    column=1,
                    channel="signal_a",
                    kind="onset",
                    ordinal=1,
                    label="Start",
                    value=2.0,
                    unit="s",
                ),
            ),
            settings={"Mode": "test"},
        )


@pytest.fixture
def fake_reader(api_app: FastAPI) -> Iterator[None]:
    child = api_app.state.container.clone()
    child.define(InstrumentReaders, lambda: InstrumentReaders((FakePlateReader(),)))
    api_app.dependency_overrides[get_container] = lambda: child
    yield
    api_app.dependency_overrides.pop(get_container, None)


async def test_fake_plate_reader_flows_through_preview_commit_and_curves(
    client: AsyncClient,
    fake_reader: None,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    ws = fake_auth.workspace_id
    run_id, protocol_id = uuid.uuid4(), uuid.uuid4()
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await _insert_org(uow, uuid.uuid4(), ws)
        await _insert_protocol(uow, protocol_id, ws)
        await _insert_run(uow, run_id, protocol_id, ws)
        await uow.commit()

    resp = await client.post(f"/api/v1/runs/{run_id}/preview-instrument-file", files=FILE)
    assert resp.status_code == 200, resp.text
    preview = resp.json()
    assert (
        preview["reader"],
        preview["holder"]["kind"],
        preview["holder"]["rows"],
        preview["holder"]["columns"],
    ) == ("fake-plate", "plate", 2, 3)
    assert [p["position_label"] for p in preview["positions"]] == ["A1", "B3"]
    assert [(s["channel"], s["kind"], s["label"]) for s in preview["series"]] == [
        ("signal_a", "onset", "Start")
    ]

    labelling = {
        "positions": [
            {"row": p["row"], "column": p["column"], "label": p["label"]}
            for p in preview["positions"]
        ]
    }
    resp = await client.post(
        f"/api/v1/runs/{run_id}/import-instrument-file",
        files=FILE,
        data={"labelling": json.dumps(labelling)},
    )
    assert resp.status_code == 201, resp.text
    assert (resp.json()["positions_created"], resp.json()["curves_created"]) == (2, 4)

    curves = (
        await client.get(f"/api/v1/runs/{run_id}/curves", params={"channel": "signal_b"})
    ).json()
    assert [c["key"] for c in curves["channels"]] == ["signal_a", "signal_b"]
    assert curves["channels"][0]["x_label"] is None
    assert curves["channel"] == "signal_b" and len(curves["curves"]) == 2
    assert [p["position_label"] for p in curves["positions"]] == ["A1", "B3"]
    assert (curves["holder"]["kind"], curves["holder"]["rows"], curves["holder"]["columns"]) == (
        "plate",
        2,
        3,
    )

    plate = (await client.get(f"/api/v1/runs/{run_id}/plate-map")).json()["plates"][0]
    assert (
        plate["holder_kind"],
        plate["holder_rows"],
        plate["holder_columns"],
        plate["format"],
        plate["holder_label"],
    ) == (
        "plate",
        2,
        3,
        "",
        holder_label(HolderKind.PLATE, 2, 3),
    )
