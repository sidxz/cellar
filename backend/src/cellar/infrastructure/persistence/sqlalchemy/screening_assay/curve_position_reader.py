"""SQLAlchemy implementation of CurvePositionReader. Never loads a curve's points."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import replace

from sqlalchemy import Select, distinct, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.application.screening.curve_position_reader import (
    CurvePosition,
    CurvePositions,
    CurveRun,
)
from cellar.domain.screening_assay.enums import HolderKind
from cellar.domain.screening_assay.holder import holder_label
from cellar.domain.screening_assay.measured_curve import CurveChannel
from cellar.domain.shared.enums import WellType
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import BatchModel
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    MeasuredCurveModel,
    PlateModel,
    ProtocolModel,
    RunModel,
    WellModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.plate_map_reader import (
    well_map_entries,
)


class SQLAlchemyCurvePositionReader:
    """Infrastructure-layer read model: a protocol's runs and positions with curves."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def find(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        *,
        run_ids: Sequence[uuid.UUID] = (),
        molecule_ids: Sequence[uuid.UUID] = (),
    ) -> CurvePositions | None:
        async with self._session_factory() as session:
            dose_unit = await session.scalar(
                select(ProtocolModel.dose_unit).where(
                    ProtocolModel.id == protocol_id,
                    ProtocolModel.workspace_id == workspace_id,
                )
            )
            if dose_unit is None:
                return None
            runs = await _runs(session, workspace_id, protocol_id)
            positions: tuple[CurvePosition, ...] = ()
            if run_ids or molecule_ids:
                order = {r.run_id: i for i, r in enumerate(runs)}
                positions = await _positions(
                    session, workspace_id, protocol_id, run_ids, molecule_ids, order
                )
        return CurvePositions(
            protocol_id=protocol_id, dose_unit=dose_unit, runs=runs, positions=positions
        )


async def _runs(
    session: AsyncSession, ws: uuid.UUID, protocol_id: uuid.UUID
) -> tuple[CurveRun, ...]:
    # One row per (run, holder) with curved positions; the run's holder is its first.
    holder_rows = await session.execute(
        select(
            RunModel.id,
            RunModel.run_date,
            RunModel.operator,
            RunModel.status,
            RunModel.notes,
            PlateModel.holder_kind,
            PlateModel.holder_rows,
            PlateModel.holder_columns,
            func.count(distinct(WellModel.id)),
        )
        .select_from(MeasuredCurveModel)
        .join(WellModel, WellModel.id == MeasuredCurveModel.well_id)
        .join(PlateModel, PlateModel.id == WellModel.plate_id)
        .join(RunModel, RunModel.id == PlateModel.run_id)
        .where(
            MeasuredCurveModel.workspace_id == ws,
            MeasuredCurveModel.run_id == RunModel.id,
            RunModel.workspace_id == ws,
            RunModel.protocol_id == protocol_id,
        )
        .group_by(RunModel.id, PlateModel.id)
        .order_by(
            RunModel.run_date.desc(),
            RunModel.created_at.desc(),
            RunModel.id,
            PlateModel.plate_number,
        )
    )
    channel_rows = await session.execute(
        select(
            MeasuredCurveModel.run_id,
            MeasuredCurveModel.channel_key,
            MeasuredCurveModel.channel_label,
            MeasuredCurveModel.x_unit,
            MeasuredCurveModel.y_unit,
            MeasuredCurveModel.channel_order,
            MeasuredCurveModel.x_label,
        )
        .distinct()
        .join(RunModel, RunModel.id == MeasuredCurveModel.run_id)
        .where(
            MeasuredCurveModel.workspace_id == ws,
            RunModel.workspace_id == ws,
            RunModel.protocol_id == protocol_id,
        )
        .order_by(MeasuredCurveModel.run_id, MeasuredCurveModel.channel_order)
    )
    channels: dict[uuid.UUID, list[CurveChannel]] = {}
    for run_id, key, label, x_unit, y_unit, order, x_label in channel_rows:
        channels.setdefault(run_id, []).append(
            CurveChannel(
                key=key, label=label, x_unit=x_unit, y_unit=y_unit, order=order, x_label=x_label
            )
        )

    runs: dict[uuid.UUID, CurveRun] = {}
    for run_id, run_date, operator, status, notes, kind, rows, columns, count in holder_rows:
        if run_id in runs:
            first = runs[run_id]
            runs[run_id] = replace(first, position_count=first.position_count + count)
            continue
        runs[run_id] = CurveRun(
            run_id=run_id,
            run_date=run_date,
            operator=operator,
            status=status,
            notes=notes,
            holder_kind=kind,
            holder_rows=rows,
            holder_columns=columns,
            holder_label=holder_label(HolderKind(kind), rows, columns),
            channels=tuple(channels.get(run_id, ())),
            position_count=count,
        )
    return tuple(runs.values())


async def _positions(
    session: AsyncSession,
    ws: uuid.UUID,
    protocol_id: uuid.UUID,
    run_ids: Sequence[uuid.UUID],
    molecule_ids: Sequence[uuid.UUID],
    run_order: dict[uuid.UUID, int],
) -> tuple[CurvePosition, ...]:
    curved: Select = (
        select(WellModel, PlateModel.run_id, PlateModel.plate_number, PlateModel.holder_kind)
        .join(PlateModel, PlateModel.id == WellModel.plate_id)
        .join(RunModel, RunModel.id == PlateModel.run_id)
        .where(
            RunModel.workspace_id == ws,
            RunModel.protocol_id == protocol_id,
            exists().where(
                MeasuredCurveModel.workspace_id == ws,
                MeasuredCurveModel.well_id == WellModel.id,
            ),
        )
    )
    matched = curved
    if run_ids:
        matched = matched.where(PlateModel.run_id.in_(run_ids))
    if molecule_ids:
        matched = matched.where(
            WellModel.batch_id.in_(
                select(BatchModel.id).where(
                    BatchModel.workspace_id == ws, BatchModel.molecule_id.in_(molecule_ids)
                )
            )
        )
    rows = {r[0].id: r for r in await session.execute(matched)}
    contributing = {r.run_id for r in rows.values()}
    if contributing:
        references = curved.where(
            PlateModel.run_id.in_(contributing), WellModel.well_type == WellType.REFERENCE.value
        )
        for r in await session.execute(references):
            rows.setdefault(r[0].id, r)

    ordered = sorted(
        rows.values(),
        key=lambda r: (run_order[r.run_id], r.plate_number, len(r[0].row), r[0].row, r[0].column),
    )
    entries = await well_map_entries(
        session, ws, [(r[0], HolderKind(r.holder_kind)) for r in ordered]
    )
    return tuple(
        CurvePosition(run_id=r.run_id, well=e) for r, e in zip(ordered, entries, strict=True)
    )
