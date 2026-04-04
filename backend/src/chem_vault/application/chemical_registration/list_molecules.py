"""ListMolecules query — retrieve active molecules for a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.molecule import Molecule
from chem_vault.domain.chemical_registration.repository import MoleculeRepository
from chem_vault.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListMoleculesQuery(Query):
    workspace_id: uuid.UUID
    molecule_type: str | None = None
    lifecycle_stage: str | None = None
    structure_status: str | None = None


class ListMolecules:
    def __init__(self, uow: UnitOfWork, repo: MoleculeRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListMoleculesQuery
    ) -> Result[list[Molecule], DomainError]:
        async with self._uow:
            filters = {}
            if input.molecule_type:
                filters["molecule_type"] = input.molecule_type
            if input.lifecycle_stage:
                filters["lifecycle_stage"] = input.lifecycle_stage
            if input.structure_status:
                filters["structure_status"] = input.structure_status

            mols = await self._repo.find_active(
                input.workspace_id, filters=filters or None
            )
            return Success(mols)
