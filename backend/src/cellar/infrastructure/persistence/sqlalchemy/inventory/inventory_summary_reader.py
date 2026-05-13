"""SQLAlchemy implementation of InventorySummaryReader."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.application.inventory.inventory_summary_reader import (
    ActivityRow,
    InventorySummaryCounts,
)
from cellar.infrastructure.persistence.sqlalchemy.audit.audit_models import (
    AuditOperationModel,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import (
    BatchModel,
    SampleModel,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.sample_request_models import (
    SampleRequestModel,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.synthesis_request_models import (
    SynthesisRequestModel,
)


class SQLAlchemyInventorySummaryReader:
    """Infrastructure-layer read model for inventory summary queries."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_summary(self, workspace_id: uuid.UUID) -> InventorySummaryCounts:
        ws = workspace_id
        today = date.today()

        async with self._session_factory() as session:
            # 1. Low-stock samples
            low_stock_stmt = (
                select(func.count())
                .select_from(SampleModel)
                .where(
                    SampleModel.workspace_id == ws,
                    SampleModel.status == "available",
                    SampleModel.low_stock_threshold.isnot(None),
                    SampleModel.amount_value < SampleModel.low_stock_threshold,
                )
            )
            low_stock_count = (await session.execute(low_stock_stmt)).scalar_one()

            # 2. Batches expiring within 30 days
            expiry_limit = today + timedelta(days=30)
            expiring_stmt = (
                select(func.count())
                .select_from(BatchModel)
                .where(
                    BatchModel.workspace_id == ws,
                    BatchModel.expiry_date.isnot(None),
                    BatchModel.expiry_date >= today,
                    BatchModel.expiry_date <= expiry_limit,
                )
            )
            expiring_soon_count = (await session.execute(expiring_stmt)).scalar_one()

            # 3. Pending sample requests
            sample_req_stmt = (
                select(func.count())
                .select_from(SampleRequestModel)
                .where(
                    SampleRequestModel.workspace_id == ws,
                    SampleRequestModel.status.in_(["submitted", "approved", "preparing"]),
                )
            )
            pending_sample_reqs = (await session.execute(sample_req_stmt)).scalar_one()

            # 4. Pending synthesis requests
            synth_req_stmt = (
                select(func.count())
                .select_from(SynthesisRequestModel)
                .where(
                    SynthesisRequestModel.workspace_id == ws,
                    SynthesisRequestModel.status.in_(
                        ["submitted", "approved", "assigned", "in_progress"]
                    ),
                )
            )
            pending_synth_reqs = (await session.execute(synth_req_stmt)).scalar_one()

            # 5. Recent inventory-related audit activity
            activity_stmt = (
                select(
                    AuditOperationModel.operation_type,
                    AuditOperationModel.entity_type,
                    AuditOperationModel.entity_id,
                    AuditOperationModel.started_at,
                )
                .where(
                    AuditOperationModel.workspace_id == ws,
                    AuditOperationModel.entity_type.in_(["batch", "sample", "storage_location"]),
                )
                .order_by(AuditOperationModel.started_at.desc())
                .limit(5)
            )
            activity_rows = (await session.execute(activity_stmt)).all()

            recent_activity = [
                ActivityRow(
                    operation_type=row.operation_type,
                    entity_type=row.entity_type,
                    entity_id=row.entity_id,
                    started_at=row.started_at,
                )
                for row in activity_rows
            ]

        return InventorySummaryCounts(
            low_stock_count=low_stock_count,
            expiring_soon_count=expiring_soon_count,
            pending_sample_requests=pending_sample_reqs,
            pending_synthesis_requests=pending_synth_reqs,
            recent_activity=recent_activity,
        )
