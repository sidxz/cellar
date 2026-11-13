"""API tests: instrument file preview, import and the run's curves.

Full HTTP stack (real DI container, real database, FakeAuth) with a synthetic
raw export built in code. Position and holder labels come from the domain
functions, the reader id from ``default_readers()``.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.domain.screening_assay.enums import HolderKind
from cellar.domain.screening_assay.holder import holder_label, position_label
from cellar.infrastructure.instrument_readers import default_readers
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.fakes.fake_auth import FakeAuth
from tests.fixtures.dose_response_curves import _insert_org, _insert_protocol, _insert_run
from tests.helpers.instrument_workbook import (
    build_processed_workbook,
    build_raw_workbook,
    temperature,
)

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
WORKBOOK = build_raw_workbook(positions={1: "protein alone", 2: "ABC-0000001 (Old)", 3: None})
FILE = {"file": ("run.xlsx", WORKBOOK, XLSX)}


def LABEL(n: int) -> str:
    return position_label(HolderKind.CASSETTE, "A", n)


@dataclass(frozen=True)
class Seeded:
    run_id: uuid.UUID
    tm1_id: uuid.UUID
    molecule_id: uuid.UUID
    batch_id: uuid.UUID

    @property
    def preview_url(self) -> str:
        return f"/api/v1/runs/{self.run_id}/preview-instrument-file"

    @property
    def import_url(self) -> str:
        return f"/api/v1/runs/{self.run_id}/import-instrument-file"


async def _seed(session_factory: async_sessionmaker[AsyncSession], ws: uuid.UUID) -> Seeded:
    """Org, protocol with a °C readout named like the file's first transition, draft run,
    and a molecule with identifier ``ABC-0000001`` and one batch."""
    s = Seeded(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    org_id, protocol_id = uuid.uuid4(), uuid.uuid4()
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await _insert_org(uow, org_id, ws)
        await _insert_protocol(uow, protocol_id, ws)
        await uow.session.execute(
            sa.text(
                "INSERT INTO readout_definitions "
                "(id, protocol_id, name, data_type, unit, display_order, is_calculated) "
                "VALUES (:id, :proto, 'Inflection Point #1 for Ratio', 'numeric', '°C', 0, false)"
            ),
            {"id": s.tm1_id, "proto": protocol_id},
        )
        await _insert_run(uow, s.run_id, protocol_id, ws)
        await uow.session.execute(
            sa.text(
                "INSERT INTO molecules "
                "(id, workspace_id, name, molecule_type, structure_status, "
                "registration_status, synthesis_status, lifecycle_stage, "
                "registration_number, originating_org_id, version) "
                "VALUES (:id, :ws, 'Molecule 1', 'small_molecule', 'undisclosed', "
                "'approved', 'virtual', 'registered', :reg, :org, 1)"
            ),
            {"id": s.molecule_id, "ws": ws, "reg": f"REG-{uuid.uuid4().hex[:8]}", "org": org_id},
        )
        await uow.session.execute(
            sa.text(
                "INSERT INTO molecule_identifiers "
                "(id, molecule_id, workspace_id, identifier, identifier_type, source, "
                "registered_by) VALUES (:id, :mol, :ws, 'ABC-0000001', 'custom', 'test', :by)"
            ),
            {"id": uuid.uuid4(), "mol": s.molecule_id, "ws": ws, "by": uuid.uuid4()},
        )
        await _insert_batch(uow, s.batch_id, ws, s.molecule_id)
        await uow.commit()
    return s


async def _insert_batch(
    uow: AsyncUnitOfWork, batch_id: uuid.UUID, ws: uuid.UUID, molecule_id: uuid.UUID
) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO batches (id, workspace_id, molecule_id, batch_number, "
            "amount_value, amount_unit, source, chemist, version) "
            "VALUES (:id, :ws, :mol, :bn, 1.0, 'mg', 'synthesized', :chem, 1)"
        ),
        {
            "id": batch_id,
            "ws": ws,
            "mol": molecule_id,
            "bn": f"B-{uuid.uuid4().hex[:6]}",
            "chem": uuid.uuid4(),
        },
    )


async def _count(
    session_factory: async_sessionmaker[AsyncSession],
    table: str,
    run_id: uuid.UUID,
    *,
    where: str = "true",
) -> int:
    async with session_factory() as session:
        return (
            await session.execute(
                sa.text(f"SELECT count(*) FROM {table} WHERE run_id = :run AND {where}"),
                {"run": run_id},
            )
        ).scalar_one()


def labelling_from(preview: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    """The labelling a user accepting every suggestion would send."""
    positions = []
    for p in preview["positions"]:
        batch_id = (p["suggestion"] or {}).get("batch_id")
        positions.append(
            {
                "row": p["row"],
                "column": p["column"],
                "label": p["label"],
                "well_type": "reference" if p["label"] == "protein alone" else "sample",
                "batch_id": batch_id,
                "dose": 10.0 if batch_id else None,
            }
        )
    series = [
        {
            "channel": s["channel"],
            "kind": s["kind"],
            "ordinal": s["ordinal"],
            "readout_definition_id": s["suggested_readout_definition_id"],
        }
        for s in preview["series"]
        if s["suggested_readout_definition_id"]
    ]
    return {"positions": positions, "series": series} | overrides


async def _import(client: AsyncClient, s: Seeded) -> dict[str, Any]:
    preview = (await client.post(s.preview_url, files=FILE)).json()
    resp = await client.post(
        s.import_url, files=FILE, data={"labelling": json.dumps(labelling_from(preview))}
    )
    assert resp.status_code == 201, resp.text
    return labelling_from(preview)


async def test_preview_then_import_then_read_curves(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s = await _seed(session_factory, fake_auth.workspace_id)

    resp = await client.post(s.preview_url, files=FILE)
    assert resp.status_code == 200, resp.text
    preview = resp.json()
    assert preview["reader"] == default_readers()[0].id
    assert preview["reader_label"] == default_readers()[0].label
    assert preview["holder"] == {
        "kind": "cassette",
        "rows": 1,
        "columns": 3,
        "label": holder_label(HolderKind.CASSETTE, 1, 3),
    }
    assert preview["dose_unit"] == "uM"
    assert [p["position_label"] for p in preview["positions"]] == [LABEL(1), LABEL(2), LABEL(3)]
    suggestion = preview["positions"][1]["suggestion"]
    assert suggestion["batch_id"] == str(s.batch_id)
    assert suggestion["molecule_id"] == str(s.molecule_id)
    assert [b["batch_id"] for b in suggestion["batches"]] == [str(s.batch_id)]
    assert preview["positions"][0]["suggestion"] is None
    assert preview["positions"][2]["label"] == ""
    transition = next(
        x for x in preview["series"] if (x["kind"], x["ordinal"]) == ("transition", 1)
    )
    assert transition["suggested_readout_definition_id"] == str(s.tm1_id)
    assert (transition["unit"], transition["count"]) == ("°C", 3)
    assert [c["key"] for c in preview["channels"]] == ["ratio", "f330", "f350", "scattering"]
    assert preview["readouts"] == [
        {"id": str(s.tm1_id), "name": "Inflection Point #1 for Ratio", "unit": "°C"}
    ]
    assert isinstance(preview["settings"], dict) and preview["warnings"] == []

    labelling = labelling_from(preview)
    resp = await client.post(s.import_url, files=FILE, data={"labelling": json.dumps(labelling)})
    assert resp.status_code == 201, resp.text
    out = resp.json()
    assert out["reader"] == default_readers()[0].id
    assert (out["positions_created"], out["curves_created"], out["values_inserted"]) == (3, 12, 3)
    assert out["file_attached"] is True and out["attachment_warning"] is None
    assert uuid.UUID(out["attachment_id"])
    assert out["compute_warning"] is None  # the calculation engine ran on a holder with no format

    resp = await client.get(f"/api/v1/runs/{s.run_id}/curves")
    assert resp.status_code == 200, resp.text
    curves = resp.json()
    assert [c["key"] for c in curves["channels"]] == ["ratio", "f330", "f350", "scattering"]
    assert curves["channels"][0]["x_label"] == "Temperature"
    assert curves["channel"] == "ratio"
    assert curves["holder"]["label"] == holder_label(HolderKind.CASSETTE, 1, 3)
    assert [p["position_label"] for p in curves["positions"]] == [LABEL(1), LABEL(2), LABEL(3)]
    assert len(curves["curves"]) == 3
    assert curves["curves"][0]["x"][:2] == [temperature(0), temperature(1)]
    assert curves["curves"][0]["well_id"] == curves["positions"][0]["well_id"]
    assert {r["kind"] for r in curves["curves"][0]["reported"]} == {"onset", "transition"}
    f330 = (await client.get(f"/api/v1/runs/{s.run_id}/curves", params={"channel": "f330"})).json()
    assert f330["channel"] == "f330" and len(f330["curves"]) == 3
    unknown = await client.get(f"/api/v1/runs/{s.run_id}/curves", params={"channel": "nope"})
    assert unknown.status_code == 422

    # The transition value landed as an ordinary readout row for the position,
    # carrying batch and molecule.
    assert (
        await _count(session_factory, "readout_data", s.run_id, where="is_computed = false") == 3
    )
    assert (
        await _count(
            session_factory,
            "readout_data",
            s.run_id,
            where=f"batch_id = '{s.batch_id}' AND molecule_id = '{s.molecule_id}'",
        )
        == 1
    )


async def test_derivative_view_over_http(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s = await _seed(session_factory, fake_auth.workspace_id)
    await _import(client, s)
    url = f"/api/v1/runs/{s.run_id}/curves"
    body = (await client.get(url, params={"view": "derivative"})).json()
    assert body["view"] == "derivative" and body["window"] > 0 and len(body["curves"]) == 3
    assert (await client.get(url, params={"view": "derivative", "window": 0})).status_code == 422
    measured = (await client.get(url)).json()
    assert measured["view"] == "measured" and measured["window"] is None


async def test_plate_map_reports_holder_and_position_labels(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s = await _seed(session_factory, fake_auth.workspace_id)
    before = (await client.get(f"/api/v1/runs/{s.run_id}/plate-map")).json()
    assert before["has_measured_curves"] is False and before["plates"] == []

    await _import(client, s)

    plate = (await client.get(f"/api/v1/runs/{s.run_id}/plate-map")).json()
    assert plate["has_measured_curves"] is True
    first = plate["plates"][0]
    assert (first["holder_kind"], first["holder_rows"], first["holder_columns"]) == (
        "cassette",
        1,
        3,
    )
    assert first["format"] == ""
    assert first["holder_label"] == holder_label(HolderKind.CASSETTE, 1, 3)
    assert first["wells"][0]["position_label"] == LABEL(1)
    assert first["wells"][0]["label"] == "protein alone"
    assert first["wells"][2]["label"] is None


async def test_note_is_returned_by_plate_map_and_curves(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s = await _seed(session_factory, fake_auth.workspace_id)
    preview = (await client.post(s.preview_url, files=FILE)).json()
    labelling = labelling_from(preview)
    labelling["positions"][1]["note"] = "strongly coloured"
    resp = await client.post(s.import_url, files=FILE, data={"labelling": json.dumps(labelling)})
    assert resp.status_code == 201, resp.text

    run_id = s.run_id
    wells = (await client.get(f"/api/v1/runs/{run_id}/plate-map")).json()["plates"][0]["wells"]
    assert [w["note"] for w in wells] == [None, "strongly coloured", None]
    positions = (await client.get(f"/api/v1/runs/{run_id}/curves")).json()["positions"]
    assert positions[1]["note"] == "strongly coloured"


async def test_note_over_1000_characters_returns_422(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s = await _seed(session_factory, fake_auth.workspace_id)
    preview = (await client.post(s.preview_url, files=FILE)).json()
    labelling = labelling_from(preview)
    labelling["positions"][0]["note"] = "x" * 1001
    resp = await client.post(s.import_url, files=FILE, data={"labelling": json.dumps(labelling)})
    assert resp.status_code == 422 and "Invalid labelling" in resp.text
    assert await _count(session_factory, "plates", s.run_id) == 0


async def test_second_import_is_refused_until_reset(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s = await _seed(session_factory, fake_auth.workspace_id)
    labelling = await _import(client, s)

    assert (await client.post(s.preview_url, files=FILE)).status_code == 409
    again = await client.post(s.import_url, files=FILE, data={"labelling": json.dumps(labelling)})
    assert again.status_code == 409 and "Reset" in again.text
    assert await _count(session_factory, "measured_curves", s.run_id) == 12  # unchanged

    reset = (await client.post(f"/api/v1/runs/{s.run_id}/reset-data")).json()
    assert reset["measured_curves_deleted"] == 12
    assert await _count(session_factory, "measured_curves", s.run_id) == 0
    again = await client.post(s.import_url, files=FILE, data={"labelling": json.dumps(labelling)})
    assert again.status_code == 201, again.text


async def test_run_update_after_import_keeps_curves(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s = await _seed(session_factory, fake_auth.workspace_id)
    await _import(client, s)

    resp = await client.patch(f"/api/v1/runs/{s.run_id}", json={"notes": "edited"})
    assert resp.status_code == 200, resp.text
    assert len((await client.get(f"/api/v1/runs/{s.run_id}/curves")).json()["curves"]) == 3


async def test_processed_layout_returns_422_asking_for_raw(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s = await _seed(session_factory, fake_auth.workspace_id)
    resp = await client.post(
        s.preview_url, files={"file": ("p.xlsx", build_processed_workbook(), XLSX)}
    )
    assert resp.status_code == 422 and "raw" in resp.text


async def test_unrecognised_file_lists_supported_formats(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s = await _seed(session_factory, fake_auth.workspace_id)
    resp = await client.post(s.preview_url, files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")})
    assert resp.status_code == 422 and default_readers()[0].label in resp.text


async def test_malformed_labelling_returns_422(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s = await _seed(session_factory, fake_auth.workspace_id)
    resp = await client.post(s.import_url, files=FILE, data={"labelling": "{not json"})
    assert resp.status_code == 422 and "Invalid labelling" in resp.text
    negative = {"positions": [{"row": 1, "column": 1, "dose": -1}]}
    resp = await client.post(s.import_url, files=FILE, data={"labelling": json.dumps(negative)})
    assert resp.status_code == 422 and "Invalid labelling" in resp.text
    assert await _count(session_factory, "plates", s.run_id) == 0


async def test_batch_from_another_workspace_is_404_and_nothing_written(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s = await _seed(session_factory, fake_auth.workspace_id)
    foreign_batch_id = uuid.uuid4()
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await _insert_batch(uow, foreign_batch_id, uuid.uuid4(), s.molecule_id)
        await uow.commit()

    preview = (await client.post(s.preview_url, files=FILE)).json()
    labelling = labelling_from(preview)
    labelling["positions"][1]["batch_id"] = str(foreign_batch_id)
    resp = await client.post(s.import_url, files=FILE, data={"labelling": json.dumps(labelling)})
    assert resp.status_code == 404, resp.text
    assert await _count(session_factory, "measured_curves", s.run_id) == 0
    assert await _count(session_factory, "plates", s.run_id) == 0


async def test_delete_run_removes_curves(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s = await _seed(session_factory, fake_auth.workspace_id)
    await _import(client, s)
    assert await _count(session_factory, "measured_curves", s.run_id) == 12

    resp = await client.delete(f"/api/v1/runs/{s.run_id}")
    assert resp.status_code == 204, resp.text
    assert await _count(session_factory, "measured_curves", s.run_id) == 0


async def test_import_missing_run_returns_404(client: AsyncClient) -> None:
    resp = await client.post(
        f"/api/v1/runs/{uuid.uuid4()}/import-instrument-file",
        files=FILE,
        data={"labelling": json.dumps({"positions": []})},
    )
    assert resp.status_code == 404, resp.text
    resp = await client.get(f"/api/v1/runs/{uuid.uuid4()}/curves")
    assert resp.status_code == 404, resp.text


async def test_viewer_cannot_preview_or_import_but_can_read_curves(
    viewer_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
) -> None:
    s = await _seed(session_factory, workspace_id)
    assert (await viewer_client.post(s.preview_url, files=FILE)).status_code == 403
    resp = await viewer_client.post(
        s.import_url, files=FILE, data={"labelling": json.dumps({"positions": []})}
    )
    assert resp.status_code == 403
    resp = await viewer_client.get(f"/api/v1/runs/{s.run_id}/curves")
    assert resp.status_code == 200, resp.text
    assert (resp.json()["channels"], resp.json()["channel"], resp.json()["curves"]) == (
        [],
        None,
        [],
    )
