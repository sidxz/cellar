"""ListBatchesGlobal query use case — all batches with molecule context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.auth import AuthContext, require_same_workspace
from chem_vault.application.shared.pagination import PageResult, clamp_limit, parse_cursor
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.inventory.repository import BatchRepository
from chem_vault.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListBatchesGlobalQuery(Query):
    workspace_id: uuid.UUID
    search: str | None = None
    sources: list[str] | None = None
    expiring_within_days: int | None = None
    cursor: str | None = None
    limit: int | None = None


class ListBatchesGlobal:
    def __init__(self, uow: UnitOfWork, repo: BatchRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        input: ListBatchesGlobalQuery,
        auth: AuthContext | None = None,
    ) -> Result[PageResult[dict], DomainError]:
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            result = await self._repo.list_global(
                input.workspace_id,
                search=input.search,
                sources=input.sources,
                expiring_within_days=input.expiring_within_days,
                cursor=parse_cursor(input.cursor),
                limit=clamp_limit(input.limit),
            )
            return Success(result)
