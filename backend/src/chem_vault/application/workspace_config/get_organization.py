"""GetOrganization query — retrieve a single organization by ID."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_workspace_role
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.errors import DomainError, NotFoundError
from chem_vault.domain.workspace_config.organization import Organization
from chem_vault.domain.workspace_config.repository import OrganizationRepository


@dataclass(frozen=True, kw_only=True)
class GetOrganizationQuery(Query):
    workspace_id: uuid.UUID
    org_id: uuid.UUID


class GetOrganization:
    def __init__(self, uow: UnitOfWork, repo: OrganizationRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetOrganizationQuery, auth: AuthContext | None = None
    ) -> Result[Organization, DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            org = await self._repo.find_by_id_in_workspace(input.workspace_id, input.org_id)
            if org is None:
                return Failure(NotFoundError("Organization", str(input.org_id)))
            return Success(org)
