"""RemoveFavorite — un-favorite an entity for the current user (no-op if absent)."""

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
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.personalization.enums import FavoriteEntityType
from cellar.domain.personalization.repository import FavoriteRepository
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class RemoveFavoriteCommand(Command):
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    entity_type: FavoriteEntityType
    entity_id: uuid.UUID


class RemoveFavorite:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: FavoriteRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: RemoveFavoriteCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        require_same_user(auth, input.user_id)

        async with self._uow:
            await self._repo.remove(
                input.workspace_id, input.user_id, input.entity_type, input.entity_id
            )
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)
