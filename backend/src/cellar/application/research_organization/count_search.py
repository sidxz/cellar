"""CountSearch -- count matches for a compound query without materializing rows.

Lightweight sibling of ExecuteSearch used to power the live "Search N compounds"
preview on the search panel. Skips similarity scoring, activity enrichment,
pagination, and saved-search write-back -- the only call that hits the DB is
``MoleculeReader.count_by_query``, which is a ``SELECT COUNT(*)`` over the
composed WHERE clause.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace
from cellar.application.chemical_registration.molecule_reader import MoleculeReader
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.repository import SavedSearchRepository
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError


@dataclass(frozen=True, kw_only=True)
class CountSearchQuery(Query):
    workspace_id: uuid.UUID
    saved_search_id: uuid.UUID | None = None
    query: dict[str, Any] | None = None
    project_ids: list[uuid.UUID] | None = None


class CountSearch:
    """Count molecules matching a compound query.

    Accepts either a saved search id or an inline query dict, mirroring
    ``ExecuteSearch``. Returns the total count as an integer.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        molecule_reader: MoleculeReader,
        saved_search_repo: SavedSearchRepository,
    ) -> None:
        self._uow = uow
        self._mol_reader = molecule_reader
        self._ss_repo = saved_search_repo

    async def __call__(
        self, input: CountSearchQuery, auth: AuthContext | None = None
    ) -> Result[int, DomainError]:
        require_same_workspace(auth, input.workspace_id)
        if input.saved_search_id is None and input.query is None:
            return Failure(ValidationError("Provide either saved_search_id or query."))

        async with self._uow:
            if input.saved_search_id is not None:
                ss = await self._ss_repo.find_by_id_in_workspace(
                    input.workspace_id, input.saved_search_id
                )
                if ss is None:
                    return Failure(NotFoundError("SavedSearch", str(input.saved_search_id)))
                query_dict = ss.query
            else:
                query_dict = input.query  # type: ignore[assignment]

            try:
                total = await self._mol_reader.count_by_query(
                    input.workspace_id,
                    query_dict,
                    project_ids=input.project_ids,
                )
            except ValueError as e:
                return Failure(ValidationError(str(e)))

            return Success(total)
