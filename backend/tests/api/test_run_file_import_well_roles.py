"""API test: a run file's "Control State" column decides each well's role.

The protocol layout says A1 = positive control, A2 = negative control; the file
(as the lab's screening platform exports it, each run with its own layout) says
the opposite. The file wins, and the preview says where the two differ. The
platform's words name the effect; under this LOW protocol (positive control = the
full effect) its "positive control (hit)" is a positive control.
"""

from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.fakes.fake_auth import FakeAuth
from tests.fixtures.dose_response_curves import _insert_org, _insert_protocol, _insert_run

CSV = (
    b"Plate Name,Well,Control State,Raw Data\n"
    b"P1,A01,negative control,0.95\n"
    b"P1,A02,positive control (hit),0.07\n"
    b"P1,A03,,0.5\n"
    b"P1,H12,,0.4\n"
)
FILE = {"file": ("run.csv", CSV, "text/csv")}


async def _seed(
    session_factory: async_sessionmaker[AsyncSession], ws: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    run_id, rd_id, protocol_id, tmpl_id = (uuid.uuid4() for _ in range(4))
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await _insert_org(uow, uuid.uuid4(), ws)
        await _insert_protocol(uow, protocol_id, ws)
        await uow.session.execute(
            sa.text(
                "INSERT INTO readout_definitions "
                "(id, protocol_id, name, data_type, display_order, is_calculated) "
                "VALUES (:id, :proto, 'Raw Data', 'numeric', 0, false)"
            ),
            {"id": rd_id, "proto": protocol_id},
        )
        await uow.session.execute(
            sa.text(
                "INSERT INTO plate_templates "
                "(id, workspace_id, name, format, template_map, created_by) "
                "VALUES (:id, :ws, 'Layout', '96', CAST(:map AS jsonb), :by)"
            ),
            {
                "id": tmpl_id,
                "ws": ws,
                "map": json.dumps({"A1": "positive_control", "A2": "negative_control"}),
                "by": uuid.uuid4(),
            },
        )
        await uow.session.execute(
            sa.text(
                "UPDATE protocols SET control_layouts = CAST(:cl AS jsonb), "
                "pos_control_signal = 'low' WHERE id = :id"
            ),
            {"cl": json.dumps({"96": str(tmpl_id)}), "id": protocol_id},
        )
        await _insert_run(uow, run_id, protocol_id, ws)
        await uow.commit()
    return run_id, rd_id


async def test_the_files_control_state_column_beats_the_protocol_layout(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    run_id, rd_id = await _seed(session_factory, fake_auth.workspace_id)

    resp = await client.post(f"/api/v1/runs/{run_id}/preview-file", files=FILE)
    assert resp.status_code == 200, resp.text
    preview = resp.json()
    roles = {s["header"]: s["role"] for s in preview["suggestions"]}
    assert roles["Control State"] == "well_role"
    (plate,) = preview["plates"]
    assert {k: plate[k] for k in plate if k.endswith("_count")} == {
        "well_count": 4,
        "sample_count": 2,
        "positive_count": 1,
        "negative_count": 1,
        "reference_count": 0,
        "blank_count": 0,
    }
    assert "Control State" in plate["roles_from"]
    assert preview["validation_errors"] == []
    assert preview["swapped_controls"] == []
    # One note that the file overrides the layout (on 2 wells), one on how roles were read.
    differ, _read_by_effect = preview["warnings"]
    assert "2 wells" in differ

    mapping = {
        "well": "Well",
        "plate_name": "Plate Name",
        "well_role": "Control State",
        "readout_columns": [{"header": "Raw Data", "readout_definition_id": str(rd_id)}],
    }
    resp = await client.post(
        f"/api/v1/runs/{run_id}/import-file",
        json={"preview_id": preview["preview_id"], "mapping": mapping},
    )
    assert resp.status_code == 201, resp.text
    out = resp.json()
    assert (out["controls_from_file"], out["controls_from_template"]) == (2, 0)
    assert (out["wells_created"], out["values_inserted"]) == (4, 4)

    async with session_factory() as session:
        rows = (
            await session.execute(
                sa.text(
                    "SELECT w.row || w.column, w.well_type FROM wells w "
                    "JOIN plates p ON p.id = w.plate_id WHERE p.run_id = :run"
                ),
                {"run": run_id},
            )
        ).all()
    assert dict(rows) == {
        "A1": "negative_control",
        "A2": "positive_control",
        "A3": "sample",
        "H12": "sample",
    }
