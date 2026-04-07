"""ListSaltEntries query — list salt catalog entries for a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.shared.query import Query
from chem_vault.domain.shared.errors import DomainError
from chem_vault.domain.workspace_config.salt_entry import SaltEntry
from chem_vault.domain.workspace_config.repository import SaltEntryRepository


@dataclass(frozen=True, kw_only=True)
class ListSaltEntriesQuery(Query):
    workspace_id: uuid.UUID
    active_only: bool = True


class ListSaltEntries:
    def __init__(self, repo: SaltEntryRepository) -> None:
        self._repo = repo

    async def __call__(
        self, input: ListSaltEntriesQuery
    ) -> Result[list[SaltEntry], DomainError]:
        results = await self._repo.find_by_workspace(
            input.workspace_id,
            active_only=input.active_only,
        )
        return Success(results)
