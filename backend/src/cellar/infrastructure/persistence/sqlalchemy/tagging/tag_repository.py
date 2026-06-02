"""SQLAlchemy repository for Tag aggregates (registry)."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from cellar.domain.workspace_config.tagging.tag import Tag, TagName
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.models import TagModel


def tag_model_to_domain(model: TagModel) -> Tag:
    """Map a TagModel row to a Tag aggregate. Shared with the link repository."""
    return Tag(
        id=model.id,
        workspace_id=model.workspace_id,
        name=TagName(key=model.key, value=model.value),
        created_by=model.created_by,
        created_at=model.created_at,
        updated_at=model.updated_at,
        version=model.version,
    )


class SQLAlchemyTagRepository(SQLAlchemyRepository[Tag, TagModel]):
    model_class = TagModel

    def _to_domain(self, model: TagModel) -> Tag:
        return tag_model_to_domain(model)

    def _to_model(self, aggregate: Tag) -> TagModel:
        return TagModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            key=aggregate.key,
            value=aggregate.value,
            normalized_key=aggregate.normalized_key,
            normalized_value=aggregate.normalized_value,
            created_by=aggregate.created_by,
            version=aggregate.version,
        )

    def _update_model(self, model: TagModel, aggregate: Tag) -> None:
        model.key = aggregate.key
        model.value = aggregate.value
        model.normalized_key = aggregate.normalized_key
        model.normalized_value = aggregate.normalized_value

    async def find_by_normalized(
        self, workspace_id: uuid.UUID, name: TagName
    ) -> Tag | None:
        stmt = select(TagModel).where(
            TagModel.workspace_id == workspace_id,
            TagModel.normalized_key == name.normalized_key,
            TagModel.normalized_value.is_not_distinct_from(name.normalized_value),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain_tracked(model) if model else None

    async def get_or_create(
        self, workspace_id: uuid.UUID, name: TagName, created_by: uuid.UUID
    ) -> Tag:
        existing = await self.find_by_normalized(workspace_id, name)
        if existing is not None:
            return existing

        tag = Tag.create(workspace_id=workspace_id, name=name, created_by=created_by)
        stmt = (
            pg_insert(TagModel)
            .values(
                id=tag.id,
                workspace_id=workspace_id,
                key=tag.key,
                value=tag.value,
                normalized_key=tag.normalized_key,
                normalized_value=tag.normalized_value,
                created_by=created_by,
                version=tag.version,
            )
            .on_conflict_do_nothing(
                index_elements=["workspace_id", "normalized_key", "normalized_value"]
            )
        )
        result = await self._session.execute(stmt)
        if result.rowcount == 0:
            # Lost the race — another tx created it. Return the winner, no event.
            tag.clear_events()
            winner = await self.find_by_normalized(workspace_id, name)
            assert winner is not None
            return winner

        self._uow.track(tag)  # so TagCreated is collected on commit
        return tag

    async def search(
        self,
        workspace_id: uuid.UUID,
        *,
        q: str | None = None,
        created_by: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[Tag]:
        stmt = select(TagModel).where(TagModel.workspace_id == workspace_id)
        if q and q.strip():
            pattern = f"%{q.strip().casefold()}%"
            stmt = stmt.where(
                or_(
                    TagModel.normalized_key.like(pattern),
                    TagModel.normalized_value.like(pattern),
                )
            )
        if created_by is not None:
            stmt = stmt.where(TagModel.created_by == created_by)
        stmt = stmt.order_by(
            TagModel.normalized_key, TagModel.normalized_value, TagModel.id
        ).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars()]

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        stmt = delete(TagModel).where(
            TagModel.workspace_id == workspace_id, TagModel.id == id
        )
        await self._session.execute(stmt)
