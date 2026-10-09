"""Ontology lookups — proxy search and subtree listing to OntologySearchService."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import structlog
from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.domain.shared.common_organisms import match_common_organism
from cellar.domain.shared.errors import DomainError
from cellar.domain.shared.ontology import OntologyTerm
from cellar.domain.shared.ontology_search_service import OntologySearchService

_log = structlog.get_logger(__name__)


@dataclass(frozen=True, kw_only=True)
class SearchOntologyQuery(Query):
    workspace_id: uuid.UUID
    query: str
    ontology_sources: list[str] = field(default_factory=list)
    subtree_root_id: str | None = None
    page_size: int = 10
    # Only terms whose label or synonym equals the query (a common organism name wins outright).
    exact_only: bool = False


class SearchOntology:
    def __init__(self, search_service: OntologySearchService) -> None:
        self._search_service = search_service

    async def __call__(
        self, input: SearchOntologyQuery, auth: AuthContext | None = None
    ) -> Result[list[OntologyTerm], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        local = self._common_organism_hits(input)
        if input.exact_only and local:
            return Success(local)
        try:
            results = await self._search_service.search(
                query=input.query,
                ontology_sources=input.ontology_sources,
                page_size=input.page_size,
                subtree_root_id=input.subtree_root_id,
                workspace_id=input.workspace_id,
                exact_only=input.exact_only,
            )
        except DomainError as exc:
            if not local:
                return Failure(exc)
            # The local hits are the answer; the search failure is reported, not fatal.
            _log.warning("ontology_search.remote_failed_local_hits_returned", error=str(exc))
            return Success(local)
        local_ids = {t.term_id for t in local}
        return Success(local + [t for t in results if t.term_id not in local_ids])

    @staticmethod
    def _common_organism_hits(input: SearchOntologyQuery) -> list[OntologyTerm]:
        """Alias match ("mouse", "Mtb") for searches that cover NCBITaxon, ahead of BioPortal."""
        sources = {s.upper() for s in input.ontology_sources}
        if input.subtree_root_id or (sources and "NCBITAXON" not in sources):
            return []
        term = match_common_organism(input.query)
        return [term] if term else []


@dataclass(frozen=True, kw_only=True)
class ListOntologyDescendantsQuery(Query):
    workspace_id: uuid.UUID
    ontology: str
    root_concept_id: str


class ListOntologyDescendants:
    """Every term under a root concept — backs dropdown-mode ontology slots."""

    def __init__(self, search_service: OntologySearchService) -> None:
        self._search_service = search_service

    async def __call__(
        self, input: ListOntologyDescendantsQuery, auth: AuthContext | None = None
    ) -> Result[list[OntologyTerm], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        try:
            terms = await self._search_service.list_descendants(
                ontology=input.ontology,
                root_concept_id=input.root_concept_id,
                workspace_id=input.workspace_id,
            )
        except DomainError as exc:
            return Failure(exc)
        return Success(terms)
