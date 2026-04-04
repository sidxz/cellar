"""ListRelationships query — retrieve all relationships for a molecule."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.molecule_relationship import MoleculeRelationship
from chem_vault.domain.chemical_registration.repository import (
    MoleculeRelationshipRepository,
    MoleculeRepository,
)
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class ListRelationshipsQuery(Query):
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID


class ListRelationships:
    """Query use case: list all relationships where molecule is source or target."""

    def __init__(
        self,
        uow: UnitOfWork,
        molecule_repo: MoleculeRepository,
        relationship_repo: MoleculeRelationshipRepository,
    ) -> None:
        self._uow = uow
        self._molecule_repo = molecule_repo
        self._relationship_repo = relationship_repo

    async def __call__(
        self, input: ListRelationshipsQuery
    ) -> Result[list[MoleculeRelationship], DomainError]:
        async with self._uow:
            # Workspace isolation
            mol = await self._molecule_repo.find_by_id(input.molecule_id)
            if mol is None or mol.workspace_id != input.workspace_id:
                return Failure(NotFoundError("Molecule", str(input.molecule_id)))

            as_source = await self._relationship_repo.find_by_source(input.molecule_id)
            as_target = await self._relationship_repo.find_by_target(input.molecule_id)

            # Deduplicate (shouldn't overlap, but safe)
            seen = set()
            combined = []
            for rel in as_source + as_target:
                if rel.id not in seen:
                    seen.add(rel.id)
                    combined.append(rel)

            return Success(combined)
