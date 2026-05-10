"""UpdatePreferences command — upsert user preferences with partial merge."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.sentinel import UNSET
from chem_vault.domain.shared.errors import DomainError
from chem_vault.domain.shared.user_preferences import (
    UserPreferences,
    UserPreferencesRepository,
)


@dataclass(frozen=True, kw_only=True)
class UpdatePreferencesCommand(Command):
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    theme: str | None = None
    sidebar_collapsed: bool | None = None
    # Use UNSET sentinel so that explicit None means "clear", while omission means "don't change"
    default_search_columns: list[str] | None | object = UNSET


class UpdatePreferences:
    """Upserts user preferences with partial merge."""

    def __init__(self, repo: UserPreferencesRepository) -> None:
        self._repo = repo

    async def __call__(
        self, input: UpdatePreferencesCommand, auth: AuthContext | None = None
    ) -> Result[UserPreferences, DomainError]:
        require_editor(auth)
        prefs = await self._repo.get_by_user(input.workspace_id, input.user_id)

        if prefs is None:
            prefs = UserPreferences(
                workspace_id=input.workspace_id,
                user_id=input.user_id,
            )

        if input.theme is not None:
            prefs.theme = input.theme
        if input.sidebar_collapsed is not None:
            prefs.sidebar_collapsed = input.sidebar_collapsed
        if input.default_search_columns is not UNSET:
            prefs.default_search_columns = input.default_search_columns  # type: ignore[assignment]

        return Success(await self._repo.save(prefs))
