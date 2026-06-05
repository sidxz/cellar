"""DeleteTag — remove a tag and (via DB CASCADE) all its links (admin)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_admin
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError
from cellar.domain.workspace_config.tagging.events import TagDeleted
from cellar.domain.workspace_config.tagging.repository import TagRepository


@dataclass(frozen=True, kw_only=True)
class DeleteTagCommand(Command):
    workspace_id: uuid.UUID
    tag_id: uuid.UUID


class DeleteTag:
    def __init__(
        self,
        uow: UnitOfWork,
        tag_repo: TagRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._tag_repo = tag_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: DeleteTagCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_admin(auth)

        async with self._uow:
            tag = await self._tag_repo.find_by_id_in_workspace(input.workspace_id, input.tag_id)
            if tag is None:
                return Failure(NotFoundError("Tag", str(input.tag_id)))

            tag.register_event(
                TagDeleted(
                    aggregate_id=tag.id,
                    aggregate_type="Tag",
                    workspace_id=input.workspace_id,
                    key=tag.key,
                    value=tag.value,
                )
            )
            self._uow.track(tag)
            await self._tag_repo.delete(input.workspace_id, tag.id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)
