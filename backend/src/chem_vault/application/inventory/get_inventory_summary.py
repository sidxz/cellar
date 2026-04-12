"""GetInventorySummary query use case — dashboard metrics for inventory hub."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from returns.result import Result, Success
from sqlalchemy import func, select

from chem_vault.application.auth import AuthContext
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class InventorySummaryQuery(Query):
    workspace_id: uuid.UUID


@dataclass(frozen=True)
class ActivityItem:
    description: str
    entity_type: str
    entity_id: uuid.UUID
    occurred_at: datetime


@dataclass(frozen=True)
class InventorySummary:
    low_stock_count: int
    expiring_soon_count: int
    pending_requests_count: int
    recent_activity: list[ActivityItem] = field(default_factory=list)


class GetInventorySummary:
    """Return dashboard summary metrics for the inventory hub.

    Uses raw SA queries (read-model approach) rather than loading full
    aggregates, since we only need counts and a small activity feed.
    """

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def __call__(
        self,
        input: InventorySummaryQuery,
        auth: AuthContext | None = None,
    ) -> Result[InventorySummary, DomainError]:
        # Deferred imports — these are infra models, only used inside the
        # read-model query.  Keeps the module importable without a DB.
        from chem_vault.infrastructure.persistence.sqlalchemy.audit.audit_models import (
            AuditOperationModel,
        )
        from chem_vault.infrastructure.persistence.sqlalchemy.inventory.models import (
            BatchModel,
            SampleModel,
        )
        from chem_vault.infrastructure.persistence.sqlalchemy.inventory.sample_request_models import (
            SampleRequestModel,
        )
        from chem_vault.infrastructure.persistence.sqlalchemy.inventory.synthesis_request_models import (
            SynthesisRequestModel,
        )

        async with self._uow as uow:
            session = uow.session  # type: ignore[union-attr]
            ws = input.workspace_id
            today = date.today()

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
                    SampleRequestModel.status.in_(
                        ["submitted", "approved", "preparing"]
                    ),
                )
            )
            pending_sample_reqs = (
                await session.execute(sample_req_stmt)
            ).scalar_one()

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
            pending_synth_reqs = (
                await session.execute(synth_req_stmt)
            ).scalar_one()

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
                    AuditOperationModel.entity_type.in_(
                        ["batch", "sample", "storage_location"]
                    ),
                )
                .order_by(AuditOperationModel.started_at.desc())
                .limit(5)
            )
            activity_rows = (await session.execute(activity_stmt)).all()

            recent_activity = [
                ActivityItem(
                    description=f"{row.operation_type.replace('_', ' ').capitalize()} {row.entity_type}",
                    entity_type=row.entity_type,
                    entity_id=row.entity_id,
                    occurred_at=row.started_at,
                )
                for row in activity_rows
            ]

            return Success(
                InventorySummary(
                    low_stock_count=low_stock_count,
                    expiring_soon_count=expiring_soon_count,
                    pending_requests_count=pending_sample_reqs + pending_synth_reqs,
                    recent_activity=recent_activity,
                )
            )
