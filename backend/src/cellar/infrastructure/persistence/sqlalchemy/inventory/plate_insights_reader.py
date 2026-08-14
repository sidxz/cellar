"""SQLAlchemy implementation of PlateInsightsReader."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.application.inventory.plate_insights_reader import (
    CountBucket,
    GroupSize,
    LocationCount,
    PlateInsightsData,
    WeeklyLoanActivity,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import (
    PlateGroupModel,
    RegisteredPlateModel,
    StorageLocationModel,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.plate_loan_models import (
    LoanItemModel,
    PlateLoanModel,
)

WEEKS_IN_WINDOW = 12


class SQLAlchemyPlateInsightsReader:
    """Infrastructure-layer read model for per-org plate-insights dashboard queries."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_insights(self, workspace_id: uuid.UUID, org_id: uuid.UUID) -> PlateInsightsData:
        ws = workspace_id
        async with self._session_factory() as session:
            plate_where = (
                RegisteredPlateModel.workspace_id == ws,
                RegisteredPlateModel.owner_org_id == org_id,
            )
            total = (await session.execute(select(func.count()).where(*plate_where))).scalar_one()

            by_status = await self._buckets(session, RegisteredPlateModel.status, plate_where)
            by_type = await self._buckets(session, RegisteredPlateModel.plate_type, plate_where)

            loc_stmt = (
                select(
                    RegisteredPlateModel.storage_location_id,
                    StorageLocationModel.name,
                    func.count(),
                )
                .select_from(RegisteredPlateModel)
                .outerjoin(
                    StorageLocationModel,
                    RegisteredPlateModel.storage_location_id == StorageLocationModel.id,
                )
                .where(*plate_where)
                .group_by(RegisteredPlateModel.storage_location_id, StorageLocationModel.name)
                .order_by(func.count().desc())
            )
            by_location = [
                LocationCount(location_id=row[0], name=row[1] or "Unassigned", count=row[2])
                for row in (await session.execute(loc_stmt)).all()
            ]

            group_stmt = (
                select(RegisteredPlateModel.group_id, PlateGroupModel.name, func.count())
                .join(PlateGroupModel, RegisteredPlateModel.group_id == PlateGroupModel.id)
                .where(*plate_where)
                .group_by(RegisteredPlateModel.group_id, PlateGroupModel.name)
                .order_by(func.count().desc())
            )
            group_sizes = [
                GroupSize(group_id=row[0], name=row[1], count=row[2])
                for row in (await session.execute(group_stmt)).all()
            ]

            loan_where = (
                PlateLoanModel.workspace_id == ws,
                PlateLoanModel.owner_org_id == org_id,
            )
            open_loans = (
                await session.execute(
                    select(func.count()).where(*loan_where, PlateLoanModel.status == "open")
                )
            ).scalar_one()
            # Overdue uses the DB's current_date (server TZ), not Python's
            # date.today() — both sides of the comparison stay consistent
            # within a single query regardless of where the app runs.
            overdue = (
                await session.execute(
                    select(func.count()).where(
                        *loan_where,
                        PlateLoanModel.status == "open",
                        PlateLoanModel.due_date < func.current_date(),
                    )
                )
            ).scalar_one()

            weekly = await self._weekly_activity(session, ws, org_id)

        return PlateInsightsData(
            total_plates=total,
            by_status=by_status,
            by_type=by_type,
            by_location=by_location,
            group_sizes=group_sizes,
            loan_activity_weekly=weekly,
            open_loans=open_loans,
            overdue_count=overdue,
        )

    async def _buckets(self, session: AsyncSession, column, where: tuple) -> list[CountBucket]:
        stmt = (
            select(column, func.count())
            .where(*where)
            .group_by(column)
            .order_by(func.count().desc())
        )
        rows = (await session.execute(stmt)).all()
        return [CountBucket(key=row[0], count=row[1]) for row in rows]

    async def _weekly_activity(
        self, session: AsyncSession, workspace_id: uuid.UUID, org_id: uuid.UUID
    ) -> list[WeeklyLoanActivity]:
        """12 ISO (Monday-start) weeks, oldest first, zero-filled, ending this week.

        Postgres ``date_trunc('week', …)`` is Monday-based ISO — the same
        convention as ``today - timedelta(days=today.weekday())`` below.
        """
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        window_start = datetime.combine(
            monday - timedelta(weeks=WEEKS_IN_WINDOW - 1), time.min, tzinfo=UTC
        )

        # Built once and reused in both SELECT and GROUP BY: two separate
        # func.date_trunc("week", …) calls bind "week" as two distinct
        # parameters, and Postgres can't prove two placeholders are equal
        # at prepare time — "column must appear in GROUP BY" even though
        # the SQL text looks identical. Reusing the same expression object
        # reuses the same bound parameter, sidestepping that entirely.
        requested_week = func.date_trunc("week", PlateLoanModel.created_at)
        requested_stmt = (
            select(requested_week, func.count())
            .where(
                PlateLoanModel.workspace_id == workspace_id,
                PlateLoanModel.owner_org_id == org_id,
                PlateLoanModel.created_at >= window_start,
            )
            .group_by(requested_week)
        )
        requested_by_week = {
            row[0].date(): row[1] for row in (await session.execute(requested_stmt)).all()
        }

        returned_week = func.date_trunc("week", LoanItemModel.status_changed_at)
        returned_stmt = (
            select(returned_week, func.count())
            .select_from(LoanItemModel)
            .join(PlateLoanModel, LoanItemModel.loan_id == PlateLoanModel.id)
            .where(
                PlateLoanModel.workspace_id == workspace_id,
                PlateLoanModel.owner_org_id == org_id,
                LoanItemModel.status == "returned",
                LoanItemModel.status_changed_at >= window_start,
            )
            .group_by(returned_week)
        )
        returned_by_week = {
            row[0].date(): row[1] for row in (await session.execute(returned_stmt)).all()
        }

        weeks = [monday - timedelta(weeks=n) for n in range(WEEKS_IN_WINDOW - 1, -1, -1)]
        return [
            WeeklyLoanActivity(
                week_start=w,
                requested=requested_by_week.get(w, 0),
                returned=returned_by_week.get(w, 0),
            )
            for w in weeks
        ]
