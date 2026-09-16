"""SQLAlchemy repository for OrgPlatePolicy aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from cellar.domain.inventory.enums import LoanConfirmationMode
from cellar.domain.inventory.org_plate_policy import OrgPlatePolicy
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import (
    OrgPlatePolicyModel,
)


class SQLAlchemyOrgPlatePolicyRepository(
    SQLAlchemyRepository[OrgPlatePolicy, OrgPlatePolicyModel]
):
    model_class = OrgPlatePolicyModel

    async def find_by_org(
        self, workspace_id: uuid.UUID, org_id: uuid.UUID
    ) -> OrgPlatePolicy | None:
        stmt = select(OrgPlatePolicyModel).where(
            OrgPlatePolicyModel.workspace_id == workspace_id,
            OrgPlatePolicyModel.org_id == org_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain_tracked(model)

    def _to_domain(self, model: OrgPlatePolicyModel) -> OrgPlatePolicy:
        return OrgPlatePolicy(
            id=model.id,
            workspace_id=model.workspace_id,
            org_id=model.org_id,
            require_approval=model.require_approval,
            confirmation=LoanConfirmationMode(model.confirmation),
            default_due_days=model.default_due_days,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: OrgPlatePolicy) -> OrgPlatePolicyModel:
        return OrgPlatePolicyModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            org_id=aggregate.org_id,
            require_approval=aggregate.require_approval,
            confirmation=aggregate.confirmation.value,
            default_due_days=aggregate.default_due_days,
            version=aggregate.version,
        )

    def _update_model(self, model: OrgPlatePolicyModel, aggregate: OrgPlatePolicy) -> None:
        model.require_approval = aggregate.require_approval
        model.confirmation = aggregate.confirmation.value
        model.default_due_days = aggregate.default_due_days
