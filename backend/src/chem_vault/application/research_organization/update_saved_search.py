"""UpdateSavedSearch command — partial update of a saved search."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.application.shared.sentinel import UNSET
from chem_vault.domain.research_organization.repository import SavedSearchRepository
from chem_vault.domain.research_organization.saved_search import SavedSearch, SearchVisibility
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class UpdateSavedSearchCommand(Command):
    workspace_id: uuid.UUID
    saved_search_id: uuid.UUID
    name: str | None = None
    description: str | None | object = UNSET
    query: dict[str, Any] | None = None
    columns: dict[str, Any] | None | object = UNSET
    visibility: str | None = None
    project_id: uuid.UUID | None | object = UNSET


class UpdateSavedSearch:
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
        self, input: UpdateSavedSearchCommand, auth: AuthContext | None = None
    ) -> Result[SavedSearch, DomainError]:
        require_editor(auth)

        async with self._uow:
            search = await self._repo.find_by_id_in_workspace(input.workspace_id, input.saved_search_id)
            if search is None:
                return Failure(
                    NotFoundError("SavedSearch", str(input.saved_search_id))
                )

            # Build kwargs — only include fields that were provided
            fields: dict[str, Any] = {}
            if input.name is not None:
                fields["name"] = input.name
            if input.description is not UNSET:
                fields["description"] = input.description
            if input.query is not None:
                fields["query"] = input.query
            if input.columns is not UNSET:
                fields["columns"] = input.columns
            if input.visibility is not None:
                fields["visibility"] = SearchVisibility(input.visibility)
            if input.project_id is not UNSET:
                fields["project_id"] = input.project_id

            if fields:
                search.update(**fields)
            await self._repo.save(search)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(search)
