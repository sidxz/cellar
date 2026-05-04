"""ListCompoundFlags query use case."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.auth import AuthContext, require_same_workspace
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.compound_flag import CompoundFlag
from chem_vault.domain.screening_assay.repository import CompoundFlagRepository
from chem_vault.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListCompoundFlagsQuery(Query):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID


class ListCompoundFlags:
    def __init__(self, uow: UnitOfWork, repo: CompoundFlagRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListCompoundFlagsQuery, auth: AuthContext | None = None
    ) -> Result[list[CompoundFlag], DomainError]:
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            flags = await self._repo.list_by_protocol(input.workspace_id, input.protocol_id)
            return Success(flags)
