"""ListFavorites — the current user's favorites of a given entity type."""

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
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.personalization.enums import FavoriteEntityType
from cellar.domain.personalization.favorite import Favorite
from cellar.domain.personalization.repository import FavoriteRepository
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListFavoritesQuery(Query):
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    entity_type: FavoriteEntityType


class ListFavorites:
    def __init__(self, uow: UnitOfWork, repo: FavoriteRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListFavoritesQuery, auth: AuthContext | None = None
    ) -> Result[list[Favorite], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        require_same_user(auth, input.user_id)
        async with self._uow:
            favorites = await self._repo.list_for_user(
                input.workspace_id, input.user_id, input.entity_type
            )
            return Success(favorites)
