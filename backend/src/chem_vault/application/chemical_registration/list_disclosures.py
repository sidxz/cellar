"""ListDisclosures query — returns all disclosure requests for a molecule."""

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
class ListDisclosuresQuery(Query):
    """Input for listing disclosure requests by molecule."""

    workspace_id: uuid.UUID
    molecule_id: uuid.UUID


class ListDisclosures:
    """Query use case: list all disclosure requests for a given molecule.

    Validates workspace isolation via the molecule.
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
        self, input: ListDisclosuresQuery
    ) -> Result[list[DisclosureRequest], DomainError]:
        async with self._uow:
            # Workspace isolation: verify molecule belongs to caller's workspace
            molecule = await self._molecule_repo.find_by_id(input.molecule_id)
            if molecule is None or molecule.workspace_id != input.workspace_id:
                return Failure(
                    NotFoundError("Molecule", str(input.molecule_id))
                )
            disclosures = await self._disclosure_repo.find_by_molecule(input.molecule_id)
            return Success(disclosures)
