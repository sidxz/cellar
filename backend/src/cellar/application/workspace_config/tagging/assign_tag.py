"""AssignTag — apply a (key, optional value) tag to an entity."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError
from cellar.domain.workspace_config.tagging.events import TagAssigned
from cellar.domain.workspace_config.tagging.repository import (
    TagLinkRepositoryProvider,
    TagRepository,
)
from cellar.domain.workspace_config.tagging.tag import Tag, TaggableEntityType, TagName


@dataclass(frozen=True, kw_only=True)
class AssignTagCommand(Command):
    workspace_id: uuid.UUID
    entity_type: TaggableEntityType
    entity_id: uuid.UUID
    key: str
    value: str | None
    assigned_by: uuid.UUID


class AssignTag:
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
        self, input: AssignTagCommand, auth: AuthContext | None = None
    ) -> Result[Tag, DomainError]:
        require_editor(auth)
        try:
            name = TagName(key=input.key, value=input.value)
        except ValueError as exc:
            return Failure(ValidationError(str(exc)))

        async with self._uow:
            link_repo = self._link_provider.for_type(input.entity_type)
            if not await link_repo.entity_exists_in_workspace(
                input.workspace_id, input.entity_id
            ):
                return Failure(NotFoundError(input.entity_type.value, str(input.entity_id)))

            tag = await self._tag_repo.get_or_create(
                input.workspace_id, name, input.assigned_by
            )
            tag.register_event(
                TagAssigned(
                    aggregate_id=tag.id,
                    aggregate_type="Tag",
                    workspace_id=input.workspace_id,
                    target_type=input.entity_type.value,
                    target_id=input.entity_id,
                )
            )
            self._uow.track(tag)
            await link_repo.add(
                input.workspace_id, input.entity_id, tag.id, input.assigned_by
            )
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(tag)
