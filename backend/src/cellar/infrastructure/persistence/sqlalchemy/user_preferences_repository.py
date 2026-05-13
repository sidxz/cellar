"""SQLAlchemy implementation of UserPreferencesRepository.

Follows the audit repository pattern — raw session, no UoW
(no domain events or optimistic concurrency needed).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.domain.shared.user_preferences import UserPreferences
from cellar.infrastructure.persistence.sqlalchemy.user_preferences import (
    UserPreferencesModel,
)


class SQLAlchemyUserPreferencesRepository:
    """Persists user preferences to PostgreSQL.

    Uses its own short-lived sessions (not shared with UoW) — no domain
    events or optimistic concurrency needed.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_by_user(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> UserPreferences | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(UserPreferencesModel).where(
                    UserPreferencesModel.workspace_id == workspace_id,
                    UserPreferencesModel.user_id == user_id,
                )
            )
            model = result.scalar_one_or_none()
            return self._to_domain(model) if model else None

    async def save(self, preferences: UserPreferences) -> UserPreferences:
        async with self._session_factory() as session:
            result = await session.execute(
                select(UserPreferencesModel).where(
                    UserPreferencesModel.workspace_id == preferences.workspace_id,
                    UserPreferencesModel.user_id == preferences.user_id,
                )
            )
            model = result.scalar_one_or_none()

            if model:
                model.preferences = self._to_json(preferences)
            else:
                model = UserPreferencesModel(
                    id=preferences.id,
                    workspace_id=preferences.workspace_id,
                    user_id=preferences.user_id,
                    preferences=self._to_json(preferences),
                )
                session.add(model)

            await session.commit()
            await session.refresh(model)
            return self._to_domain(model)

    @staticmethod
    def _to_domain(model: UserPreferencesModel) -> UserPreferences:
        prefs = model.preferences or {}
        return UserPreferences(
            id=model.id,
            workspace_id=model.workspace_id,
            user_id=model.user_id,
            theme=prefs.get("theme", "dark"),
            sidebar_collapsed=prefs.get("sidebar_collapsed", False),
            default_search_columns=prefs.get("default_search_columns"),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_json(preferences: UserPreferences) -> dict:
        data: dict = {
            "theme": preferences.theme,
            "sidebar_collapsed": preferences.sidebar_collapsed,
        }
        if preferences.default_search_columns is not None:
            data["default_search_columns"] = preferences.default_search_columns
        return data
