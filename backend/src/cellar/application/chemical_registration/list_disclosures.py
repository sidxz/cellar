"""ListDisclosures query — returns all disclosure requests for a molecule."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.disclosure_request import DisclosureRequest
from cellar.domain.chemical_registration.repository import (
    DisclosureRequestRepository,
    MoleculeRepository,
)
from cellar.domain.shared.errors import DomainError, NotFoundError


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
        self, input: ListDisclosuresQuery, auth: AuthContext | None = None
    ) -> Result[list[DisclosureRequest], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            # Workspace isolation: verify molecule belongs to caller's workspace
            molecule = await self._molecule_repo.find_by_id_in_workspace(
                input.workspace_id, input.molecule_id
            )
            if molecule is None:
                return Failure(NotFoundError("Molecule", str(input.molecule_id)))
            disclosures = await self._disclosure_repo.find_by_molecule(
                input.workspace_id, input.molecule_id
            )
            return Success(disclosures)
