"""Protocol interface for ontology search (domain layer, no infra dependency)."""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from cellar.domain.shared.ontology import OntologyTerm


@runtime_checkable
class OntologySearchService(Protocol):
    """Search external ontology services for matching terms.

    Infrastructure implementations may call BioPortal, OLS, or a local cache.
    The domain layer only depends on this protocol.
    """

    async def search(
        self,
        query: str,
        ontology_sources: list[str],
        page_size: int = 10,
        subtree_root_id: str | None = None,
        *,
        workspace_id: uuid.UUID | None = None,
    ) -> list[OntologyTerm]: ...
