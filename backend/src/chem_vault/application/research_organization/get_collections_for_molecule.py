"""ListCollectionsForMolecule query — collections containing a molecule."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.research_organization.collection import Collection
from chem_vault.domain.research_organization.repository import CollectionRepository
from chem_vault.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListCollectionsForMoleculeQuery(Query):
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID


class ListCollectionsForMolecule:
    def __init__(self, uow: UnitOfWork, repo: CollectionRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListCollectionsForMoleculeQuery
    ) -> Result[list[Collection], DomainError]:
        async with self._uow:
            collections = await self._repo.find_collections_containing(
                input.workspace_id, input.molecule_id
            )
            return Success(collections)
