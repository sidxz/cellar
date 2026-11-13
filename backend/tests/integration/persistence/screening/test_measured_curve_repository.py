"""Integration tests: SQLAlchemyMeasuredCurveRepository against a migrated database."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from cellar.domain.screening_assay.enums import HolderKind
from cellar.domain.screening_assay.measured_curve import MeasuredCurve, ReportedPoint
from cellar.domain.screening_assay.run import Plate, Run, Well
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.measured_curve_repository import (  # noqa: E501
    SQLAlchemyMeasuredCurveRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.run_repository import (
    SQLAlchemyRunRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.fixtures.dose_response_curves import (
    _USER_ID,
    _insert_org,
    _insert_protocol,
    _insert_run,
)


async def _seed_run(session_factory, workspace_id) -> uuid.UUID:  # type: ignore[no-untyped-def]
    run_id = uuid.uuid4()
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        protocol_id = uuid.uuid4()
        await _insert_org(uow, uuid.uuid4(), workspace_id)
        await _insert_protocol(uow, protocol_id, workspace_id)
        await _insert_run(uow, run_id, protocol_id, workspace_id)
        await uow.commit()
    return run_id


def _curve(  # type: ignore[no-untyped-def]
    workspace_id,
    run_id,
    well_id,
    *,
    key="ratio",
    order=0,
    x=(25.0, 26.0, 27.0),
    y=(0.80, 0.81, 0.83),
    reported=(),
) -> MeasuredCurve:
    return MeasuredCurve(
        workspace_id=workspace_id,
        run_id=run_id,
        well_id=well_id,
        channel_key=key,
        channel_label=key.upper(),
        x_unit="°C",
        y_unit=None,
        channel_order=order,
        x=x,
        y=y,
        reported=reported,
        reader="test-reader",
    )


async def _save(session_factory, curves) -> None:  # type: ignore[no-untyped-def]
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await SQLAlchemyMeasuredCurveRepository(uow).save_bulk(curves)
        await uow.commit()


async def test_array_columns_round_trip(session_factory, workspace_id):
    run_id = await _seed_run(session_factory, workspace_id)
    x = tuple(25.0 + i * 0.057 for i in range(1223))
    y = tuple(0.8 + i * 1e-4 for i in range(1223))
    reported = (ReportedPoint("transition", 1, "T1", 61.5, "°C"),)
    await _save(
        session_factory, [_curve(workspace_id, run_id, uuid.uuid4(), x=x, y=y, reported=reported)]
    )

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        repo = SQLAlchemyMeasuredCurveRepository(uow)
        (got,) = await repo.find_by_run(workspace_id, run_id)
    assert got.x == x and got.y == y and isinstance(got.x, tuple)
    assert got.reported == (ReportedPoint("transition", 1, "T1", 61.5, "°C"),)


async def _seed_four_curves(session_factory, workspace_id) -> uuid.UUID:  # type: ignore[no-untyped-def]
    """Two wells x two channels (ratio first, f330 second)."""
    run_id = await _seed_run(session_factory, workspace_id)
    wells = [uuid.uuid4(), uuid.uuid4()]
    await _save(
        session_factory,
        [
            _curve(workspace_id, run_id, w, key=key, order=order)
            for key, order in (("f330", 1), ("ratio", 0))
            for w in wells
        ],
    )
    return run_id


async def test_unique_per_well_and_channel(session_factory, workspace_id):
    run_id = await _seed_run(session_factory, workspace_id)
    well_id = uuid.uuid4()
    await _save(session_factory, [_curve(workspace_id, run_id, well_id)])

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await SQLAlchemyMeasuredCurveRepository(uow).save_bulk(
            [_curve(workspace_id, run_id, well_id)]
        )
        with pytest.raises(IntegrityError):
            await uow.session.flush()


async def test_check_constraint_refuses_unequal_lengths(session_factory, workspace_id):
    run_id = await _seed_run(session_factory, workspace_id)
    async with session_factory() as session:
        with pytest.raises(IntegrityError, match="ck_measured_curve_points"):
            await session.execute(
                sa.text(
                    "INSERT INTO measured_curves (id, workspace_id, run_id, well_id, "
                    "channel_key, channel_label, x_unit, channel_order, x, y, reader) "
                    "VALUES (:id, :ws, :run, :well, 'ratio', 'Ratio', 'C', 0, "
                    "ARRAY[1.0, 2.0, 3.0], ARRAY[1.0, 2.0], 'test-reader')"
                ),
                {"id": uuid.uuid4(), "ws": workspace_id, "run": run_id, "well": uuid.uuid4()},
            )


async def test_find_by_run_filters_channel_and_workspace(session_factory, workspace_id):
    ws = workspace_id
    run_id = await _seed_four_curves(session_factory, ws)
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        repo = SQLAlchemyMeasuredCurveRepository(uow)
        assert len(await repo.find_by_run(ws, run_id)) == 4
        assert [c.channel_key for c in await repo.find_by_run(ws, run_id, channel_key="f330")] == [
            "f330",
            "f330",
        ]
        assert await repo.find_by_run(uuid.uuid4(), run_id) == []
        # Ordered by (channel_order, well_id).
        keys = [(c.channel_order, c.well_id) for c in await repo.find_by_run(ws, run_id)]
        assert keys == sorted(keys)


async def test_list_channels_is_ordered_by_channel_order(session_factory, workspace_id):
    ws = workspace_id
    run_id = await _seed_four_curves(session_factory, ws)
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        repo = SQLAlchemyMeasuredCurveRepository(uow)
        assert [(c.key, c.order) for c in await repo.list_channels(ws, run_id)] == [
            ("ratio", 0),
            ("f330", 1),
        ]


async def test_delete_by_run_returns_count_and_is_workspace_scoped(session_factory, workspace_id):
    ws = workspace_id
    run_id = await _seed_four_curves(session_factory, ws)
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        repo = SQLAlchemyMeasuredCurveRepository(uow)
        assert await repo.delete_by_run(uuid.uuid4(), run_id) == 0
        assert await repo.delete_by_run(ws, run_id) == 4
        await uow.commit()
    async with uow:
        assert await SQLAlchemyMeasuredCurveRepository(uow).find_by_run(ws, run_id) == []


async def _seed_protocol(session_factory, workspace_id) -> uuid.UUID:  # type: ignore[no-untyped-def]
    protocol_id = uuid.uuid4()
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await _insert_protocol(uow, protocol_id, workspace_id)
        await uow.commit()
    return protocol_id


async def _load_run(session_factory, workspace_id, run_id) -> Run:  # type: ignore[no-untyped-def]
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        loaded = await SQLAlchemyRunRepository(uow).find_by_id_in_workspace(workspace_id, run_id)
    assert loaded is not None
    return loaded


async def test_run_round_trips_holder_fields_and_well_label(session_factory, workspace_id):
    protocol_id = await _seed_protocol(session_factory, workspace_id)
    run = Run.create(
        workspace_id=workspace_id,
        protocol_id=protocol_id,
        run_date=date.today(),
        operator=_USER_ID,
    )
    cassette = Plate(
        run_id=run.id,
        plate_number=1,
        format=None,
        holder_kind=HolderKind.CASSETTE,
        holder_rows=1,
        holder_columns=48,
    )
    run.add_plate(cassette)
    run.wells.append(Well(plate_id=cassette.id, row="A", column=31, label="protein alone"))
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await SQLAlchemyRunRepository(uow).save(run)
        await uow.commit()

    loaded = await _load_run(session_factory, workspace_id, run.id)
    plate = loaded.plates[0]
    assert (plate.holder_kind, plate.holder_rows, plate.holder_columns, plate.format) == (
        HolderKind.CASSETTE,
        1,
        48,
        None,
    )
    assert loaded.wells[0].label == "protein alone"


async def test_run_round_trips_well_note(session_factory, workspace_id):
    protocol_id = await _seed_protocol(session_factory, workspace_id)
    run = Run.create(
        workspace_id=workspace_id,
        protocol_id=protocol_id,
        run_date=date.today(),
        operator=_USER_ID,
    )
    plate = Plate(run_id=run.id, plate_number=1)
    run.add_plate(plate)
    run.wells.append(Well(plate_id=plate.id, row="A", column=1, note="went cloudy"))
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await SQLAlchemyRunRepository(uow).save(run)
        await uow.commit()

    loaded = await _load_run(session_factory, workspace_id, run.id)
    assert loaded.wells[0].note == "went cloudy"


async def test_existing_plate_rows_read_as_plate_holders(session_factory, workspace_id):
    run_id = await _seed_run(session_factory, workspace_id)
    async with session_factory() as session:
        await session.execute(
            sa.text(
                "INSERT INTO plates (id, run_id, plate_number, format) VALUES (:id, :run, 1, '96')"
            ),
            {"id": uuid.uuid4(), "run": run_id},
        )
        await session.commit()

    loaded = await _load_run(session_factory, workspace_id, run_id)
    plate = loaded.plates[0]
    assert plate.holder_kind is HolderKind.PLATE and plate.holder_rows is None
