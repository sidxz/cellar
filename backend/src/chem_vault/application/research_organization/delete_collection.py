"""DeleteCollection command — remove a collection and its membership."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.research_organization.repository import CollectionRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class DeleteCollectionCommand(Command):
    workspace_id: uuid.UUID
    collection_id: uuid.UUID


class DeleteCollection:
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
        self, input: DeleteCollectionCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)

        async with self._uow:
            collection = await self._repo.find_by_id_in_workspace(input.workspace_id, input.collection_id)
            if collection is None:
                return Failure(NotFoundError("Collection", str(input.collection_id)))

            await self._repo.delete(input.workspace_id, input.collection_id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)
