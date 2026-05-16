"""Integration tests for DoseResponseCurveRepository.find_all_curves_for_molecules.

Verifies SQL filtering by run_scope (all / last_n / since / between),
correct grouping by (mol, rd), and run_date desc ordering.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa

from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.enums import CurveType
from cellar.domain.screening_assay.run_scope import RunScope
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


async def _insert_readout_def(
    uow: AsyncUnitOfWork, rd_id: uuid.UUID, protocol_id: uuid.UUID
) -> None:
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


async def _insert_run(
    uow: AsyncUnitOfWork,
    run_id: uuid.UUID,
    protocol_id: uuid.UUID,
    ws_id: uuid.UUID,
    run_date: date,
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
            "run_date": run_date,
            "user": _USER_ID,
            "notes": None,
        },
    )


async def _save_curve(
    uow: AsyncUnitOfWork,
    *,
    workspace_id: uuid.UUID,
    protocol_id: uuid.UUID,
    run_id: uuid.UUID,
    molecule_id: uuid.UUID,
    readout_definition_id: uuid.UUID,
) -> DoseResponseCurve:
    curve = DoseResponseCurve(
        workspace_id=workspace_id,
        molecule_id=molecule_id,
        batch_id=uuid.uuid4(),
        protocol_id=protocol_id,
        run_id=run_id,
        readout_definition_id=readout_definition_id,
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


async def _seed_three_runs(
    uow: AsyncUnitOfWork, workspace_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID, list[tuple[date, DoseResponseCurve]]]:
    """Seed one protocol + one readout-def + one molecule with curves across 3 runs.

    Returns (molecule_id, readout_definition_id, [(run_date, curve), ...]).
    """
    org_id = uuid.uuid4()
    protocol_id = uuid.uuid4()
    readout_def_id = uuid.uuid4()
    molecule_id = uuid.uuid4()

    await _insert_org(uow, org_id, workspace_id)
    await _insert_protocol(uow, protocol_id, workspace_id)
    await _insert_readout_def(uow, readout_def_id, protocol_id)

    # Insert curves out-of-order on purpose so the desc-sort assertion is meaningful.
    seeded: list[tuple[date, DoseResponseCurve]] = []
    for run_date in (date(2026, 1, 1), date(2026, 4, 1), date(2026, 2, 1)):
        run_id = uuid.uuid4()
        await _insert_run(uow, run_id, protocol_id, workspace_id, run_date)
        curve = await _save_curve(
            uow,
            workspace_id=workspace_id,
            protocol_id=protocol_id,
            run_id=run_id,
            molecule_id=molecule_id,
            readout_definition_id=readout_def_id,
        )
        seeded.append((run_date, curve))

    return molecule_id, readout_def_id, seeded


@pytest.mark.asyncio
class TestFindAllCurves:
    async def test_returns_all_runs_sorted_desc(self, uow, workspace_id):
        """Three runs of the same protocol on the same compound → 3 curves, newest first."""
        async with uow:
            mol_id, rd_id, seeded = await _seed_three_runs(uow, workspace_id)
            await uow.commit()

        repo = SQLAlchemyDoseResponseCurveRepository(uow)
        async with uow:
            grouped = await repo.find_all_curves_for_molecules(
                workspace_id, [mol_id]
            )

        assert mol_id in grouped
        assert rd_id in grouped[mol_id]
        curves = grouped[mol_id][rd_id]
        assert len(curves) == 3
        # Map curve.id -> seeded run_date
        date_by_id = {c.id: d for d, c in seeded}
        actual_dates = [date_by_id[c.id] for c in curves]
        assert actual_dates == [date(2026, 4, 1), date(2026, 2, 1), date(2026, 1, 1)]

    async def test_honors_last_n(self, uow, workspace_id):
        """RunScope.last_n(2) caps to the 2 most recent runs PER (mol, rd)."""
        async with uow:
            mol_id, rd_id, seeded = await _seed_three_runs(uow, workspace_id)
            await uow.commit()

        repo = SQLAlchemyDoseResponseCurveRepository(uow)
        async with uow:
            grouped = await repo.find_all_curves_for_molecules(
                workspace_id, [mol_id], run_scope=RunScope.last_n(2)
            )

        curves = grouped[mol_id][rd_id]
        assert len(curves) == 2
        date_by_id = {c.id: d for d, c in seeded}
        actual_dates = [date_by_id[c.id] for c in curves]
        assert actual_dates == [date(2026, 4, 1), date(2026, 2, 1)]

    async def test_honors_since(self, uow, workspace_id):
        """RunScope.since(2026-03-01) drops the Jan and Feb curves."""
        async with uow:
            mol_id, rd_id, seeded = await _seed_three_runs(uow, workspace_id)
            await uow.commit()

        repo = SQLAlchemyDoseResponseCurveRepository(uow)
        async with uow:
            grouped = await repo.find_all_curves_for_molecules(
                workspace_id, [mol_id], run_scope=RunScope.since(date(2026, 3, 1))
            )

        curves = grouped[mol_id][rd_id]
        assert len(curves) == 1
        date_by_id = {c.id: d for d, c in seeded}
        assert date_by_id[curves[0].id] == date(2026, 4, 1)
