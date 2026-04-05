"""ExecuteSearch -- run a compound query (inline or from SavedSearch)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success
from sqlalchemy import select, text

from chem_vault.application.shared.pagination import PageResult
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.search_query_composer import compose_criteria
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
    """Execute a compound search -- either by saved_search_id or inline query dict."""

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

            # Check for similarity criterion -- need to SET threshold before query
            similarity_threshold: float | None = None
            for criterion in query_dict.get("criteria", []):
                if (
                    criterion.get("type") == "structure"
                    and criterion.get("search_type") == "similarity"
                ):
                    similarity_threshold = float(criterion.get("threshold", 0.7))
                    break

            # Compose WHERE clause
            try:
                where_clause = compose_criteria(query_dict)
            except ValueError as e:
                return Failure(ValidationError(str(e)))

            # Build query
            from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
                MoleculeModel,
            )

            stmt = select(MoleculeModel).where(
                MoleculeModel.workspace_id == input.workspace_id,
                MoleculeModel.merged_into_id.is_(None),
            )

            # Require disclosed structure for structure searches
            has_structure_criterion = any(
                c.get("type") == "structure" for c in query_dict.get("criteria", [])
            )
            if has_structure_criterion:
                stmt = stmt.where(MoleculeModel.smiles.is_not(None))

            if where_clause is not None:
                stmt = stmt.where(where_clause)

            # Cursor pagination
            stmt = stmt.order_by(MoleculeModel.id)
            if input.cursor_id is not None:
                stmt = stmt.where(MoleculeModel.id > input.cursor_id)

            # Fetch limit + 1 for next_cursor detection
            fetch_limit = input.limit + 1
            stmt = stmt.limit(fetch_limit)

            # Set similarity threshold if needed (session-level GUC)
            if similarity_threshold is not None:
                session = self._uow._session  # type: ignore[attr-defined]
                safe_threshold = float(similarity_threshold)
                await session.execute(
                    text(f"SET rdkit.tanimoto_threshold = {safe_threshold}")
                )

            # Execute via the UoW's session
            session = self._uow._session  # type: ignore[attr-defined]
            result = await session.execute(stmt)

            # Map to domain models
            models = list(result.scalars())
            molecules = [self._mol_repo._to_domain(m) for m in models]  # type: ignore[attr-defined]

            # Determine next_cursor
            next_cursor: str | None = None
            if len(molecules) > input.limit:
                molecules = molecules[: input.limit]
                next_cursor = str(molecules[-1].id)

            return Success(PageResult(items=molecules, next_cursor=next_cursor))
