"""MergeTags — fold a source tag into a target, repointing all links (admin)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_admin, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError
from cellar.domain.workspace_config.tagging.events import TagMerged
from cellar.domain.workspace_config.tagging.repository import (
    TagLinkRepositoryProvider,
    TagRepository,
)
from cellar.domain.workspace_config.tagging.tag import Tag, TaggableEntityType


@dataclass(frozen=True, kw_only=True)
class MergeTagsCommand(Command):
    workspace_id: uuid.UUID
    source_tag_id: uuid.UUID
    target_tag_id: uuid.UUID


class MergeTags:
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
        self, input: MergeTagsCommand, auth: AuthContext | None = None
    ) -> Result[Tag, DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)
        if input.source_tag_id == input.target_tag_id:
            return Failure(ValidationError("Cannot merge a tag into itself"))

        async with self._uow:
            source = await self._tag_repo.find_by_id_in_workspace(
                input.workspace_id, input.source_tag_id
            )
            if source is None:
                return Failure(NotFoundError("Tag", str(input.source_tag_id)))
            target = await self._tag_repo.find_by_id_in_workspace(
                input.workspace_id, input.target_tag_id
            )
            if target is None:
                return Failure(NotFoundError("Tag", str(input.target_tag_id)))

            for entity_type in TaggableEntityType:
                link_repo = self._link_provider.for_type(entity_type)
                await link_repo.repoint(source.id, target.id)

            source.register_event(
                TagMerged(
                    aggregate_id=source.id,
                    aggregate_type="Tag",
                    workspace_id=input.workspace_id,
                    target_tag_id=target.id,
                )
            )
            self._uow.track(source)
            await self._tag_repo.delete(input.workspace_id, source.id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(target)
