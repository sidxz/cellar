"""Integration test: migration 069 BACKFILL_SQL links run plates to inventory plates.

Exact barcode match, else exact ``plate_map->>'name'`` = ``plate_label``; same
workspace as the run; only when exactly one candidate matches.
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa

_M069_PATH = (
    Path(__file__).parents[2] / "alembic" / "versions" / "069_run_plate_registered_plate.py"
)
_USER_ID = uuid.UUID("eeeeeeee-0000-0000-0000-000000000001")


def _load_m069():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("m069", _M069_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _insert_protocol(session, protocol_id: uuid.UUID, ws_id: uuid.UUID) -> None:  # type: ignore[no-untyped-def]
    await session.execute(
        sa.text(
            "INSERT INTO protocols "
            "(id, workspace_id, name, protocol_type, status, "
            "is_locked, dose_unit, pos_control_signal, version, protocol_version, created_by) "
            "VALUES (:id, :ws, :name, 'biochemical', 'active', "
            "false, 'uM', 'high', 1, 1, :user)"
        ),
        {"id": protocol_id, "ws": ws_id, "name": f"P-{str(protocol_id)[:8]}", "user": _USER_ID},
    )


async def _insert_run(
    session, run_id: uuid.UUID, protocol_id: uuid.UUID, ws_id: uuid.UUID
) -> None:  # type: ignore[no-untyped-def]
    await session.execute(
        sa.text(
            "INSERT INTO runs (id, workspace_id, protocol_id, run_date, operator, "
            "status, is_locked, version) "
            "VALUES (:id, :ws, :proto, :run_date, :user, 'draft', false, 1)"
        ),
        {
            "id": run_id,
            "ws": ws_id,
            "proto": protocol_id,
            "run_date": date.today(),
            "user": _USER_ID,
        },
    )


async def _insert_plate(  # type: ignore[no-untyped-def]
    session,
    plate_id: uuid.UUID,
    run_id: uuid.UUID,
    plate_number: int,
    *,
    barcode: str | None = None,
    name: str | None = None,
) -> None:
    await session.execute(
        sa.text(
            "INSERT INTO plates (id, run_id, plate_number, barcode, plate_map) "
            "VALUES (:id, :run, :n, :bc, CAST(:pm AS jsonb))"
        ),
        {
            "id": plate_id,
            "run": run_id,
            "n": plate_number,
            "bc": barcode,
            "pm": json.dumps({"name": name}) if name is not None else None,
        },
    )


async def _insert_registered_plate(  # type: ignore[no-untyped-def]
    session, plate_id: uuid.UUID, ws_id: uuid.UUID, *, barcode: str, label: str
) -> None:
    await session.execute(
        sa.text(
            "INSERT INTO registered_plates (id, workspace_id, barcode, plate_label, "
            "format, plate_type, registered_by, version) "
            "VALUES (:id, :ws, :bc, :label, '96', 'assay', :rb, 1)"
        ),
        {"id": plate_id, "ws": ws_id, "bc": barcode, "label": label, "rb": _USER_ID},
    )


async def _linked_id(session, plate_id: uuid.UUID) -> uuid.UUID | None:  # type: ignore[no-untyped-def]
    return (
        await session.execute(
            sa.text("SELECT registered_plate_id FROM plates WHERE id = :id"), {"id": plate_id}
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_backfill_links_unique_matches_only(db_session, workspace_id):  # type: ignore[no-untyped-def]
    m069 = _load_m069()
    other_ws = uuid.uuid4()
    proto_id, run_id = uuid.uuid4(), uuid.uuid4()
    rp_unique, rp_ambig_1, rp_ambig_2, rp_foreign = (uuid.uuid4() for _ in range(4))
    plate_by_barcode, plate_by_label, plate_ambiguous, plate_cross_ws = (
        uuid.uuid4() for _ in range(4)
    )

    await _insert_protocol(db_session, proto_id, workspace_id)
    await _insert_run(db_session, run_id, proto_id, workspace_id)
    await _insert_registered_plate(
        db_session, rp_unique, workspace_id, barcode="000123", label="SAC3-014-3070"
    )
    await _insert_registered_plate(
        db_session, rp_ambig_1, workspace_id, barcode="AMB-1", label="AMBIG"
    )
    await _insert_registered_plate(
        db_session, rp_ambig_2, workspace_id, barcode="AMB-2", label="AMBIG"
    )
    await _insert_registered_plate(
        db_session, rp_foreign, other_ws, barcode="999999", label="FOREIGN"
    )

    await _insert_plate(db_session, plate_by_barcode, run_id, 1, barcode="000123")
    await _insert_plate(db_session, plate_by_label, run_id, 2, name="SAC3-014-3070")
    await _insert_plate(db_session, plate_ambiguous, run_id, 3, name="AMBIG")
    await _insert_plate(db_session, plate_cross_ws, run_id, 4, barcode="999999", name="FOREIGN")

    await db_session.execute(sa.text(m069.BACKFILL_SQL))

    assert await _linked_id(db_session, plate_by_barcode) == rp_unique
    assert await _linked_id(db_session, plate_by_label) == rp_unique
    assert await _linked_id(db_session, plate_ambiguous) is None
    assert await _linked_id(db_session, plate_cross_ws) is None
