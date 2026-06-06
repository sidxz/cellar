"""SearchOntology query — proxy search to OntologySearchService."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.domain.shared.errors import DomainError
from cellar.domain.shared.ontology import OntologyTerm
from cellar.domain.shared.ontology_search_service import OntologySearchService


@dataclass(frozen=True, kw_only=True)
class SearchOntologyQuery(Query):
    workspace_id: uuid.UUID
    query: str
    ontology_sources: list[str] = field(default_factory=list)
    subtree_root_id: str | None = None
    page_size: int = 10


class SearchOntology:
    def __init__(self, search_service: OntologySearchService) -> None:
        self._search_service = search_service

    async def __call__(
        self, input: SearchOntologyQuery, auth: AuthContext | None = None
    ) -> Result[list[OntologyTerm], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        results = await self._search_service.search(
            query=input.query,
            ontology_sources=input.ontology_sources,
            page_size=input.page_size,
            subtree_root_id=input.subtree_root_id,
            workspace_id=input.workspace_id,
        )
        return Success(results)
