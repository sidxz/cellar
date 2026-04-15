"""GetDataSource query — fetch a single data source by ID."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.errors import DomainError, NotFoundError
from chem_vault.domain.workspace_config.data_source import DataSource
from chem_vault.domain.workspace_config.repository import DataSourceRepository


@dataclass(frozen=True, kw_only=True)
class GetDataSourceQuery(Query):
    workspace_id: uuid.UUID
    data_source_id: uuid.UUID


class GetDataSource:
    def __init__(self, uow: UnitOfWork, repo: DataSourceRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetDataSourceQuery
    ) -> Result[DataSource, DomainError]:
        async with self._uow:
            ds = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.data_source_id
            )
            if ds is None:
                return Failure(NotFoundError("DataSource", str(input.data_source_id)))
            return Success(ds)
