"""ListSaltEntries query — list salt catalog entries for a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError
from cellar.domain.workspace_config.salt_entry import SaltEntry
from cellar.domain.workspace_config.repository import SaltEntryRepository


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
