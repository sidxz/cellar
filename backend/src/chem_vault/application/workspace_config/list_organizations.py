"""ListOrganizations query — retrieve all organizations for a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.errors import DomainError
from chem_vault.domain.workspace_config.organization import Organization
from chem_vault.domain.workspace_config.repository import OrganizationRepository


@dataclass(frozen=True, kw_only=True)
class ListOrganizationsQuery(Query):
    workspace_id: uuid.UUID
    include_inactive: bool = False


class ListOrganizations:
    def __init__(self, uow: UnitOfWork, repo: OrganizationRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListOrganizationsQuery
    ) -> Result[list[Organization], DomainError]:
        async with self._uow:
            orgs = await self._repo.find_by_workspace(
                input.workspace_id, include_inactive=input.include_inactive
            )
            return Success(orgs)
