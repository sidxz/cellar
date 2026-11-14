"""RecordRecentSearch — remember a search the user just ran."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_same_user,
    require_same_workspace,
    require_workspace_role,
)
from cellar.application.shared.command import Command
from cellar.domain.personalization.recent_search import MAX_RECENT_SEARCHES, RecentSearch
from cellar.domain.personalization.repository import RecentSearchRepository
from cellar.domain.shared.errors import DomainError, ValidationError


@dataclass(frozen=True, kw_only=True)
class RecordRecentSearchCommand(Command):
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    query: dict[str, Any]
    columns: dict[str, Any] | None = None
    result_count: int | None = None


class RecordRecentSearch:
    """Put a search at the top of the user's history (moving it if already there).

    No UnitOfWork or events — plain-CRUD history, see ``RecentSearch``.
    """

    def __init__(self, repo: RecentSearchRepository) -> None:
        self._repo = repo

    async def __call__(
        self, input: RecordRecentSearchCommand, auth: AuthContext | None = None
    ) -> Result[RecentSearch, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        require_same_user(auth, input.user_id)
        try:
            search = RecentSearch.record(
                workspace_id=input.workspace_id,
                user_id=input.user_id,
                query=input.query,
                columns=input.columns,
                result_count=input.result_count,
            )
        except ValidationError as error:
            return Failure(error)
        return Success(await self._repo.record(search, keep=MAX_RECENT_SEARCHES))
