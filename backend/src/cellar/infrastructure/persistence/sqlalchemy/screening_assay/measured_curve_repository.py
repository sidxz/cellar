"""SQLAlchemy repository for MeasuredCurve entities.

MeasuredCurve is not an AggregateRoot: written once with the run's import,
removed with the run or on data reset. Standalone repo with manual CRUD.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict

from sqlalchemy import delete, select

from cellar.domain.screening_assay.measured_curve import (
    CurveChannel,
    MeasuredCurve,
    ReportedPoint,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    MeasuredCurveModel,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyMeasuredCurveRepository:
    """Persists MeasuredCurve entities to PostgreSQL."""

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def save_bulk(self, curves: list[MeasuredCurve]) -> None:
        self._uow.session.add_all([self._to_model(c) for c in curves])

    async def find_by_run(
        self,
        workspace_id: uuid.UUID,
        run_id: uuid.UUID,
        *,
        channel_key: str | None = None,
    ) -> list[MeasuredCurve]:
        stmt = select(MeasuredCurveModel).where(
            MeasuredCurveModel.workspace_id == workspace_id,
            MeasuredCurveModel.run_id == run_id,
        )
        if channel_key is not None:
            stmt = stmt.where(MeasuredCurveModel.channel_key == channel_key)
        stmt = stmt.order_by(MeasuredCurveModel.channel_order, MeasuredCurveModel.well_id)
        result = await self._uow.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_channels(
        self, workspace_id: uuid.UUID, run_id: uuid.UUID
    ) -> list[CurveChannel]:
        stmt = (
            select(
                MeasuredCurveModel.channel_key,
                MeasuredCurveModel.channel_label,
                MeasuredCurveModel.x_unit,
                MeasuredCurveModel.y_unit,
                MeasuredCurveModel.channel_order,
            )
            .distinct()
            .where(
                MeasuredCurveModel.workspace_id == workspace_id,
                MeasuredCurveModel.run_id == run_id,
            )
            .order_by(MeasuredCurveModel.channel_order)
        )
        result = await self._uow.session.execute(stmt)
        return [
            CurveChannel(key=key, label=label, x_unit=x_unit, y_unit=y_unit, order=order)
            for key, label, x_unit, y_unit, order in result.all()
        ]

    async def delete_by_run(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> int:
        stmt = delete(MeasuredCurveModel).where(
            MeasuredCurveModel.workspace_id == workspace_id,
            MeasuredCurveModel.run_id == run_id,
        )
        result = await self._uow.session.execute(stmt)
        return result.rowcount or 0

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _to_domain(model: MeasuredCurveModel) -> MeasuredCurve:
        return MeasuredCurve(
            id=model.id,
            workspace_id=model.workspace_id,
            run_id=model.run_id,
            well_id=model.well_id,
            channel_key=model.channel_key,
            channel_label=model.channel_label,
            x_unit=model.x_unit,
            y_unit=model.y_unit,
            channel_order=model.channel_order,
            x=tuple(model.x),
            y=tuple(model.y),
            reported=tuple(ReportedPoint(**r) for r in model.reported),
            reader=model.reader,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_model(entity: MeasuredCurve) -> MeasuredCurveModel:
        return MeasuredCurveModel(
            id=entity.id,
            workspace_id=entity.workspace_id,
            run_id=entity.run_id,
            well_id=entity.well_id,
            channel_key=entity.channel_key,
            channel_label=entity.channel_label,
            x_unit=entity.x_unit,
            y_unit=entity.y_unit,
            channel_order=entity.channel_order,
            x=list(entity.x),
            y=list(entity.y),
            reported=[asdict(r) for r in entity.reported],
            reader=entity.reader,
        )
