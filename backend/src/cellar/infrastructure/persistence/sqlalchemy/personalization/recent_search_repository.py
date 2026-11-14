"""SQLAlchemy implementation of RecentSearchRepository.

Plain-CRUD pattern (like user preferences): short-lived sessions, no UoW —
recent searches carry no domain events and no optimistic concurrency.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.domain.personalization.recent_search import RecentSearch
from cellar.infrastructure.persistence.sqlalchemy.personalization.models import (
    RecentSearchModel,
)


class SQLAlchemyRecentSearchRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record(self, search: RecentSearch, *, keep: int) -> RecentSearch:
        """Upsert on (workspace, user, query_key), then trim to the newest ``keep``.

        One transaction, so a burst of searches never leaves more than ``keep``
        rows; ON CONFLICT makes two tabs recording the same search converge.
        """
        insert_stmt = insert(RecentSearchModel).values(
            id=search.id,
            workspace_id=search.workspace_id,
            user_id=search.user_id,
            query_key=search.query_key,
            query=search.query,
            columns=search.columns,
            result_count=search.result_count,
            ran_at=search.ran_at,
        )
        upsert = insert_stmt.on_conflict_do_update(
            index_elements=["workspace_id", "user_id", "query_key"],
            set_={
                "query": insert_stmt.excluded.query,
                "columns": insert_stmt.excluded.columns,
                "result_count": insert_stmt.excluded.result_count,
                "ran_at": insert_stmt.excluded.ran_at,
                "updated_at": func.now(),
            },
        ).returning(RecentSearchModel)
        mine = (
            RecentSearchModel.workspace_id == search.workspace_id,
            RecentSearchModel.user_id == search.user_id,
        )
        async with self._session_factory() as session:
            stored = self._to_domain((await session.execute(upsert)).scalar_one())
            newest = (
                select(RecentSearchModel.id)
                .where(*mine)
                .order_by(RecentSearchModel.ran_at.desc())
                .limit(keep)
            )
            await session.execute(
                delete(RecentSearchModel).where(*mine, RecentSearchModel.id.not_in(newest))
            )
            await session.commit()
        return stored

    async def list_for_user(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, limit: int
    ) -> list[RecentSearch]:
        async with self._session_factory() as session:
            rows = await session.execute(
                select(RecentSearchModel)
                .where(
                    RecentSearchModel.workspace_id == workspace_id,
                    RecentSearchModel.user_id == user_id,
                )
                .order_by(RecentSearchModel.ran_at.desc())
                .limit(limit)
            )
            return [self._to_domain(m) for m in rows.scalars()]

    async def clear(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> None:
        async with self._session_factory() as session:
            await session.execute(
                delete(RecentSearchModel).where(
                    RecentSearchModel.workspace_id == workspace_id,
                    RecentSearchModel.user_id == user_id,
                )
            )
            await session.commit()

    @staticmethod
    def _to_domain(model: RecentSearchModel) -> RecentSearch:
        return RecentSearch(
            id=model.id,
            workspace_id=model.workspace_id,
            user_id=model.user_id,
            query=model.query,
            columns=model.columns,
            result_count=model.result_count,
            ran_at=model.ran_at,
        )
