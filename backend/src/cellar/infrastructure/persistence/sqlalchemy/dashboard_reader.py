"""SQLAlchemy implementation of the DashboardStatsReader protocol."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.application.dashboard.get_dashboard_stats import DashboardStats
from cellar.domain.screening_assay.enums import ProtocolStatus
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import (
    BatchModel,
    SampleModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    ProtocolModel,
    RunModel,
)


class SQLAlchemyDashboardReader:
    """Read-model reader for dashboard aggregate counts."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_stats(self, workspace_id: uuid.UUID) -> DashboardStats:
        async with self._session_factory() as session:
            compounds = await session.scalar(
                select(func.count())
                .select_from(MoleculeModel)
                .where(MoleculeModel.workspace_id == workspace_id)
            )
            batches = await session.scalar(
                select(func.count())
                .select_from(BatchModel)
                .where(BatchModel.workspace_id == workspace_id)
            )
            samples = await session.scalar(
                select(func.count())
                .select_from(SampleModel)
                .where(SampleModel.workspace_id == workspace_id)
            )
            protocols = await session.scalar(
                select(func.count())
                .select_from(ProtocolModel)
                .where(
                    ProtocolModel.workspace_id == workspace_id,
                    ProtocolModel.status == ProtocolStatus.ACTIVE,
                )
            )
            runs = await session.scalar(
                select(func.count())
                .select_from(RunModel)
                .where(RunModel.workspace_id == workspace_id)
            )

        return DashboardStats(
            total_compounds=compounds or 0,
            total_batches=batches or 0,
            total_samples=samples or 0,
            active_protocols=protocols or 0,
            total_runs=runs or 0,
        )
