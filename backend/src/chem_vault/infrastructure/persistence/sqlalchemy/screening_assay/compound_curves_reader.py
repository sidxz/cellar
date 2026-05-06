"""SQLAlchemy implementation of CompoundCurvesReader."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chem_vault.application.screening.compound_curves_reader import CurveRow
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    DoseResponseCurveModel,
    RunModel,
)


class SQLAlchemyCompoundCurvesReader:
    """Infrastructure-layer read model for compound curves queries."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_curves(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        molecule_id: uuid.UUID,
    ) -> list[CurveRow]:
        async with self._session_factory() as session:
            stmt = (
                select(DoseResponseCurveModel)
                .join(RunModel, DoseResponseCurveModel.run_id == RunModel.id)
                .where(
                    DoseResponseCurveModel.protocol_id == protocol_id,
                    DoseResponseCurveModel.molecule_id == molecule_id,
                    RunModel.workspace_id == workspace_id,
                )
                .order_by(RunModel.run_date.desc())
            )
            rows = (await session.execute(stmt)).scalars().all()

            return [
                CurveRow(
                    id=r.id,
                    workspace_id=r.workspace_id,
                    molecule_id=r.molecule_id,
                    batch_id=r.batch_id,
                    protocol_id=r.protocol_id,
                    run_id=r.run_id,
                    curve_type=r.curve_type,
                    fitted_value=r.fitted_value,
                    hill_slope=r.hill_slope,
                    top=r.top,
                    bottom=r.bottom,
                    r_squared=r.r_squared,
                    confidence_interval_low=r.confidence_interval_low,
                    confidence_interval_high=r.confidence_interval_high,
                    num_points=r.num_points,
                    curve_class=r.curve_class,
                    raw_data=r.raw_data,
                    excluded_points=r.excluded_points,
                )
                for r in rows
            ]
