"""AddFavorite — idempotently favorite an entity for the current user."""

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
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.personalization.enums import FavoriteEntityType
from cellar.domain.personalization.favorite import Favorite
from cellar.domain.personalization.repository import FavoriteRepository
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class AddFavoriteCommand(Command):
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    entity_type: FavoriteEntityType
    entity_id: uuid.UUID


class AddFavorite:
    """Idempotently favorite an entity for the current user.

    No domain events — see Favorite aggregate. ``uow.commit()`` always returns
    an empty list, so no EventDispatcher is wired.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        repo: FavoriteRepository,
    ) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: AddFavoriteCommand, auth: AuthContext | None = None
    ) -> Result[Favorite, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        require_same_user(auth, input.user_id)

        async with self._uow:
            existing = await self._repo.find_by_entity(
                input.workspace_id, input.user_id, input.entity_type, input.entity_id
            )
            if existing is not None:
                return Success(existing)  # idempotent

            favorite = Favorite.create(
                workspace_id=input.workspace_id,
                user_id=input.user_id,
                entity_type=input.entity_type,
                entity_id=input.entity_id,
            )
            await self._repo.save(favorite)
            # No domain events to dispatch — see Favorite aggregate.
            await self._uow.commit()

        return Success(favorite)
