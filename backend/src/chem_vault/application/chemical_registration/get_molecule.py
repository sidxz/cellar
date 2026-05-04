"""GetMolecule query — retrieve a single molecule by ID."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_same_workspace
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.molecule import Molecule
from chem_vault.domain.chemical_registration.repository import MoleculeRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetMoleculeQuery(Query):
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID


class GetMolecule:
    def __init__(self, uow: UnitOfWork, repo: MoleculeRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetMoleculeQuery, auth: AuthContext | None = None
    ) -> Result[Molecule, DomainError]:
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            mol = await self._repo.find_by_id_in_workspace(input.workspace_id, input.molecule_id)
            if mol is None:
                return Failure(NotFoundError("Molecule", str(input.molecule_id)))
            return Success(mol)
