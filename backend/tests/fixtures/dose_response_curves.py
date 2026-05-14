"""Seed helpers for DoseResponseCurve integration tests.

Creates the prerequisite rows (protocol, run) then saves a curve via the
SQLAlchemy repository. Returns the domain entity.
"""

from __future__ import annotations

import uuid
from datetime import date

import sqlalchemy as sa

from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.enums import CurveType
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (
    SQLAlchemyDoseResponseCurveRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

_USER_ID = uuid.UUID("eeeeeeee-0000-0000-0000-000000000001")


async def _insert_org(uow: AsyncUnitOfWork, org_id: uuid.UUID, ws_id: uuid.UUID) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO organizations "
            "(id, workspace_id, name, org_type, is_active, version) "
            "VALUES (:id, :ws, 'Test Org', 'internal', true, 1) "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": org_id, "ws": ws_id},
    )


async def _insert_protocol(
    uow: AsyncUnitOfWork, protocol_id: uuid.UUID, ws_id: uuid.UUID
) -> None:
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
    uow: AsyncUnitOfWork, run_id: uuid.UUID, protocol_id: uuid.UUID, ws_id: uuid.UUID
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
            "run_date": date.today(),
            "user": _USER_ID,
            "notes": None,
        },
    )


async def _insert_readout_def(
    uow: AsyncUnitOfWork, rd_id: uuid.UUID, protocol_id: uuid.UUID
) -> None:
    """Seed a dose-response readout-def on the protocol so curves can FK to it.

    Minimal shape: a numeric-typed readout with no normalizations. The curve
    tests don't exercise the protocol-level DR config, only the curve row's
    FK identity.
    """
    await uow.session.execute(
        sa.text(
            "INSERT INTO readout_definitions "
            "(id, protocol_id, name, data_type, display_order, is_calculated) "
            "VALUES (:id, :proto, :name, 'numeric', 0, false)"
        ),
        {
            "id": rd_id,
            "proto": protocol_id,
            "name": f"Readout-{str(rd_id)[:8]}",
        },
    )


async def seed_curve(
    uow: AsyncUnitOfWork,
    *,
    workspace_id: uuid.UUID,
) -> DoseResponseCurve:
    """Insert prerequisite rows and save a minimal DoseResponseCurve.

    The caller is responsible for entering the UoW context (``async with uow:``).
    Returns the saved domain entity (id is set).
    """
    org_id = uuid.uuid4()
    protocol_id = uuid.uuid4()
    run_id = uuid.uuid4()
    readout_def_id = uuid.uuid4()

    await _insert_org(uow, org_id, workspace_id)
    await _insert_protocol(uow, protocol_id, workspace_id)
    await _insert_readout_def(uow, readout_def_id, protocol_id)
    await _insert_run(uow, run_id, protocol_id, workspace_id)

    curve = DoseResponseCurve(
        workspace_id=workspace_id,
        molecule_id=uuid.uuid4(),
        batch_id=uuid.uuid4(),
        protocol_id=protocol_id,
        run_id=run_id,
        readout_definition_id=readout_def_id,
        curve_type=CurveType.IC50,
        fitted_value=10.0,
        hill_slope=1.0,
        top=100.0,
        bottom=0.0,
        r_squared=0.95,
        num_points=5,
        raw_data=[],
    )

    repo = SQLAlchemyDoseResponseCurveRepository(uow)
    await repo.save(curve)
    return curve
