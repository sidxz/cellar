"""ClearRecentSearches — forget the user's search history in a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import (
    AuthContext,
    require_same_user,
    require_same_workspace,
    require_workspace_role,
)
from cellar.application.shared.command import Command
from cellar.domain.personalization.repository import RecentSearchRepository
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ClearRecentSearchesCommand(Command):
    workspace_id: uuid.UUID
    user_id: uuid.UUID


class ClearRecentSearches:
    def __init__(self, repo: RecentSearchRepository) -> None:
        self._repo = repo

    async def __call__(
        self, input: ClearRecentSearchesCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        require_same_user(auth, input.user_id)
        await self._repo.clear(input.workspace_id, input.user_id)
        return Success(None)
