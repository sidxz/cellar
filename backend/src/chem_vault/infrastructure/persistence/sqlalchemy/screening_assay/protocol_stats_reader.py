"""SQLAlchemy implementation of ProtocolStatsReader."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chem_vault.application.screening.protocol_stats_reader import (
    LatestRunRow,
    ProtocolStatsData,
    ProtocolStatsRow,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    PlateModel,
    ProtocolModel,
    ReadoutDataModel,
    RunModel,
)


class SQLAlchemyProtocolStatsReader:
    """Infrastructure-layer read model for protocol stats queries."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_stats_data(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID
    ) -> ProtocolStatsData:
        ws = workspace_id
        pid = protocol_id

        async with self._session_factory() as session:
            # 1. Verify protocol exists in workspace
            protocol_stmt = select(
                ProtocolModel.id,
                ProtocolModel.recommended_hit_criteria,
            ).where(
                ProtocolModel.id == pid,
                ProtocolModel.workspace_id == ws,
            )
            protocol_row = (
                await session.execute(protocol_stmt)
            ).one_or_none()

            if protocol_row is None:
                return ProtocolStatsData(
                    protocol=None,
                    status_counts={},
                    compound_count=0,
                    latest_run=None,
                )

            protocol = ProtocolStatsRow(
                id=protocol_row.id,
                recommended_hit_criteria=protocol_row.recommended_hit_criteria,
            )

            # 2. Run counts by status
            status_counts_stmt = (
                select(RunModel.status, func.count())
                .where(
                    RunModel.protocol_id == pid,
                    RunModel.workspace_id == ws,
                )
                .group_by(RunModel.status)
            )
            status_rows = (await session.execute(status_counts_stmt)).all()
            status_counts: dict[str, int] = {
                row[0]: row[1] for row in status_rows
            }

            # 3. Unique compound count across all runs for this protocol
            compound_count_stmt = (
                select(
                    func.count(func.distinct(ReadoutDataModel.molecule_id))
                )
                .select_from(ReadoutDataModel)
                .join(RunModel, ReadoutDataModel.run_id == RunModel.id)
                .where(
                    RunModel.protocol_id == pid,
                    RunModel.workspace_id == ws,
                    ReadoutDataModel.molecule_id.isnot(None),
                )
            )
            compound_count = (
                await session.execute(compound_count_stmt)
            ).scalar_one()

            # 4. Latest run by run_date
            latest_run_stmt = (
                select(
                    RunModel.id,
                    RunModel.run_date,
                    RunModel.status,
                    RunModel.plate_format,
                    RunModel.qc_metrics,
                )
                .where(
                    RunModel.protocol_id == pid,
                    RunModel.workspace_id == ws,
                )
                .order_by(RunModel.run_date.desc(), RunModel.created_at.desc())
                .limit(1)
            )
            latest_run_row = (
                await session.execute(latest_run_stmt)
            ).one_or_none()

            latest_run: LatestRunRow | None = None
            if latest_run_row is not None:
                run_id = latest_run_row.id

                # Plate count for the latest run
                plate_count_stmt = (
                    select(func.count())
                    .select_from(PlateModel)
                    .where(PlateModel.run_id == run_id)
                )
                plate_count = (
                    await session.execute(plate_count_stmt)
                ).scalar_one()

                # Compound count for the latest run
                run_compound_stmt = (
                    select(
                        func.count(
                            func.distinct(ReadoutDataModel.molecule_id)
                        )
                    )
                    .select_from(ReadoutDataModel)
                    .where(
                        ReadoutDataModel.run_id == run_id,
                        ReadoutDataModel.molecule_id.isnot(None),
                    )
                )
                run_compound_count = (
                    await session.execute(run_compound_stmt)
                ).scalar_one()

                latest_run = LatestRunRow(
                    id=run_id,
                    run_date=latest_run_row.run_date,
                    status=latest_run_row.status,
                    plate_format=latest_run_row.plate_format,
                    qc_metrics=latest_run_row.qc_metrics,
                    plate_count=plate_count,
                    compound_count=run_compound_count,
                )

        return ProtocolStatsData(
            protocol=protocol,
            status_counts=status_counts,
            compound_count=compound_count,
            latest_run=latest_run,
        )
