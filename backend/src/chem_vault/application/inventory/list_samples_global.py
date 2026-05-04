"""ListSamplesGlobal query use case — all samples with batch/molecule/location context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.auth import AuthContext, require_same_workspace
from chem_vault.application.shared.pagination import PageResult, clamp_limit, parse_cursor
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.inventory.repository import SampleRepository
from chem_vault.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListSamplesGlobalQuery(Query):
    workspace_id: uuid.UUID
    search: str | None = None
    statuses: list[str] | None = None
    location_id: uuid.UUID | None = None
    container_types: list[str] | None = None
    low_stock: bool = False
    cursor: str | None = None
    limit: int | None = None


class ListSamplesGlobal:
    def __init__(self, uow: UnitOfWork, repo: SampleRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self,
        input: ListSamplesGlobalQuery,
        auth: AuthContext | None = None,
    ) -> Result[PageResult[dict], DomainError]:
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            result = await self._repo.list_global(
                input.workspace_id,
                search=input.search,
                statuses=input.statuses,
                location_id=input.location_id,
                container_types=input.container_types,
                low_stock=input.low_stock,
                cursor=parse_cursor(input.cursor),
                limit=clamp_limit(input.limit),
            )
            return Success(result)
