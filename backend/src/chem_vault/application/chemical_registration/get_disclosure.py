"""GetDisclosure query — returns a single disclosure request by ID."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.disclosure_request import DisclosureRequest
from chem_vault.domain.chemical_registration.repository import DisclosureRequestRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetDisclosureQuery(Query):
    """Input for fetching a single disclosure request."""

    disclosure_id: uuid.UUID


class GetDisclosure:
    """Query use case: fetch a disclosure request by its ID."""

    def __init__(self, uow: UnitOfWork, repo: DisclosureRequestRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetDisclosureQuery
    ) -> Result[DisclosureRequest, DomainError]:
        async with self._uow:
            dr = await self._repo.find_by_id(input.disclosure_id)
            if dr is None:
                return Failure(
                    NotFoundError("DisclosureRequest", str(input.disclosure_id))
                )
            return Success(dr)
