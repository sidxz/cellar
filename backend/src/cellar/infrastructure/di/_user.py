"""User preferences bindings."""

from __future__ import annotations

from lagom import Container
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.application.user.get_preferences import GetPreferences
from cellar.application.user.update_preferences import UpdatePreferences
from cellar.domain.shared.user_preferences import UserPreferencesRepository
from cellar.infrastructure.persistence.sqlalchemy.user_preferences_repository import (
    SQLAlchemyUserPreferencesRepository,
)


def register_user(container: Container) -> None:
    container.define(
        SQLAlchemyUserPreferencesRepository,
        lambda c: SQLAlchemyUserPreferencesRepository(c[async_sessionmaker]),
    )
    container.define(UserPreferencesRepository, lambda c: c[SQLAlchemyUserPreferencesRepository])
    container.define(
        GetPreferences,
        lambda c: GetPreferences(c[UserPreferencesRepository]),
    )
    container.define(
        UpdatePreferences,
        lambda c: UpdatePreferences(c[UserPreferencesRepository]),
    )
