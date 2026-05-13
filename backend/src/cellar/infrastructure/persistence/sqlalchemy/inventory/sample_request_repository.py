"""SQLAlchemy repository for SampleRequest aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from cellar.domain.inventory.enums import RequestPriority, SampleRequestStatus
from cellar.domain.inventory.sample_request import SampleRequest
from cellar.domain.shared.enums import AmountUnit
from cellar.domain.shared.value_objects import Amount
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.sample_request_models import (
    SampleRequestModel,
)


class SQLAlchemySampleRequestRepository(SQLAlchemyRepository[SampleRequest, SampleRequestModel]):
    model_class = SampleRequestModel

    async def find_by_workspace(
        self, workspace_id: uuid.UUID, *, status: str | None = None
    ) -> list[SampleRequest]:
        stmt = select(SampleRequestModel).where(SampleRequestModel.workspace_id == workspace_id)
        if status:
            stmt = stmt.where(SampleRequestModel.status == status)
        stmt = stmt.order_by(SampleRequestModel.created_at.desc())
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]

    def _to_domain(self, model: SampleRequestModel) -> SampleRequest:
        return SampleRequest(
            id=model.id,
            workspace_id=model.workspace_id,
            requester_id=model.requester_id,
            molecule_id=model.molecule_id,
            batch_id=model.batch_id,
            requested_amount=Amount(
                value=model.requested_amount_value,
                unit=AmountUnit(model.requested_amount_unit),
            ),
            purpose=model.purpose,
            priority=RequestPriority(model.priority),
            status=SampleRequestStatus(model.status),
            assigned_to=model.assigned_to,
            fulfilled_sample_id=model.fulfilled_sample_id,
            rejection_reason=model.rejection_reason,
            fulfilled_at=model.fulfilled_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: SampleRequest) -> SampleRequestModel:
        return SampleRequestModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            requester_id=aggregate.requester_id,
            molecule_id=aggregate.molecule_id,
            batch_id=aggregate.batch_id,
            requested_amount_value=aggregate.requested_amount.value,
            requested_amount_unit=aggregate.requested_amount.unit.value,
            purpose=aggregate.purpose,
            priority=aggregate.priority.value,
            status=aggregate.status.value,
            assigned_to=aggregate.assigned_to,
            fulfilled_sample_id=aggregate.fulfilled_sample_id,
            rejection_reason=aggregate.rejection_reason,
            fulfilled_at=aggregate.fulfilled_at,
            version=aggregate.version,
        )

    def _update_model(self, model: SampleRequestModel, aggregate: SampleRequest) -> None:
        model.batch_id = aggregate.batch_id
        model.purpose = aggregate.purpose
        model.priority = aggregate.priority.value
        model.requested_amount_value = aggregate.requested_amount.value
        model.requested_amount_unit = aggregate.requested_amount.unit.value
        model.status = aggregate.status.value
        model.assigned_to = aggregate.assigned_to
        model.fulfilled_sample_id = aggregate.fulfilled_sample_id
        model.rejection_reason = aggregate.rejection_reason
        model.fulfilled_at = aggregate.fulfilled_at
