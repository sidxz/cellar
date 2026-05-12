"""SQLAlchemy repository for RegistrationForm aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from cellar.domain.workspace_config.enums import FieldTarget
from cellar.domain.workspace_config.registration_form import RegistrationForm
from cellar.domain.workspace_config.value_objects import FieldOverride
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.models import (
    RegistrationFormModel,
)


class SQLAlchemyRegistrationFormRepository(
    SQLAlchemyRepository[RegistrationForm, RegistrationFormModel]
):
    model_class = RegistrationFormModel

    def _to_domain(self, model: RegistrationFormModel) -> RegistrationForm:
        field_overrides = [FieldOverride(**item) for item in (model.field_overrides or [])]
        return RegistrationForm(
            id=model.id,
            workspace_id=model.workspace_id,
            name=model.name,
            applies_to=FieldTarget(model.applies_to),
            is_default=model.is_default,
            field_overrides=field_overrides,
            version=model.version,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, aggregate: RegistrationForm) -> RegistrationFormModel:
        return RegistrationFormModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            name=aggregate.name,
            applies_to=aggregate.applies_to.value,
            is_default=aggregate.is_default,
            field_overrides=[o.model_dump() for o in aggregate.field_overrides],
            version=aggregate.version,
        )

    def _update_model(self, model: RegistrationFormModel, aggregate: RegistrationForm) -> None:
        model.name = aggregate.name
        model.applies_to = aggregate.applies_to.value
        model.is_default = aggregate.is_default
        model.field_overrides = [o.model_dump() for o in aggregate.field_overrides]

    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        applies_to: FieldTarget | None = None,
    ) -> list[RegistrationForm]:
        stmt = select(RegistrationFormModel).where(
            RegistrationFormModel.workspace_id == workspace_id
        )
        if applies_to is not None:
            stmt = stmt.where(RegistrationFormModel.applies_to == applies_to.value)
        stmt = stmt.order_by(RegistrationFormModel.name)
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars()]

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        stmt = delete(RegistrationFormModel).where(
            RegistrationFormModel.workspace_id == workspace_id,
            RegistrationFormModel.id == id,
        )
        await self._session.execute(stmt)
