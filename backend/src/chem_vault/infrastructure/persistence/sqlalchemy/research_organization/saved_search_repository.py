"""SQLAlchemy repository for SavedSearch aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from chem_vault.domain.research_organization.saved_search import (
    SavedSearch,
    SearchVisibility,
)
from chem_vault.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.models import (
    SavedSearchModel,
)


class SQLAlchemySavedSearchRepository(
    SQLAlchemyRepository[SavedSearch, SavedSearchModel]
):
    model_class = SavedSearchModel

    def _to_domain(self, model: SavedSearchModel) -> SavedSearch:
        return SavedSearch(
            id=model.id,
            workspace_id=model.workspace_id,
            name=model.name,
            query=dict(model.query),
            columns=dict(model.columns) if model.columns else None,
            visibility=SearchVisibility(model.visibility),
            project_id=model.project_id,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: SavedSearch) -> SavedSearchModel:
        return SavedSearchModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            name=aggregate.name,
            query=aggregate.query,
            columns=aggregate.columns,
            visibility=aggregate.visibility.value,
            project_id=aggregate.project_id,
            created_by=aggregate.created_by,
            version=aggregate.version,
        )

    def _update_model(self, model: SavedSearchModel, aggregate: SavedSearch) -> None:
        model.name = aggregate.name
        model.query = aggregate.query
        model.columns = aggregate.columns
        model.visibility = aggregate.visibility.value
        model.project_id = aggregate.project_id

    async def find_by_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[SavedSearch]:
        stmt = (
            select(SavedSearchModel)
            .where(SavedSearchModel.workspace_id == workspace_id)
            .order_by(SavedSearchModel.name)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars()]

    async def find_by_project(
        self, project_id: uuid.UUID
    ) -> list[SavedSearch]:
        stmt = (
            select(SavedSearchModel)
            .where(SavedSearchModel.project_id == project_id)
            .order_by(SavedSearchModel.name)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars()]

    async def find_by_creator(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[SavedSearch]:
        stmt = (
            select(SavedSearchModel)
            .where(
                SavedSearchModel.workspace_id == workspace_id,
                SavedSearchModel.created_by == user_id,
            )
            .order_by(SavedSearchModel.name)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars()]

    async def delete(self, id: uuid.UUID) -> None:
        stmt = delete(SavedSearchModel).where(SavedSearchModel.id == id)
        await self._session.execute(stmt)
