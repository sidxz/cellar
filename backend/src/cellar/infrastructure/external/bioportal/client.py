"""BioPortal ontology search client — implements OntologySearchService protocol."""

from __future__ import annotations

import os
import uuid
from typing import Any
from urllib.parse import quote

import httpx

from cellar.domain.shared.errors import ServiceUnavailableError
from cellar.domain.shared.ontology import OntologyTerm
from cellar.domain.shared.secret_provider import SecretProvider

BIOPORTAL_BASE_URL = "https://data.bioontology.org"
BIOPORTAL_SEARCH_URL = f"{BIOPORTAL_BASE_URL}/search"
# ponytail: caps a descendants listing at 2,000 terms (20 pages); a dropdown longer
# than that is unusable anyway — point the slot at a narrower root concept instead.
_MAX_DESCENDANT_PAGES = 20


class BioPortalClient:
    """Search BioPortal for ontology terms.

    Resolves the API key via SecretProvider (workspace-scoped key named
    ``bioportal``), falling back to the ``BIOPORTAL_API_KEY`` env var.

    A missing key or an unreachable BioPortal raises ``ServiceUnavailableError``
    rather than returning ``[]`` — an empty list must mean "no matching terms",
    never "the lookup didn't happen".
    """

    def __init__(
        self, secret_provider: SecretProvider, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._secret_provider = secret_provider
        self._transport = transport

    async def _resolve_api_key(self, workspace_id: uuid.UUID | None) -> str:
        """Workspace secret > env var, else ServiceUnavailableError.

        Single resolution path so every method picks up the same fallback
        chain without duplicating the logic.
        """
        if workspace_id is not None:
            key = await self._secret_provider.get_secret(f"{workspace_id}:bioportal")
            if key:
                return key
        key = os.environ.get("BIOPORTAL_API_KEY")
        if not key:
            raise ServiceUnavailableError(
                "Ontology search needs a BioPortal API key — an admin can add one under "
                "Admin → API Keys (key name 'bioportal')."
            )
        return key

    async def _get(
        self, url: str, params: dict[str, Any], workspace_id: uuid.UUID | None, timeout: float
    ) -> Any:
        headers = {"Authorization": f"apikey token={await self._resolve_api_key(workspace_id)}"}
        async with httpx.AsyncClient(timeout=timeout, transport=self._transport) as client:
            try:
                resp = await client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ServiceUnavailableError(f"BioPortal lookup failed: {exc}") from exc

    async def search(
        self,
        query: str,
        ontology_sources: list[str],
        page_size: int = 10,
        subtree_root_id: str | None = None,
        *,
        workspace_id: uuid.UUID | None = None,
    ) -> list[OntologyTerm]:
        """Search BioPortal and map results to OntologyTerm VOs."""
        params: dict[str, Any] = {
            "q": query,
            "pagesize": page_size,
            "include": "prefLabel",
        }
        if subtree_root_id and ontology_sources:
            # BioPortal requires "ontology" (singular) with subtree_root_id
            params["ontology"] = ontology_sources[0]
            params["subtree_root_id"] = subtree_root_id
        elif ontology_sources:
            params["ontologies"] = ",".join(ontology_sources)

        data = await self._get(BIOPORTAL_SEARCH_URL, params, workspace_id, timeout=10.0)
        results: list[OntologyTerm] = []
        for item in data.get("collection", []):
            term_id = item.get("@id", "")
            label = item.get("prefLabel", "")
            # Extract ontology source from the links or ID
            ontology_source = ""
            links = item.get("links", {})
            ontology_link = links.get("ontology", "") if isinstance(links, dict) else ""
            if ontology_link:
                ontology_source = ontology_link.rstrip("/").rsplit("/", 1)[-1]
            if not ontology_source:
                # Fallback: parse from term_id
                for src in ontology_sources:
                    if src.upper() in term_id.upper():
                        ontology_source = src
                        break
                if not ontology_source:
                    ontology_source = "unknown"

            if term_id and label and ontology_source:
                results.append(
                    OntologyTerm(
                        term_id=term_id,
                        label=label,
                        ontology_source=ontology_source,
                        uri=term_id,
                    )
                )

        return results

    async def list_descendants(
        self,
        ontology: str,
        root_concept_id: str,
        *,
        workspace_id: uuid.UUID | None = None,
    ) -> list[OntologyTerm]:
        """List all descendants of a concept in an ontology, across every page."""
        encoded_id = quote(root_concept_id, safe="")
        url = f"{BIOPORTAL_BASE_URL}/ontologies/{ontology}/classes/{encoded_id}/descendants"

        results: list[OntologyTerm] = []
        page, page_count = 1, 1
        while page <= min(page_count, _MAX_DESCENDANT_PAGES):
            data = await self._get(
                url, {"pagesize": 100, "page": page}, workspace_id, timeout=15.0
            )
            # A paged result is {"collection": [...], "pageCount": n}; a concept with no
            # descendants comes back as a bare [] instead.
            if isinstance(data, list):
                items = data
            else:
                items = data.get("collection", [])
                page_count = data.get("pageCount") or 1
            for item in items:
                term_id = item.get("@id", "")
                label = item.get("prefLabel", "")
                if term_id and label:
                    results.append(
                        OntologyTerm(
                            term_id=term_id,
                            label=label,
                            ontology_source=ontology,
                            uri=term_id,
                        )
                    )
            page += 1
        results.sort(key=lambda t: t.label)
        return results
