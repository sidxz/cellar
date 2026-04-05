"""ListDisclosuresByWorkspace query — all disclosures in workspace, optional status filter."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.disclosure_request import DisclosureRequest
from chem_vault.domain.chemical_registration.repository import DisclosureRequestRepository
from chem_vault.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListDisclosuresByWorkspaceQuery(Query):
    workspace_id: uuid.UUID
    status: str | None = None


class ListDisclosuresByWorkspace:
    def __init__(
        self,
        uow: UnitOfWork,
        disclosure_repo: DisclosureRequestRepository,
    ) -> None:
        self._uow = uow
        self._disclosure_repo = disclosure_repo

    async def __call__(
        self, input: ListDisclosuresByWorkspaceQuery
    ) -> Result[list[DisclosureRequest], DomainError]:
        async with self._uow:
            disclosures = await self._disclosure_repo.find_by_workspace(
                input.workspace_id, status=input.status
            )
            return Success(disclosures)
