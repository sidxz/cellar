"""Integration tests: SQLAlchemyCurvePositionReader (and the protocol curves flag)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

import sqlalchemy as sa

from cellar.domain.screening_assay.enums import HolderKind
from cellar.domain.screening_assay.holder import holder_label, position_label
from cellar.domain.screening_assay.measured_curve import MeasuredCurve
from cellar.domain.screening_assay.run import Plate, Run, Well
from cellar.domain.shared.enums import WellType
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.curve_position_reader import (
    SQLAlchemyCurvePositionReader,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.measured_curve_repository import (  # noqa: E501
    SQLAlchemyMeasuredCurveRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.run_repository import (
    SQLAlchemyRunRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.fixtures.dose_response_curves import _USER_ID, _insert_org, _insert_protocol


@dataclass(frozen=True)
class Seed:
    protocol_id: uuid.UUID
    other_protocol_id: uuid.UUID
    run_a: uuid.UUID
    run_b: uuid.UUID
    run_c: uuid.UUID
    run_d: uuid.UUID
    run_e: uuid.UUID
    compound_x: uuid.UUID
    compound_y: uuid.UUID
    batch_x: uuid.UUID
    reg_x: str
    uncurved_well: uuid.UUID


async def _insert_compound(uow: AsyncUnitOfWork, ws: uuid.UUID, org_id: uuid.UUID, name: str):  # type: ignore[no-untyped-def]
    molecule_id, batch_id = uuid.uuid4(), uuid.uuid4()
    reg = f"REG-{uuid.uuid4().hex[:8]}"
    await uow.session.execute(
        sa.text(
            "INSERT INTO molecules "
            "(id, workspace_id, name, molecule_type, structure_status, "
            "registration_status, synthesis_status, lifecycle_stage, "
            "registration_number, originating_org_id, version) "
            "VALUES (:id, :ws, :name, 'small_molecule', 'undisclosed', "
            "'approved', 'virtual', 'registered', :reg, :org, 1)"
        ),
        {"id": molecule_id, "ws": ws, "name": name, "reg": reg, "org": org_id},
    )
    await uow.session.execute(
        sa.text(
            "INSERT INTO batches (id, workspace_id, molecule_id, batch_number, "
            "amount_value, amount_unit, source, chemist, version) "
            "VALUES (:id, :ws, :mol, :bn, 1.0, 'mg', 'synthesized', :chem, 1)"
        ),
        {"id": batch_id, "ws": ws, "mol": molecule_id, "bn": f"B-{name}", "chem": uuid.uuid4()},
    )
    return molecule_id, batch_id, reg


def _run(  # type: ignore[no-untyped-def]
    ws, protocol_id, run_date, *, batch_x, batch_y, columns=3, curved=True
):
    """A run with a cassette of positions 1 reference, 2 compound X, 3 compound Y
    (and 4, compound X, without curves, when ``columns`` is 4)."""
    run = Run.create(
        workspace_id=ws, protocol_id=protocol_id, run_date=run_date, operator=_USER_ID
    )
    holder = Plate(
        run_id=run.id,
        plate_number=1,
        holder_kind=HolderKind.CASSETTE,
        holder_rows=1,
        holder_columns=columns,
    )
    run.add_plate(holder)
    wells = [
        Well(plate_id=holder.id, row="A", column=1, well_type=WellType.REFERENCE),
        Well(
            plate_id=holder.id,
            row="A",
            column=2,
            batch_id=batch_x,
            dose=10.0,
            label="sample x",
            note="went cloudy",
        ),
        Well(plate_id=holder.id, row="A", column=3, batch_id=batch_y, dose=10.0),
    ]
    if columns == 4:
        wells.append(Well(plate_id=holder.id, row="A", column=4, batch_id=batch_x))
    run.wells.extend(wells)
    curves = (
        [
            MeasuredCurve(
                workspace_id=ws,
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
            for w in wells[:3]
        ]
        if curved
        else []
    )
    return run, curves, wells


async def _seed(session_factory, ws) -> Seed:  # type: ignore[no-untyped-def]
    protocol_id, other_protocol_id, org_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    today = date.today()
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await _insert_org(uow, org_id, ws)
        await _insert_protocol(uow, protocol_id, ws)
        await _insert_protocol(uow, other_protocol_id, ws)
        compound_x, batch_x, reg_x = await _insert_compound(uow, ws, org_id, "X")
        compound_y, batch_y, _ = await _insert_compound(uow, ws, org_id, "Y")
        await uow.commit()

    batches = dict(batch_x=batch_x, batch_y=batch_y)
    made = [
        _run(ws, protocol_id, today - timedelta(days=2), columns=4, **batches),
        _run(ws, protocol_id, today, **batches),
        _run(ws, protocol_id, today, **batches),
        _run(ws, protocol_id, today, curved=False, **batches),
        _run(ws, other_protocol_id, today, **batches),
    ]
    # One transaction per run, so created_at orders runs of the same date.
    for run, curves, _ in made:
        async with uow:
            await SQLAlchemyRunRepository(uow).save(run)
            await uow.session.flush()
            await SQLAlchemyMeasuredCurveRepository(uow).save_bulk(curves)
            await uow.commit()

    a, b, c, d, e = (r.id for r, _, _ in made)
    return Seed(
        protocol_id=protocol_id,
        other_protocol_id=other_protocol_id,
        run_a=a,
        run_b=b,
        run_c=c,
        run_d=d,
        run_e=e,
        compound_x=compound_x,
        compound_y=compound_y,
        batch_x=batch_x,
        reg_x=reg_x,
        uncurved_well=made[0][2][3].id,
    )


async def test_runs_lists_only_this_protocols_runs_with_curves_newest_first(
    session_factory, workspace_id
):
    s = await _seed(session_factory, workspace_id)
    out = await SQLAlchemyCurvePositionReader(session_factory).find(workspace_id, s.protocol_id)
    assert out is not None and out.protocol_id == s.protocol_id and out.dose_unit == "uM"
    assert [r.run_id for r in out.runs] == [s.run_c, s.run_b, s.run_a]
    first = out.runs[0]
    assert first.position_count == 3 and [c.key for c in first.channels] == ["ratio", "f330"]
    assert first.holder_label == holder_label(HolderKind.CASSETTE, 1, 3)
    assert (first.holder_kind, first.holder_rows, first.holder_columns) == ("cassette", 1, 3)
    assert (first.run_date, first.operator, first.status) == (date.today(), _USER_ID, "draft")
    assert out.runs[-1].position_count == 3  # the uncurved fourth position does not count


async def test_no_filter_returns_no_positions(session_factory, workspace_id):
    s = await _seed(session_factory, workspace_id)
    out = await SQLAlchemyCurvePositionReader(session_factory).find(workspace_id, s.protocol_id)
    assert out is not None and out.positions == ()


async def test_run_filter_returns_those_runs_positions_in_holder_order(
    session_factory, workspace_id
):
    s = await _seed(session_factory, workspace_id)
    out = await SQLAlchemyCurvePositionReader(session_factory).find(
        workspace_id, s.protocol_id, run_ids=[s.run_a, s.run_d, s.run_e]
    )
    assert out is not None
    assert [(p.run_id, p.well.column) for p in out.positions] == [
        (s.run_a, 1),
        (s.run_a, 2),
        (s.run_a, 3),
    ]


async def test_positions_follow_the_run_order_then_the_holder(session_factory, workspace_id):
    s = await _seed(session_factory, workspace_id)
    out = await SQLAlchemyCurvePositionReader(session_factory).find(
        workspace_id, s.protocol_id, run_ids=[s.run_a, s.run_c]
    )
    assert out is not None
    assert [(p.run_id, p.well.column) for p in out.positions] == [
        (s.run_c, 1),
        (s.run_c, 2),
        (s.run_c, 3),
        (s.run_a, 1),
        (s.run_a, 2),
        (s.run_a, 3),
    ]


async def test_compound_filter_returns_that_compounds_positions_and_each_runs_references(
    session_factory, workspace_id
):
    s = await _seed(session_factory, workspace_id)
    out = await SQLAlchemyCurvePositionReader(session_factory).find(
        workspace_id, s.protocol_id, molecule_ids=[s.compound_x]
    )
    assert out is not None
    assert sorted(
        (p.well.well_type, p.well.column) for p in out.positions if p.run_id == s.run_a
    ) == [
        ("reference", 1),
        ("sample", 2),
    ]
    assert {p.run_id for p in out.positions} == {s.run_a, s.run_b, s.run_c}


async def test_both_filters_narrow_to_the_compound_within_the_runs(session_factory, workspace_id):
    s = await _seed(session_factory, workspace_id)
    out = await SQLAlchemyCurvePositionReader(session_factory).find(
        workspace_id, s.protocol_id, run_ids=[s.run_b], molecule_ids=[s.compound_y]
    )
    assert out is not None
    assert [(p.run_id, p.well.well_type, p.well.column) for p in out.positions] == [
        (s.run_b, "reference", 1),
        (s.run_b, "sample", 3),
    ]


async def test_a_position_without_any_curve_is_left_out(session_factory, workspace_id):
    s = await _seed(session_factory, workspace_id)
    reader = SQLAlchemyCurvePositionReader(session_factory)
    for kwargs in ({"run_ids": [s.run_a]}, {"molecule_ids": [s.compound_x]}):
        out = await reader.find(workspace_id, s.protocol_id, **kwargs)
        assert out is not None
        assert s.uncurved_well not in {p.well.well_id for p in out.positions}


async def test_position_carries_label_note_batch_compound_and_registration_number(
    session_factory, workspace_id
):
    s = await _seed(session_factory, workspace_id)
    out = await SQLAlchemyCurvePositionReader(session_factory).find(
        workspace_id, s.protocol_id, run_ids=[s.run_b]
    )
    assert out is not None
    well = next(p.well for p in out.positions if p.well.column == 2)
    assert (well.label, well.note, well.dose) == ("sample x", "went cloudy", 10.0)
    assert (well.batch_id, well.batch_number) == (s.batch_x, "B-X")
    assert (well.molecule_id, well.molecule_name, well.registration_number) == (
        s.compound_x,
        "X",
        s.reg_x,
    )
    assert well.position_label == position_label(HolderKind.CASSETTE, "A", 2)


async def test_other_workspace_or_unknown_protocol_is_none(session_factory, workspace_id):
    s = await _seed(session_factory, workspace_id)
    reader = SQLAlchemyCurvePositionReader(session_factory)
    assert await reader.find(uuid.uuid4(), s.protocol_id, run_ids=[s.run_a]) is None
    assert await reader.find(workspace_id, uuid.uuid4()) is None
