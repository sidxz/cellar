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

    workspace_id: uuid.UUID
    disclosure_id: uuid.UUID


class GetDisclosure:
    """Query use case: fetch a disclosure request by its ID.

    Workspace isolation enforced by ``find_by_id_in_workspace``.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        disclosure_repo: DisclosureRequestRepository,
    ) -> None:
        self._uow = uow
        self._disclosure_repo = disclosure_repo

    async def __call__(
        self, input: GetDisclosureQuery
    ) -> Result[DisclosureRequest, DomainError]:
        async with self._uow:
            dr = await self._disclosure_repo.find_by_id_in_workspace(input.workspace_id, input.disclosure_id)
            if dr is None:
                return Failure(
                    NotFoundError("DisclosureRequest", str(input.disclosure_id))
                )
            return Success(dr)
