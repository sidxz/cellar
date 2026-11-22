"""Hand a record to another Duar org: an admin or the record's creator, to an enabled org.

One implementation for every owned record (collections, projects, protocols); each
context binds it to its repository with a one-line subclass.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, ClassVar, Protocol

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_admin_or_user,
    require_authenticated,
    require_editor,
    require_same_workspace,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.org_directory import OrgDirectoryPort, unpickable_org
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError


class Owned(Protocol):
    created_by: uuid.UUID

    def change_owner(self, owner_org_id: uuid.UUID) -> None: ...


@dataclass(frozen=True, kw_only=True)
class ChangeOwnerCommand(Command):
    workspace_id: uuid.UUID
    entity_id: uuid.UUID
    owner_org_id: uuid.UUID


class ChangeOwner[T: Owned]:
    entity_name: ClassVar[str]

    def __init__(
        self,
        uow: UnitOfWork,
        repo: Any,
        dispatcher: EventDispatcherProtocol,
        org_directory: OrgDirectoryPort,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._org_directory = org_directory

    async def __call__(
        self, input: ChangeOwnerCommand, auth: AuthContext | None = None
    ) -> Result[T, DomainError]:
        require_authenticated(auth)
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            entity = await self._repo.find_by_id_in_workspace(input.workspace_id, input.entity_id)
            if entity is None:
                return Failure(NotFoundError(self.entity_name, str(input.entity_id)))
            require_admin_or_user(auth, entity.created_by)
            if (err := await unpickable_org(self._org_directory, input.owner_org_id)) is not None:
                return Failure(err)
            try:
                entity.change_owner(input.owner_org_id)
            except DomainError as e:
                return Failure(e)
            await self._repo.save(entity)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(entity)
