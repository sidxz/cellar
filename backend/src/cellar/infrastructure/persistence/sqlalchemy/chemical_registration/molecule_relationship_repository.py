"""SQLAlchemy repository for MoleculeRelationship entities.

Follows the same UoW pattern as SQLAlchemyMergeEventRepository — takes
AsyncUnitOfWork for transaction management.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from cellar.domain.chemical_registration.enums import RelationshipType
from cellar.domain.chemical_registration.molecule_relationship import MoleculeRelationship
from cellar.domain.shared.errors import AuthorizationError
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeRelationshipModel,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyMoleculeRelationshipRepository:
    """Simple CRUD repository for MoleculeRelationship (not an aggregate root)."""

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    @property
    def _session(self) -> AsyncSession:
        return self._uow.session

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

    async def _find_by_id_unscoped(self, id: uuid.UUID) -> MoleculeRelationship | None:
        model = await self._session.get(MoleculeRelationshipModel, id)
        return self._to_domain(model) if model else None

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> MoleculeRelationship | None:
        """Load by PK scoped to workspace."""
        stmt = select(MoleculeRelationshipModel).where(
            MoleculeRelationshipModel.id == id,
            MoleculeRelationshipModel.workspace_id == workspace_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

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

    async def save(self, entity: MoleculeRelationship) -> None:
        existing = await self._session.get(MoleculeRelationshipModel, entity.id)
        if existing is not None and existing.workspace_id != entity.workspace_id:
            raise AuthorizationError(
                "Cannot update MoleculeRelationship from a different workspace"
            )
        model = self._to_model(entity)
        self._session.add(model)
        await self._session.flush()

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        stmt = delete(MoleculeRelationshipModel).where(
            MoleculeRelationshipModel.workspace_id == workspace_id,
            MoleculeRelationshipModel.id == id,
        )
        await self._session.execute(stmt)
