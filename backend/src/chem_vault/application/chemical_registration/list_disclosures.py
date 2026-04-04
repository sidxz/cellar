"""ListDisclosures query — returns all disclosure requests for a molecule."""

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
class ListDisclosuresQuery(Query):
    """Input for listing disclosure requests by molecule."""

    molecule_id: uuid.UUID


class ListDisclosures:
    """Query use case: list all disclosure requests for a given molecule."""

    def __init__(self, uow: UnitOfWork, repo: DisclosureRequestRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListDisclosuresQuery
    ) -> Result[list[DisclosureRequest], DomainError]:
        async with self._uow:
            disclosures = await self._repo.find_by_molecule(input.molecule_id)
            return Success(disclosures)
