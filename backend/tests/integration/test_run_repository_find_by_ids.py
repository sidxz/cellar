"""Integration tests: RunRepository — find_by_ids and the registered-plate link round-trip."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa

from cellar.domain.screening_assay.run import Plate, Run
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.run_repository import (
    SQLAlchemyRunRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

_USER_ID = uuid.UUID("eeeeeeee-0000-0000-0000-000000000001")


async def _insert_protocol(uow: AsyncUnitOfWork, protocol_id: uuid.UUID, ws_id: uuid.UUID) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO protocols "
            "(id, workspace_id, name, protocol_type, status, "
            "is_locked, dose_unit, pos_control_signal, version, protocol_version, created_by) "
            "VALUES (:id, :ws, :name, 'biochemical', 'active', "
            "false, 'uM', 'high', 1, 1, :user)"
        ),
        {
            "id": protocol_id,
            "ws": ws_id,
            "name": f"Protocol-{str(protocol_id)[:8]}",
            "user": _USER_ID,
        },
    )


async def _insert_run(
    uow: AsyncUnitOfWork,
    run_id: uuid.UUID,
    protocol_id: uuid.UUID,
    ws_id: uuid.UUID,
    *,
    run_date: date | None = None,
) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO runs "
            "(id, workspace_id, protocol_id, run_date, operator, "
            "status, is_locked, version, notes) "
            "VALUES (:id, :ws, :proto, :run_date, :user, "
            "'draft', false, 1, :notes)"
        ),
        {
            "id": run_id,
            "ws": ws_id,
            "proto": protocol_id,
            "run_date": run_date or date.today(),
            "user": _USER_ID,
            "notes": None,
        },
    )


@pytest.mark.asyncio
class TestFindByIds:
    async def test_returns_runs_for_matching_ids(self, uow, workspace_id):
        proto_id = uuid.uuid4()
        r1, r2, r3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        async with uow:
            await _insert_protocol(uow, proto_id, workspace_id)
            await _insert_run(uow, r1, proto_id, workspace_id)
            await _insert_run(uow, r2, proto_id, workspace_id)
            await _insert_run(uow, r3, proto_id, workspace_id)
            await uow.commit()

        repo = SQLAlchemyRunRepository(uow)
        async with uow:
            runs = await repo.find_by_ids(workspace_id, [r1, r3])

        assert set(runs.keys()) == {r1, r3}
        assert runs[r1].id == r1
        assert runs[r3].id == r3

    async def test_filters_by_workspace(self, uow, workspace_id):
        other_ws = uuid.uuid4()
        proto_a = uuid.uuid4()
        proto_b = uuid.uuid4()
        r_local = uuid.uuid4()
        r_other = uuid.uuid4()
        async with uow:
            await _insert_protocol(uow, proto_a, workspace_id)
            await _insert_protocol(uow, proto_b, other_ws)
            await _insert_run(uow, r_local, proto_a, workspace_id)
            await _insert_run(uow, r_other, proto_b, other_ws)
            await uow.commit()

        repo = SQLAlchemyRunRepository(uow)
        async with uow:
            runs = await repo.find_by_ids(workspace_id, [r_local, r_other])

        assert set(runs.keys()) == {r_local}

    async def test_empty_input_returns_empty(self, uow, workspace_id):
        repo = SQLAlchemyRunRepository(uow)
        async with uow:
            runs = await repo.find_by_ids(workspace_id, [])
        assert runs == {}

    async def test_missing_ids_silently_dropped(self, uow, workspace_id):
        proto_id = uuid.uuid4()
        r1 = uuid.uuid4()
        async with uow:
            await _insert_protocol(uow, proto_id, workspace_id)
            await _insert_run(uow, r1, proto_id, workspace_id)
            await uow.commit()

        repo = SQLAlchemyRunRepository(uow)
        async with uow:
            runs = await repo.find_by_ids(workspace_id, [r1, uuid.uuid4()])
        assert set(runs.keys()) == {r1}


async def _insert_registered_plate(
    uow: AsyncUnitOfWork, plate_id: uuid.UUID, ws_id: uuid.UUID, *, barcode: str
) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO registered_plates (id, workspace_id, barcode, plate_label, "
            "format, plate_type, registered_by, version) "
            "VALUES (:id, :ws, :bc, :bc, '96', 'assay', :rb, 1)"
        ),
        {"id": plate_id, "ws": ws_id, "bc": barcode, "rb": _USER_ID},
    )


@pytest.mark.asyncio
class TestRegisteredPlateLinkRoundTrip:
    async def test_link_persists_and_clearing_persists_null(self, uow, workspace_id):
        proto_id, rp_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            await _insert_protocol(uow, proto_id, workspace_id)
            await _insert_registered_plate(uow, rp_id, workspace_id, barcode="000123")
            await uow.commit()

        run = Run.create(
            workspace_id=workspace_id,
            protocol_id=proto_id,
            run_date=date.today(),
            operator=_USER_ID,
        )
        plate = Plate(run_id=run.id, plate_number=1, registered_plate_id=rp_id)
        run.add_plate(plate)

        repo = SQLAlchemyRunRepository(uow)
        async with uow:
            await repo.save(run)
            await uow.commit()

        async with uow:
            loaded = await repo.find_by_id_in_workspace(workspace_id, run.id)
            assert loaded is not None
            assert loaded.plates[0].registered_plate_id == rp_id
            loaded.link_plate(plate.id, None)
            await repo.save(loaded)
            await uow.commit()

        async with uow:
            again = await repo.find_by_id_in_workspace(workspace_id, run.id)
            assert again is not None
            assert again.plates[0].registered_plate_id is None
