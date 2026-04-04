"""SQLAlchemy implementation of UserPreferencesRepository.

Follows the audit repository pattern — raw session, no UoW
(no domain events or optimistic concurrency needed).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chem_vault.domain.shared.user_preferences import UserPreferences
from chem_vault.infrastructure.persistence.sqlalchemy.user_preferences import (
    UserPreferencesModel,
)


class SQLAlchemyUserPreferencesRepository:
    """Persists user preferences to PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> UserPreferences | None:
        result = await self._session.execute(
            select(UserPreferencesModel).where(
                UserPreferencesModel.workspace_id == workspace_id,
                UserPreferencesModel.user_id == user_id,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def save(self, preferences: UserPreferences) -> UserPreferences:
        result = await self._session.execute(
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
            self._session.add(model)

        await self._session.commit()
        await self._session.refresh(model)
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
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_json(preferences: UserPreferences) -> dict:
        return {
            "theme": preferences.theme,
            "sidebar_collapsed": preferences.sidebar_collapsed,
        }
