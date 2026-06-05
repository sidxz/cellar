"""RenameTag — change a tag's key/value (admin)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_admin
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)
from cellar.domain.workspace_config.tagging.repository import TagRepository
from cellar.domain.workspace_config.tagging.tag import Tag, TagName


@dataclass(frozen=True, kw_only=True)
class RenameTagCommand(Command):
    workspace_id: uuid.UUID
    tag_id: uuid.UUID
    key: str
    value: str | None


class RenameTag:
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
        self, input: RenameTagCommand, auth: AuthContext | None = None
    ) -> Result[Tag, DomainError]:
        require_admin(auth)
        try:
            new_name = TagName(key=input.key, value=input.value)
        except ValueError as exc:
            return Failure(ValidationError(str(exc)))

        async with self._uow:
            tag = await self._tag_repo.find_by_id_in_workspace(input.workspace_id, input.tag_id)
            if tag is None:
                return Failure(NotFoundError("Tag", str(input.tag_id)))

            existing = await self._tag_repo.find_by_normalized(input.workspace_id, new_name)
            if existing is not None and existing.id != tag.id:
                return Failure(
                    ConflictError(
                        f"A tag '{new_name.key}' already exists — merge instead of rename"
                    )
                )

            tag.rename(new_name)
            self._uow.track(tag)
            await self._tag_repo.save(tag)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(tag)
