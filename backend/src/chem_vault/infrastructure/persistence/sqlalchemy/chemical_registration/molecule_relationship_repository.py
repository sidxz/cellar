"""SQLAlchemy repository for MoleculeRelationship entities."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chem_vault.domain.chemical_registration.enums import RelationshipType
from chem_vault.domain.chemical_registration.molecule_relationship import MoleculeRelationship
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeRelationshipModel,
)


class SQLAlchemyMoleculeRelationshipRepository:
    """Simple CRUD repository for MoleculeRelationship (not an aggregate root)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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

    async def find_by_id(self, id: uuid.UUID) -> MoleculeRelationship | None:
        model = await self._session.get(MoleculeRelationshipModel, id)
        return self._to_domain(model) if model else None

    async def find_by_source(
        self, source_molecule_id: uuid.UUID
    ) -> list[MoleculeRelationship]:
        stmt = select(MoleculeRelationshipModel).where(
            MoleculeRelationshipModel.source_molecule_id == source_molecule_id
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars()]

    async def find_by_target(
        self, target_molecule_id: uuid.UUID
    ) -> list[MoleculeRelationship]:
        stmt = select(MoleculeRelationshipModel).where(
            MoleculeRelationshipModel.target_molecule_id == target_molecule_id
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars()]

    async def save(self, entity: MoleculeRelationship) -> None:
        model = self._to_model(entity)
        self._session.add(model)
        await self._session.flush()

    async def delete(self, id: uuid.UUID) -> None:
        stmt = delete(MoleculeRelationshipModel).where(
            MoleculeRelationshipModel.id == id
        )
        await self._session.execute(stmt)
