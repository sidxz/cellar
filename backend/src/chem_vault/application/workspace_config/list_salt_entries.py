"""ListSaltEntries query — list salt catalog entries for a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.auth import AuthContext, require_workspace_role
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.errors import DomainError
from chem_vault.domain.workspace_config.salt_entry import SaltEntry
from chem_vault.domain.workspace_config.repository import SaltEntryRepository


@dataclass(frozen=True, kw_only=True)
class ListSaltEntriesQuery(Query):
    workspace_id: uuid.UUID
    active_only: bool = True


class ListSaltEntries:
    def __init__(self, uow: UnitOfWork, repo: SaltEntryRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListSaltEntriesQuery, auth: AuthContext | None = None
    ) -> Result[list[SaltEntry], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            results = await self._repo.find_by_workspace(
                input.workspace_id,
                active_only=input.active_only,
            )
            return Success(results)
