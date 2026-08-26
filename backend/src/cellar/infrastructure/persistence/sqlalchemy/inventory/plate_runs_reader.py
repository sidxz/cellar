"""SQLAlchemy implementation of PlateRunsReader — plates → runs → protocols."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.application.inventory.plate_runs_reader import PlateRunRow
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    PlateModel,
    ProtocolModel,
    RunModel,
)


class SQLAlchemyPlateRunsReader:
    """Opens a fresh session per call — safe to register as a singleton."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def runs_for_plate(
        self, workspace_id: uuid.UUID, plate_id: uuid.UUID
    ) -> list[PlateRunRow]:
        # Column order == PlateRunRow field order (rows are splatted below).
        stmt = (
            select(
                RunModel.id,
                RunModel.run_date,
                RunModel.status,
                ProtocolModel.id,
                ProtocolModel.name,
                PlateModel.plate_number,
                RunModel.created_at,
            )
            .select_from(PlateModel)
            .join(RunModel, RunModel.id == PlateModel.run_id)
            .join(ProtocolModel, ProtocolModel.id == RunModel.protocol_id)
            .where(
                PlateModel.registered_plate_id == plate_id,
                RunModel.workspace_id == workspace_id,
            )
            .order_by(RunModel.created_at.desc(), PlateModel.plate_number)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return [PlateRunRow(*row) for row in rows]
