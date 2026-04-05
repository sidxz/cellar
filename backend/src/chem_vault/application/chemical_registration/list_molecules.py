"""ListMolecules query — retrieve active molecules for a workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.shared.pagination import PageResult
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
    search_term: str | None = None
    cursor_id: uuid.UUID | None = None
    limit: int | None = None


class ListMolecules:
    def __init__(self, uow: UnitOfWork, repo: MoleculeRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListMoleculesQuery
    ) -> Result[PageResult[Molecule], DomainError]:
        async with self._uow:
            filters = {}
            if input.molecule_type:
                filters["molecule_type"] = input.molecule_type
            if input.lifecycle_stage:
                filters["lifecycle_stage"] = input.lifecycle_stage
            if input.structure_status:
                filters["structure_status"] = input.structure_status

            # Fetch one extra row to detect whether a next page exists.
            effective_limit = input.limit
            fetch_limit = effective_limit + 1 if effective_limit is not None else None

            mols = await self._repo.find_active(
                input.workspace_id,
                filters=filters or None,
                search_term=input.search_term,
                cursor_id=input.cursor_id,
                limit=fetch_limit,
            )

            # Determine next_cursor from the extra row.
            next_cursor: str | None = None
            if effective_limit is not None and len(mols) > effective_limit:
                mols = mols[:effective_limit]
                next_cursor = str(mols[-1].id)

            return Success(PageResult(items=mols, next_cursor=next_cursor))
