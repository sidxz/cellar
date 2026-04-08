"""SearchOntology query — proxy search to OntologySearchService."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Result, Success

from chem_vault.application.shared.query import Query
from chem_vault.domain.shared.errors import DomainError
from chem_vault.domain.shared.ontology import OntologyTerm
from chem_vault.domain.shared.ontology_search_service import OntologySearchService


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
        self, input: SearchOntologyQuery
    ) -> Result[list[OntologyTerm], DomainError]:
        results = await self._search_service.search(
            query=input.query,
            ontology_sources=input.ontology_sources,
            page_size=input.page_size,
            subtree_root_id=input.subtree_root_id,
            workspace_id=input.workspace_id,  # type: ignore[call-arg]
        )
        return Success(results)
