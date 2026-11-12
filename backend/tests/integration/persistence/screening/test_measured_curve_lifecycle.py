"""Integration tests: measured curves survive an ordinary run save and go with reset or delete."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text

from cellar.application.screening.delete_run import DeleteRun, DeleteRunCommand
from cellar.application.screening.reset_run_data import ResetRunData, ResetRunDataCommand
from cellar.domain.screening_assay.enums import HolderKind
from cellar.domain.screening_assay.measured_curve import MeasuredCurve
from cellar.domain.screening_assay.run import Plate, Run, Well
from cellar.infrastructure.messaging.event_dispatcher import EventDispatcher
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (  # noqa: E501
    SQLAlchemyDoseResponseCurveRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.measured_curve_repository import (  # noqa: E501
    SQLAlchemyMeasuredCurveRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.readout_data_repository import (
    SQLAlchemyReadoutDataRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.run_repository import (
    SQLAlchemyRunRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.fakes.fake_auth import FakeAuth
from tests.fixtures.dose_response_curves import _USER_ID, _insert_protocol


async def _run_with_curves(session_factory, workspace_id):  # type: ignore[no-untyped-def]
    """Save a run with one cassette plate, 3 wells and 2 channels x 3 curves."""
    protocol_id = uuid.uuid4()
    run = Run.create(
        workspace_id=workspace_id,
        protocol_id=protocol_id,
        run_date=date.today(),
        operator=_USER_ID,
    )
    cassette = Plate(
        run_id=run.id,
        plate_number=1,
        holder_kind=HolderKind.CASSETTE,
        holder_rows=1,
        holder_columns=48,
    )
    run.add_plate(cassette)
    wells = [Well(plate_id=cassette.id, row="A", column=n) for n in (1, 2, 3)]
    run.wells.extend(wells)
    curves = [
        MeasuredCurve(
            workspace_id=workspace_id,
            run_id=run.id,
            well_id=w.id,
            channel_key=key,
            channel_label=key,
            x_unit="°C",
            y_unit=None,
            channel_order=order,
            x=(20.0, 21.0, 22.0),
            y=(0.1, 0.2, 0.3),
            reader="test-reader",
        )
        for key, order in (("ratio", 0), ("f330", 1))
        for w in wells
    ]
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await _insert_protocol(uow, protocol_id, workspace_id)
        await SQLAlchemyRunRepository(uow).save(run)
        await uow.session.flush()  # no ORM relationship orders the run before its curves
        await SQLAlchemyMeasuredCurveRepository(uow).save_bulk(curves)
        await uow.commit()
    return run.id, [w.id for w in wells]


def _repos(uow):  # type: ignore[no-untyped-def]
    return dict(
        uow=uow,
        run_repo=SQLAlchemyRunRepository(uow),
        readout_data_repo=SQLAlchemyReadoutDataRepository(uow),
        curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
        dispatcher=EventDispatcher(),
    )


async def test_run_save_keeps_every_curve(session_factory, workspace_id):
    run_id, well_ids = await _run_with_curves(session_factory, workspace_id)

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        run_repo = SQLAlchemyRunRepository(uow)
        run = await run_repo.find_by_id_in_workspace(workspace_id, run_id)
        assert run is not None
        run.update(notes="edited")
        await run_repo.save(run)
        await uow.commit()

    async with uow:
        curve_repo = SQLAlchemyMeasuredCurveRepository(uow)
        run_repo = SQLAlchemyRunRepository(uow)
        after = await curve_repo.find_by_run(workspace_id, run_id)
        assert len(after) == 6 and {c.well_id for c in after} == set(well_ids)
        reloaded = await run_repo.find_by_id_in_workspace(workspace_id, run_id)
        assert reloaded is not None
        assert {w.id for w in reloaded.wells} == set(well_ids)


async def test_reset_run_data_leaves_no_curves(session_factory, workspace_id):
    run_id, _ = await _run_with_curves(session_factory, workspace_id)

    uow = AsyncUnitOfWork(session_factory)
    uc = ResetRunData(**_repos(uow), measured_curve_repo=SQLAlchemyMeasuredCurveRepository(uow))
    result = await uc(
        ResetRunDataCommand(workspace_id=workspace_id, run_id=run_id),
        auth=FakeAuth(workspace_id=workspace_id),
    )

    assert result.unwrap().measured_curves_deleted == 6
    async with uow:
        curve_repo = SQLAlchemyMeasuredCurveRepository(uow)
        assert await curve_repo.find_by_run(workspace_id, run_id) == []


async def test_delete_run_leaves_no_curves(session_factory, workspace_id):
    run_id, _ = await _run_with_curves(session_factory, workspace_id)

    uc = DeleteRun(**_repos(AsyncUnitOfWork(session_factory)))
    result = await uc(
        DeleteRunCommand(workspace_id=workspace_id, run_id=run_id),
        auth=FakeAuth(workspace_id=workspace_id),
    )

    assert result.unwrap() is None
    async with session_factory() as session:
        count = await session.execute(
            text("SELECT count(*) FROM measured_curves WHERE run_id = :r"), {"r": run_id}
        )
        assert count.scalar() == 0
