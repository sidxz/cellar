"""GetPreferences query — fetch user preferences for a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.shared.query import Query
from chem_vault.domain.shared.errors import DomainError
from chem_vault.domain.shared.user_preferences import (
    UserPreferences,
    UserPreferencesRepository,
)


@dataclass(frozen=True, kw_only=True)
class GetPreferencesQuery(Query):
    workspace_id: uuid.UUID
    user_id: uuid.UUID


class GetPreferences:
    """Returns user preferences, or sensible defaults if none stored."""

    def __init__(self, repo: UserPreferencesRepository) -> None:
        self._repo = repo

    async def __call__(
        self, input: GetPreferencesQuery
    ) -> Result[UserPreferences, DomainError]:
        prefs = await self._repo.get_by_user(input.workspace_id, input.user_id)
        if prefs is None:
            prefs = UserPreferences(
                workspace_id=input.workspace_id,
                user_id=input.user_id,
            )
        return Success(prefs)
