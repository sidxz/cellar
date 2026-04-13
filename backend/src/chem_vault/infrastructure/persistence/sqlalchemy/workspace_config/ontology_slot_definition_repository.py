"""SQLAlchemy repository for OntologySlotDefinition aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from chem_vault.domain.workspace_config.ontology_slot_definition import OntologySlotDefinition
from chem_vault.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.models import (
    OntologySlotDefinitionModel,
)


class SQLAlchemyOntologySlotDefinitionRepository(
    SQLAlchemyRepository[OntologySlotDefinition, OntologySlotDefinitionModel]
):
    model_class = OntologySlotDefinitionModel

    def _to_domain(self, model: OntologySlotDefinitionModel) -> OntologySlotDefinition:
        return OntologySlotDefinition(
            id=model.id,
            workspace_id=model.workspace_id,
            name=model.name,
            label=model.label,
            ontology_sources=list(model.ontology_sources),
            root_concept_id=model.root_concept_id,
            is_required=model.is_required,
            allow_free_text=model.allow_free_text,
            display_order=model.display_order,
            version=model.version,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, aggregate: OntologySlotDefinition) -> OntologySlotDefinitionModel:
        return OntologySlotDefinitionModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            name=aggregate.name,
            label=aggregate.label,
            ontology_sources=list(aggregate.ontology_sources),
            root_concept_id=aggregate.root_concept_id,
            is_required=aggregate.is_required,
            allow_free_text=aggregate.allow_free_text,
            display_order=aggregate.display_order,
            version=aggregate.version,
        )

    def _update_model(self, model: OntologySlotDefinitionModel, aggregate: OntologySlotDefinition) -> None:
        model.label = aggregate.label
        model.ontology_sources = list(aggregate.ontology_sources)
        model.root_concept_id = aggregate.root_concept_id
        model.is_required = aggregate.is_required
        model.allow_free_text = aggregate.allow_free_text
        model.display_order = aggregate.display_order

    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
    ) -> list[OntologySlotDefinition]:
        stmt = (
            select(OntologySlotDefinitionModel)
            .where(OntologySlotDefinitionModel.workspace_id == workspace_id)
            .order_by(OntologySlotDefinitionModel.display_order)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars()]

    async def find_by_name(
        self, workspace_id: uuid.UUID, name: str
    ) -> OntologySlotDefinition | None:
        stmt = select(OntologySlotDefinitionModel).where(
            OntologySlotDefinitionModel.workspace_id == workspace_id,
            OntologySlotDefinitionModel.name == name,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain_tracked(model) if model else None

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        stmt = delete(OntologySlotDefinitionModel).where(
            OntologySlotDefinitionModel.workspace_id == workspace_id,
            OntologySlotDefinitionModel.id == id,
        )
        await self._session.execute(stmt)
