"""SQLAlchemy repository for Organization aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from chem_vault.domain.workspace_config.enums import OrganizationType
from chem_vault.domain.workspace_config.organization import Organization
from chem_vault.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.models import (
    OrganizationModel,
)


class SQLAlchemyOrganizationRepository(
    SQLAlchemyRepository[Organization, OrganizationModel]
):
    model_class = OrganizationModel

    def _to_domain(self, model: OrganizationModel) -> Organization:
        return Organization(
            id=model.id,
            workspace_id=model.workspace_id,
            name=model.name,
            org_type=OrganizationType(model.org_type),
            contact_name=model.contact_name,
            contact_email=model.contact_email,
            notes=model.notes,
            is_active=model.is_active,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: Organization) -> OrganizationModel:
        return OrganizationModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            name=aggregate.name,
            org_type=aggregate.org_type.value,
            contact_name=aggregate.contact_name,
            contact_email=aggregate.contact_email,
            notes=aggregate.notes,
            is_active=aggregate.is_active,
            version=aggregate.version,
        )

    def _update_model(self, model: OrganizationModel, aggregate: Organization) -> None:
        model.name = aggregate.name
        model.org_type = aggregate.org_type.value
        model.contact_name = aggregate.contact_name
        model.contact_email = aggregate.contact_email
        model.notes = aggregate.notes
        model.is_active = aggregate.is_active

    async def find_by_workspace(
        self, workspace_id: uuid.UUID, *, include_inactive: bool = False
    ) -> list[Organization]:
        stmt = select(OrganizationModel).where(
            OrganizationModel.workspace_id == workspace_id
        )
        if not include_inactive:
            stmt = stmt.where(OrganizationModel.is_active.is_(True))
        stmt = stmt.order_by(OrganizationModel.name)
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars()]

    async def find_by_name(
        self, workspace_id: uuid.UUID, name: str
    ) -> Organization | None:
        stmt = select(OrganizationModel).where(
            OrganizationModel.workspace_id == workspace_id,
            OrganizationModel.name == name,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None
