"""ListProtocolForms query — list protocol form templates for a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.errors import DomainError
from chem_vault.domain.workspace_config.protocol_form import ProtocolForm
from chem_vault.domain.workspace_config.repository import ProtocolFormRepository


@dataclass(frozen=True, kw_only=True)
class ListProtocolFormsQuery(Query):
    workspace_id: uuid.UUID


class ListProtocolForms:
    def __init__(self, uow: UnitOfWork, repo: ProtocolFormRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListProtocolFormsQuery
    ) -> Result[list[ProtocolForm], DomainError]:
        async with self._uow:
            results = await self._repo.find_by_workspace(input.workspace_id)
            return Success(results)
