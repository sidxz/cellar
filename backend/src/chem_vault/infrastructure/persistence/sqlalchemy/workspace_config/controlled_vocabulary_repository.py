"""SQLAlchemy repository for ControlledVocabulary aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from chem_vault.domain.workspace_config.controlled_vocabulary import ControlledVocabulary
from chem_vault.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.models import (
    ControlledVocabularyModel,
)


class SQLAlchemyControlledVocabularyRepository(
    SQLAlchemyRepository[ControlledVocabulary, ControlledVocabularyModel]
):
    model_class = ControlledVocabularyModel

    def _to_domain(self, model: ControlledVocabularyModel) -> ControlledVocabulary:
        return ControlledVocabulary(
            id=model.id,
            workspace_id=model.workspace_id,
            name=model.name,
            terms=list(model.terms or []),
            is_locked=model.is_locked,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: ControlledVocabulary) -> ControlledVocabularyModel:
        return ControlledVocabularyModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            name=aggregate.name,
            terms=aggregate.terms,
            is_locked=aggregate.is_locked,
            created_by=aggregate.created_by,
            version=aggregate.version,
        )

    def _update_model(
        self, model: ControlledVocabularyModel, aggregate: ControlledVocabulary
    ) -> None:
        model.name = aggregate.name
        model.terms = aggregate.terms
        model.is_locked = aggregate.is_locked

    async def find_by_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[ControlledVocabulary]:
        stmt = (
            select(ControlledVocabularyModel)
            .where(ControlledVocabularyModel.workspace_id == workspace_id)
            .order_by(ControlledVocabularyModel.name)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars()]

    async def find_by_name(
        self, workspace_id: uuid.UUID, name: str
    ) -> ControlledVocabulary | None:
        stmt = select(ControlledVocabularyModel).where(
            ControlledVocabularyModel.workspace_id == workspace_id,
            ControlledVocabularyModel.name == name,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def delete(self, id: uuid.UUID) -> None:
        stmt = delete(ControlledVocabularyModel).where(
            ControlledVocabularyModel.id == id
        )
        await self._session.execute(stmt)
