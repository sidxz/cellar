"""SQLAlchemy repository for MoleculeRelationship entities.

MoleculeRelationship is a plain Entity (no version, no domain events). Inherits
the workspace-scoped read/save/delete surface from ``EntityRepository``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from cellar.domain.chemical_registration.enums import RelationshipType
from cellar.domain.chemical_registration.molecule_relationship import (
    MoleculeRelationship,
)
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    EntityRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeRelationshipModel,
)


class SQLAlchemyMoleculeRelationshipRepository(
    EntityRepository[MoleculeRelationship, MoleculeRelationshipModel]
):
    """Simple CRUD repository for MoleculeRelationship (not an aggregate root)."""

    model_class = MoleculeRelationshipModel

    def _to_domain(self, model: MoleculeRelationshipModel) -> MoleculeRelationship:
        return MoleculeRelationship(
            id=model.id,
            workspace_id=model.workspace_id,
            source_molecule_id=model.source_molecule_id,
            target_molecule_id=model.target_molecule_id,
            relationship_type=RelationshipType(model.relationship_type),
            notes=model.notes,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: MoleculeRelationship) -> MoleculeRelationshipModel:
        return MoleculeRelationshipModel(
            id=entity.id,
            workspace_id=entity.workspace_id,
            source_molecule_id=entity.source_molecule_id,
            target_molecule_id=entity.target_molecule_id,
            relationship_type=entity.relationship_type.value,
            notes=entity.notes,
            created_by=entity.created_by,
        )

    def _update_model(
        self, model: MoleculeRelationshipModel, entity: MoleculeRelationship
    ) -> None:
        model.relationship_type = entity.relationship_type.value
        model.notes = entity.notes

    async def find_by_source(
        self, workspace_id: uuid.UUID, source_molecule_id: uuid.UUID
    ) -> list[MoleculeRelationship]:
        stmt = select(MoleculeRelationshipModel).where(
            MoleculeRelationshipModel.workspace_id == workspace_id,
            MoleculeRelationshipModel.source_molecule_id == source_molecule_id,
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars()]

    async def find_by_target(
        self, workspace_id: uuid.UUID, target_molecule_id: uuid.UUID
    ) -> list[MoleculeRelationship]:
        stmt = select(MoleculeRelationshipModel).where(
            MoleculeRelationshipModel.workspace_id == workspace_id,
            MoleculeRelationshipModel.target_molecule_id == target_molecule_id,
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars()]
