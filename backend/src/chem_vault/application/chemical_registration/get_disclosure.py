"""GetDisclosure query — returns a single disclosure request by ID."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.disclosure_request import DisclosureRequest
from chem_vault.domain.chemical_registration.repository import (
    DisclosureRequestRepository,
    MoleculeRepository,
)
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetDisclosureQuery(Query):
    """Input for fetching a single disclosure request."""

    workspace_id: uuid.UUID
    disclosure_id: uuid.UUID


class GetDisclosure:
    """Query use case: fetch a disclosure request by its ID.

    Validates workspace isolation via the linked molecule.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        disclosure_repo: DisclosureRequestRepository,
        molecule_repo: MoleculeRepository,
    ) -> None:
        self._uow = uow
        self._disclosure_repo = disclosure_repo
        self._molecule_repo = molecule_repo

    async def __call__(
        self, input: GetDisclosureQuery
    ) -> Result[DisclosureRequest, DomainError]:
        async with self._uow:
            dr = await self._disclosure_repo.find_by_id(input.disclosure_id)
            if dr is None:
                return Failure(
                    NotFoundError("DisclosureRequest", str(input.disclosure_id))
                )
            # Workspace isolation: verify the linked molecule belongs to caller's workspace
            molecule = await self._molecule_repo.find_by_id(dr.molecule_id)
            if molecule is None or molecule.workspace_id != input.workspace_id:
                return Failure(
                    NotFoundError("DisclosureRequest", str(input.disclosure_id))
                )
            return Success(dr)
