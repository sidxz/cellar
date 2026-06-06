"""CreateCollection command — create a new molecule collection in a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.collection import Collection, CollectionVisibility
from cellar.domain.research_organization.enums import CollectionType
from cellar.domain.research_organization.repository import CollectionRepository
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class CreateCollectionCommand(Command):
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    project_id: uuid.UUID | None = None
    owned_by_org_id: uuid.UUID | None = None
    created_by: uuid.UUID
    visibility: str = "private"
    type: str = "generic"


class CreateCollection:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: CollectionRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: CreateCollectionCommand, auth: AuthContext | None = None
    ) -> Result[Collection, DomainError]:
        require_editor(auth)

        async with self._uow:
            collection = Collection.create(
                workspace_id=input.workspace_id,
                name=input.name,
                description=input.description,
                project_id=input.project_id,
                owned_by_org_id=input.owned_by_org_id,
                created_by=input.created_by,
                visibility=CollectionVisibility(input.visibility),
                type=CollectionType(input.type),
            )
            await self._repo.save(collection)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(collection)
