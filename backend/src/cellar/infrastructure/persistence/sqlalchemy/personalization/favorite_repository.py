"""SQLAlchemy repository for Favorite aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from cellar.domain.personalization.enums import FavoriteEntityType
from cellar.domain.personalization.favorite import Favorite
from cellar.infrastructure.persistence.sqlalchemy.base_repository import SQLAlchemyRepository
from cellar.infrastructure.persistence.sqlalchemy.personalization.models import FavoriteModel


class SQLAlchemyFavoriteRepository(SQLAlchemyRepository[Favorite, FavoriteModel]):
    model_class = FavoriteModel

    def _to_domain(self, model: FavoriteModel) -> Favorite:
        return Favorite(
            id=model.id,
            workspace_id=model.workspace_id,
            user_id=model.user_id,
            entity_type=FavoriteEntityType(model.entity_type),
            entity_id=model.entity_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: Favorite) -> FavoriteModel:
        return FavoriteModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            user_id=aggregate.user_id,
            entity_type=aggregate.entity_type.value,
            entity_id=aggregate.entity_id,
            version=aggregate.version,
        )

    def _update_model(self, model: FavoriteModel, aggregate: Favorite) -> None:
        # Favorites are immutable (add/remove only); nothing to update.
        return

    async def find_by_entity(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        entity_type: FavoriteEntityType,
        entity_id: uuid.UUID,
    ) -> Favorite | None:
        stmt = select(FavoriteModel).where(
            FavoriteModel.workspace_id == workspace_id,
            FavoriteModel.user_id == user_id,
            FavoriteModel.entity_type == entity_type.value,
            FavoriteModel.entity_id == entity_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_domain_tracked(model) if model else None

    async def list_for_user(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        entity_type: FavoriteEntityType,
    ) -> list[Favorite]:
        stmt = (
            select(FavoriteModel)
            .where(
                FavoriteModel.workspace_id == workspace_id,
                FavoriteModel.user_id == user_id,
                FavoriteModel.entity_type == entity_type.value,
            )
            .order_by(FavoriteModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars()]

    async def remove(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        entity_type: FavoriteEntityType,
        entity_id: uuid.UUID,
    ) -> None:
        stmt = delete(FavoriteModel).where(
            FavoriteModel.workspace_id == workspace_id,
            FavoriteModel.user_id == user_id,
            FavoriteModel.entity_type == entity_type.value,
            FavoriteModel.entity_id == entity_id,
        )
        await self._session.execute(stmt)
