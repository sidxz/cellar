"""SQLAlchemy repository for Tag aggregates (registry)."""

from __future__ import annotations

import uuid

from sqlalchemy import column, delete, func, or_, select, table
from sqlalchemy.dialects.postgresql import insert as pg_insert

from cellar.domain.workspace_config.tagging.tag import Tag, TagName
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration._field_clauses import (
    escape_like,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.models import TagModel

# Read-only handle to the cross-type assignment view (created in migrations
# 047/050). Declared via table()/column() so it is NOT registered in the ORM
# metadata — alembic won't try to manage it.
_tag_links_all = table("tag_links_all", column("tag_id"))


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
        # Usage count per tag across every entity type — drives most-used-first
        # ordering. Aggregated from the cross-type view; the per-table tag_id
        # indexes back it. If ever measured slow at very high assignment
        # cardinality, a maintained usage_count column is the documented next step.
        usage = (
            select(_tag_links_all.c.tag_id, func.count().label("n"))
            .group_by(_tag_links_all.c.tag_id)
            .subquery()
        )
        stmt = (
            select(TagModel)
            .outerjoin(usage, usage.c.tag_id == TagModel.id)
            .where(TagModel.workspace_id == workspace_id)
        )
        if q and q.strip():
            # Escape LIKE metacharacters so a literal % or _ in the query does not
            # act as a wildcard. Columns are pre-casefolded, so .like (not .ilike)
            # is correct for case-insensitive matching.
            term = q.strip().casefold()
            if "=" in term:
                # "key=value" → match the key part AND the value part separately,
                # so `own=44` narrows to tags whose key contains "own" and value
                # contains "44" (rather than the literal substring "own=44").
                key_part, _, value_part = term.partition("=")
                key_part, value_part = key_part.strip(), value_part.strip()
                if key_part:
                    stmt = stmt.where(
                        TagModel.normalized_key.like(f"%{escape_like(key_part)}%", escape="\\")
                    )
                if value_part:
                    stmt = stmt.where(
                        TagModel.normalized_value.like(
                            f"%{escape_like(value_part)}%", escape="\\"
                        )
                    )
            else:
                # Plain term → substring match on key OR value.
                pattern = f"%{escape_like(term)}%"
                stmt = stmt.where(
                    or_(
                        TagModel.normalized_key.like(pattern, escape="\\"),
                        TagModel.normalized_value.like(pattern, escape="\\"),
                    )
                )
        if created_by is not None:
            stmt = stmt.where(TagModel.created_by == created_by)
        stmt = stmt.order_by(
            func.coalesce(usage.c.n, 0).desc(),
            TagModel.normalized_key,
            TagModel.normalized_value,
            TagModel.id,
        ).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars()]

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        stmt = delete(TagModel).where(
            TagModel.workspace_id == workspace_id, TagModel.id == id
        )
        await self._session.execute(stmt)
