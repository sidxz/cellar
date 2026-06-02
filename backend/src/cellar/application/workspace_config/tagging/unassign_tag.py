"""UnassignTag — remove a tag from an entity."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError
from cellar.domain.workspace_config.tagging.events import TagUnassigned
from cellar.domain.workspace_config.tagging.repository import (
    TagLinkRepositoryProvider,
    TagRepository,
)
from cellar.domain.workspace_config.tagging.tag import TaggableEntityType


@dataclass(frozen=True, kw_only=True)
class UnassignTagCommand(Command):
    workspace_id: uuid.UUID
    entity_type: TaggableEntityType
    entity_id: uuid.UUID
    tag_id: uuid.UUID


class UnassignTag:
    def __init__(
        self,
        uow: UnitOfWork,
        tag_repo: TagRepository,
        link_provider: TagLinkRepositoryProvider,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._tag_repo = tag_repo
        self._link_provider = link_provider
        self._dispatcher = dispatcher

    async def __call__(
        self, input: UnassignTagCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)

        async with self._uow:
            tag = await self._tag_repo.find_by_id_in_workspace(
                input.workspace_id, input.tag_id
            )
            if tag is None:
                return Failure(NotFoundError("Tag", str(input.tag_id)))

            link_repo = self._link_provider.for_type(input.entity_type)
            if not await link_repo.entity_exists_in_workspace(
                input.workspace_id, input.entity_id
            ):
                return Failure(NotFoundError(input.entity_type.value, str(input.entity_id)))

            await link_repo.remove(input.workspace_id, input.entity_id, input.tag_id)
            tag.register_event(
                TagUnassigned(
                    aggregate_id=tag.id,
                    aggregate_type="Tag",
                    workspace_id=input.workspace_id,
                    target_type=input.entity_type.value,
                    target_id=input.entity_id,
                )
            )
            self._uow.track(tag)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)
