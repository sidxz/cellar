"""GetProtocolStats query use case — dashboard metrics for a single protocol."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from returns.result import Failure, Result, Success
from sqlalchemy import func, select

from chem_vault.application.auth import AuthContext
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class ProtocolStatsQuery(Query):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID


@dataclass(frozen=True)
class RunCounts:
    total: int
    draft: int
    in_progress: int
    completed: int
    approved: int
    rejected: int


@dataclass(frozen=True)
class LatestRunInfo:
    id: uuid.UUID
    run_date: date
    status: str
    plate_format: str | None
    plate_count: int
    compound_count: int
    z_prime: float | None


@dataclass(frozen=True)
class ProtocolStats:
    run_counts: RunCounts
    compound_count: int
    hit_count: int | None  # None if no criteria set
    hit_criteria_applied: bool
    latest_run: LatestRunInfo | None


class GetProtocolStats:
    """Return dashboard summary metrics for a single protocol.

    Uses raw SA queries (read-model approach) rather than loading full
    aggregates, since we only need counts and a latest-run snapshot.
    """

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def __call__(
        self,
        input: ProtocolStatsQuery,
        auth: AuthContext | None = None,
    ) -> Result[ProtocolStats, DomainError]:
        # Deferred imports — these are infra models, only used inside the
        # read-model query.  Keeps the module importable without a DB.
        from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models import (
            PlateModel,
            ProtocolModel,
            ReadoutDataModel,
            RunModel,
        )

        async with self._uow as uow:
            session = uow.session  # type: ignore[union-attr]
            ws = input.workspace_id
            pid = input.protocol_id

            # 1. Verify protocol exists in workspace
            protocol_stmt = select(
                ProtocolModel.id,
                ProtocolModel.recommended_hit_criteria,
            ).where(
                ProtocolModel.id == pid,
                ProtocolModel.workspace_id == ws,
            )
            protocol_row = (await session.execute(protocol_stmt)).one_or_none()
            if protocol_row is None:
                return Failure(
                    NotFoundError(f"Protocol {pid} not found in workspace")
                )

            hit_criteria = protocol_row.recommended_hit_criteria
            hit_criteria_applied = bool(hit_criteria)

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
            counts_map: dict[str, int] = {row[0]: row[1] for row in status_rows}

            run_counts = RunCounts(
                total=sum(counts_map.values()),
                draft=counts_map.get("draft", 0),
                in_progress=counts_map.get("in_progress", 0),
                completed=counts_map.get("completed", 0),
                approved=counts_map.get("approved", 0),
                rejected=counts_map.get("rejected", 0),
            )

            # 3. Unique compound count across all runs for this protocol
            compound_count_stmt = (
                select(func.count(func.distinct(ReadoutDataModel.molecule_id)))
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
                select(RunModel.id, RunModel.run_date, RunModel.status, RunModel.plate_format, RunModel.qc_metrics)
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

            latest_run: LatestRunInfo | None = None
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
                    select(func.count(func.distinct(ReadoutDataModel.molecule_id)))
                    .select_from(ReadoutDataModel)
                    .where(
                        ReadoutDataModel.run_id == run_id,
                        ReadoutDataModel.molecule_id.isnot(None),
                    )
                )
                run_compound_count = (
                    await session.execute(run_compound_stmt)
                ).scalar_one()

                # Z-prime from qc_metrics JSONB
                z_prime: float | None = None
                qc_metrics = latest_run_row.qc_metrics
                if qc_metrics and isinstance(qc_metrics, dict):
                    z_prime = qc_metrics.get("z_prime")

                latest_run = LatestRunInfo(
                    id=run_id,
                    run_date=latest_run_row.run_date,
                    status=latest_run_row.status,
                    plate_format=latest_run_row.plate_format,
                    plate_count=plate_count,
                    compound_count=run_compound_count,
                    z_prime=z_prime,
                )

            # 5. hit_count: None for now (computed client-side)
            hit_count: int | None = None

            return Success(
                ProtocolStats(
                    run_counts=run_counts,
                    compound_count=compound_count,
                    hit_count=hit_count,
                    hit_criteria_applied=hit_criteria_applied,
                    latest_run=latest_run,
                )
            )
