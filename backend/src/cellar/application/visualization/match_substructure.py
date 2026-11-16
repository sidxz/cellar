"""MatchSubstructure — which of a dataset's molecules contain a drawn substructure."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace
from cellar.application.shared.query import Query
from cellar.application.visualization.get_dataset import MAX_DATASET_ROWS
from cellar.domain.shared.errors import DomainError, ValidationError

QueryKind = Literal["smiles", "smarts"]

# A dataset never has more compounds than rows.
MAX_MATCH_IDS = MAX_DATASET_ROWS


@dataclass(frozen=True)
class SubstructureMatchResult:
    matched_ids: list[uuid.UUID]
    searched: int  # given ids found in the workspace
    without_structure: int  # of those, molecules with no structure (never matched)


class SubstructureMatcher(Protocol):
    async def match(
        self,
        workspace_id: uuid.UUID,
        molecule_ids: Sequence[uuid.UUID],
        query: str,
        query_kind: QueryKind | None,
    ) -> SubstructureMatchResult:
        """Raises ``ValueError`` (a chemist-readable message) for an unreadable query."""
        ...


@dataclass(frozen=True, kw_only=True)
class MatchSubstructureQuery(Query):
    workspace_id: uuid.UUID
    molecule_ids: tuple[uuid.UUID, ...]
    query: str
    query_kind: QueryKind | None = None


class MatchSubstructure:
    def __init__(self, matcher: SubstructureMatcher) -> None:
        self._matcher = matcher

    async def __call__(
        self, input: MatchSubstructureQuery, auth: AuthContext | None = None
    ) -> Result[SubstructureMatchResult, DomainError]:
        require_same_workspace(auth, input.workspace_id)
        query = input.query.strip()
        if not query:
            return Failure(ValidationError("Draw or type a structure to match."))
        if len(input.molecule_ids) > MAX_MATCH_IDS:
            return Failure(
                ValidationError(
                    f"This dataset has {len(input.molecule_ids):,} compounds; substructure "
                    f"matching is capped at {MAX_MATCH_IDS:,}. Choose fewer runs."
                )
            )
        if not input.molecule_ids:
            return Success(
                SubstructureMatchResult(matched_ids=[], searched=0, without_structure=0)
            )
        try:
            found = await self._matcher.match(
                input.workspace_id, input.molecule_ids, query, input.query_kind
            )
        except ValueError as e:
            return Failure(ValidationError(str(e)))
        return Success(found)
