"""DeleteSavedSearch command — remove a saved search definition."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.research_organization.repository import SavedSearchRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class DeleteSavedSearchCommand(Command):
    workspace_id: uuid.UUID
    saved_search_id: uuid.UUID


class DeleteSavedSearch:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SavedSearchRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: DeleteSavedSearchCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)

        async with self._uow:
            search = await self._repo.find_by_id_in_workspace(input.workspace_id, input.saved_search_id)
            if search is None:
                return Failure(
                    NotFoundError("SavedSearch", str(input.saved_search_id))
                )

            await self._repo.delete(input.workspace_id, input.saved_search_id)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(None)
