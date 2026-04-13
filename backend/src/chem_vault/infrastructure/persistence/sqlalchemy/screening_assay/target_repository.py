"""SQLAlchemy repository for Target entities.

Target is not an AggregateRoot — standalone repo with manual CRUD.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from chem_vault.domain.screening_assay.enums import TargetType
from chem_vault.domain.screening_assay.target import Target
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    TargetModel,
)
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyTargetRepository:
    """Persists Target entities to PostgreSQL."""

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def find_by_id(self, id: uuid.UUID) -> Target | None:
        model = await self._uow.session.get(TargetModel, id)
        return self._to_domain(model) if model else None

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> Target | None:
        """Load by PK scoped to workspace."""
        stmt = (
            select(TargetModel)
            .where(
                TargetModel.id == id,
                TargetModel.workspace_id == workspace_id,
            )
        )
        result = await self._uow.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def find_by_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[Target]:
        stmt = (
            select(TargetModel)
            .where(TargetModel.workspace_id == workspace_id)
            .order_by(TargetModel.name)
        )
        result = await self._uow.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def save(self, entity: Target) -> None:
        model = self._to_model(entity)
        await self._uow.session.merge(model)

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        model = await self._uow.session.get(TargetModel, id)
        if model is not None and model.workspace_id == workspace_id:
            await self._uow.session.delete(model)

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _to_domain(model: TargetModel) -> Target:
        return Target(
            id=model.id,
            workspace_id=model.workspace_id,
            name=model.name,
            target_type=TargetType(model.target_type),
            organism=model.organism,
            gene_name=model.gene_name,
            uniprot_id=model.uniprot_id,
            ncbi_gene_id=model.ncbi_gene_id,
            description=model.description,
            target_class=model.target_class,
            sequence=model.sequence,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_model(entity: Target) -> TargetModel:
        return TargetModel(
            id=entity.id,
            workspace_id=entity.workspace_id,
            name=entity.name,
            target_type=entity.target_type.value,
            organism=entity.organism,
            gene_name=entity.gene_name,
            uniprot_id=entity.uniprot_id,
            ncbi_gene_id=entity.ncbi_gene_id,
            description=entity.description,
            target_class=entity.target_class,
            sequence=entity.sequence,
        )
