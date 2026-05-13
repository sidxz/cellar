"""GetMoleculeByIdentifier query — look up a molecule by external identifier."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetMoleculeByIdentifierQuery(Query):
    workspace_id: uuid.UUID
    identifier: str


class GetMoleculeByIdentifier:
    """Query use case: find a molecule by any of its external identifiers.

    Looks up CAS numbers, ChEMBL IDs, vendor IDs, etc. via
    ``MoleculeRepository.find_by_identifier``.
    """

    def __init__(self, uow: UnitOfWork, repo: MoleculeRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetMoleculeByIdentifierQuery, auth: AuthContext | None = None
    ) -> Result[Molecule, DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            mol = await self._repo.find_by_identifier(input.workspace_id, input.identifier)
            if mol is None:
                return Failure(NotFoundError("Molecule", f"identifier={input.identifier}"))
            return Success(mol)
