"""Migration 096: NaN and infinite well doses become NULL; finite doses stay."""

from __future__ import annotations

import importlib.util
import math
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.fixtures.dose_response_curves import _insert_protocol, _insert_run

_M096 = Path(__file__).parents[2] / "alembic" / "versions" / "096_null_non_finite_well_doses.py"


def _load_m096():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("m096", _M096)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_non_finite_doses_are_cleared(session_factory, workspace_id) -> None:
    protocol_id, run_id, plate_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    doses = {1: math.nan, 2: math.inf, 3: -math.inf, 4: 1.5, 5: None}
    m096 = _load_m096()

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await _insert_protocol(uow, protocol_id, workspace_id)
        await _insert_run(uow, run_id, protocol_id, workspace_id)
        session = uow.session
        await session.execute(
            sa.text("INSERT INTO plates (id, run_id, plate_number) VALUES (:id, :run, 1)"),
            {"id": plate_id, "run": run_id},
        )
        for column, dose in doses.items():
            await session.execute(
                sa.text(
                    'INSERT INTO wells (id, plate_id, row, "column", dose) '
                    "VALUES (:id, :plate, 'A', :col, :dose)"
                ),
                {"id": uuid.uuid4(), "plate": plate_id, "col": column, "dose": dose},
            )

        def upgrade(sync_session) -> None:  # type: ignore[no-untyped-def]
            with Operations.context(MigrationContext.configure(sync_session.connection())):
                m096.upgrade()

        await session.run_sync(upgrade)
        rows = (
            await session.execute(
                sa.text('SELECT "column", dose FROM wells WHERE plate_id = :p ORDER BY "column"'),
                {"p": plate_id},
            )
        ).all()
        await session.rollback()  # leave the shared test database as it was

    assert [(c, d) for c, d in rows] == [(1, None), (2, None), (3, None), (4, 1.5), (5, None)]
