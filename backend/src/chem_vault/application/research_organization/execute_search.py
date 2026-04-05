"""ExecuteSearch -- run a compound query (inline or from SavedSearch)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from chem_vault.application.shared.pagination import PageResult
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.molecule import Molecule
from chem_vault.domain.chemical_registration.repository import MoleculeRepository
from chem_vault.domain.research_organization.repository import SavedSearchRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError, ValidationError


@dataclass(frozen=True, kw_only=True)
class ExecuteSearchQuery(Query):
    workspace_id: uuid.UUID
    saved_search_id: uuid.UUID | None = None
    query: dict[str, Any] | None = None
    cursor_id: uuid.UUID | None = None
    limit: int = 50


class ExecuteSearch:
    """Execute a compound search -- either by saved_search_id or inline query dict.

    Resolves the query dict (from SavedSearch or inline), then delegates
    the composed query execution to MoleculeRepository.search_by_query().
    """

    def __init__(
        self,
        uow: UnitOfWork,
        molecule_repo: MoleculeRepository,
        saved_search_repo: SavedSearchRepository,
    ) -> None:
        self._uow = uow
        self._mol_repo = molecule_repo
        self._ss_repo = saved_search_repo

    async def __call__(
        self, input: ExecuteSearchQuery
    ) -> Result[PageResult[Molecule], DomainError]:
        if input.saved_search_id is None and input.query is None:
            return Failure(
                ValidationError("Provide either saved_search_id or query.")
            )

        async with self._uow:
            # Resolve query dict
            if input.saved_search_id is not None:
                ss = await self._ss_repo.find_by_id(input.saved_search_id)
                if ss is None or ss.workspace_id != input.workspace_id:
                    return Failure(NotFoundError("SavedSearch", str(input.saved_search_id)))
                query_dict = ss.query
            else:
                query_dict = input.query  # type: ignore[assignment]

            # Delegate to repository — fetch limit + 1 for next_cursor detection
            fetch_limit = input.limit + 1
            try:
                molecules = await self._mol_repo.search_by_query(
                    input.workspace_id,
                    query_dict,
                    cursor_id=input.cursor_id,
                    limit=fetch_limit,
                )
            except ValueError as e:
                return Failure(ValidationError(str(e)))

            # Determine next_cursor
            next_cursor: str | None = None
            if len(molecules) > input.limit:
                molecules = molecules[: input.limit]
                next_cursor = str(molecules[-1].id)

            return Success(PageResult(items=molecules, next_cursor=next_cursor))
