"""DeleteSavedSearch command — remove a saved search definition."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
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
    ) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: DeleteSavedSearchCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)

        async with self._uow:
            search = await self._repo.find_by_id(input.saved_search_id)
            if search is None or search.workspace_id != input.workspace_id:
                return Failure(
                    NotFoundError("SavedSearch", str(input.saved_search_id))
                )

            await self._repo.delete(input.saved_search_id)
            await self._uow.commit()
            return Success(None)
