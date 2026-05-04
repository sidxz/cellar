"""CreateSavedSearch command — persist a reusable search definition."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.research_organization.repository import SavedSearchRepository
from chem_vault.domain.research_organization.saved_search import SavedSearch, SearchVisibility
from chem_vault.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class CreateSavedSearchCommand(Command):
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    query: dict[str, Any]
    columns: dict[str, Any] | None = None
    visibility: str = "private"
    project_id: uuid.UUID | None = None
    created_by: uuid.UUID


class CreateSavedSearch:
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
        self, input: CreateSavedSearchCommand, auth: AuthContext | None = None
    ) -> Result[SavedSearch, DomainError]:
        require_editor(auth)

        visibility = SearchVisibility(input.visibility)

        async with self._uow:
            search = SavedSearch.create(
                workspace_id=input.workspace_id,
                name=input.name,
                description=input.description,
                query=input.query,
                columns=input.columns,
                visibility=visibility,
                project_id=input.project_id,
                created_by=input.created_by,
            )
            await self._repo.save(search)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(search)
