"""SQLAlchemy repository for CustomFieldDefinition aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from chem_vault.domain.workspace_config.custom_field_definition import CustomFieldDefinition
from chem_vault.domain.workspace_config.enums import FieldDataType, FieldTarget
from chem_vault.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.models import (
    CustomFieldDefinitionModel,
)


class SQLAlchemyCustomFieldDefinitionRepository(
    SQLAlchemyRepository[CustomFieldDefinition, CustomFieldDefinitionModel]
):
    model_class = CustomFieldDefinitionModel

    def _to_domain(self, model: CustomFieldDefinitionModel) -> CustomFieldDefinition:
        return CustomFieldDefinition(
            id=model.id,
            workspace_id=model.workspace_id,
            name=model.name,
            label=model.label,
            data_type=FieldDataType(model.data_type),
            applies_to=FieldTarget(model.applies_to),
            is_required=model.is_required,
            default_value=model.default_value,
            display_order=model.display_order,
            pick_list_values=list(model.pick_list_values) if model.pick_list_values else None,
            vocabulary_id=model.vocabulary_id,
            is_active=model.is_active,
            version=model.version,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, aggregate: CustomFieldDefinition) -> CustomFieldDefinitionModel:
        return CustomFieldDefinitionModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            name=aggregate.name,
            label=aggregate.label,
            data_type=aggregate.data_type.value,
            applies_to=aggregate.applies_to.value,
            is_required=aggregate.is_required,
            default_value=aggregate.default_value,
            display_order=aggregate.display_order,
            pick_list_values=aggregate.pick_list_values,
            vocabulary_id=aggregate.vocabulary_id,
            is_active=aggregate.is_active,
            version=aggregate.version,
        )

    def _update_model(
        self, model: CustomFieldDefinitionModel, aggregate: CustomFieldDefinition
    ) -> None:
        model.label = aggregate.label
        model.is_required = aggregate.is_required
        model.default_value = aggregate.default_value
        model.display_order = aggregate.display_order
        model.pick_list_values = aggregate.pick_list_values
        model.vocabulary_id = aggregate.vocabulary_id
        model.is_active = aggregate.is_active

    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        applies_to: FieldTarget | None = None,
        active_only: bool = True,
    ) -> list[CustomFieldDefinition]:
        stmt = select(CustomFieldDefinitionModel).where(
            CustomFieldDefinitionModel.workspace_id == workspace_id
        )
        if active_only:
            stmt = stmt.where(CustomFieldDefinitionModel.is_active.is_(True))
        if applies_to is not None:
            stmt = stmt.where(
                CustomFieldDefinitionModel.applies_to == applies_to.value
            )
        stmt = stmt.order_by(CustomFieldDefinitionModel.display_order)
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars()]

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        stmt = delete(CustomFieldDefinitionModel).where(
            CustomFieldDefinitionModel.workspace_id == workspace_id,
            CustomFieldDefinitionModel.id == id,
        )
        await self._session.execute(stmt)
