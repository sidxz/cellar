"""BioPortal ontology search client — implements OntologySearchService protocol."""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx

from chem_vault.domain.shared.ontology import OntologyTerm
from chem_vault.domain.shared.secret_provider import SecretProvider

BIOPORTAL_BASE_URL = "https://data.bioontology.org"
BIOPORTAL_SEARCH_URL = f"{BIOPORTAL_BASE_URL}/search"


class BioPortalClient:
    """Search BioPortal for ontology terms.

    Resolves the API key via SecretProvider (workspace-scoped key named
    ``bioportal``), falling back to the ``BIOPORTAL_API_KEY`` env var.
    """

    def __init__(self, secret_provider: SecretProvider) -> None:
        self._secret_provider = secret_provider

    async def _resolve_api_key(self, workspace_id: uuid.UUID | None) -> str | None:
        """Workspace secret > env var > None.

        Single resolution path so every method picks up the same fallback
        chain without duplicating the logic.
        """
        if workspace_id is not None:
            key = await self._secret_provider.get_secret(f"{workspace_id}:bioportal")
            if key:
                return key
        return os.environ.get("BIOPORTAL_API_KEY")

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
        api_key = await self._resolve_api_key(workspace_id)
        if not api_key:
            return []

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

        headers = {"Authorization": f"apikey token={api_key}"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(BIOPORTAL_SEARCH_URL, params=params, headers=headers)
                resp.raise_for_status()
            except httpx.HTTPError:
                return []

        data = resp.json()
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
        """List all descendants of a concept in an ontology."""
        api_key = await self._resolve_api_key(workspace_id)
        if not api_key:
            return []

        from urllib.parse import quote
        encoded_id = quote(root_concept_id, safe="")
        url = f"{BIOPORTAL_BASE_URL}/ontologies/{ontology}/classes/{encoded_id}/descendants"
        headers = {"Authorization": f"apikey token={api_key}"}

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(url, params={"pagesize": 100}, headers=headers)
                resp.raise_for_status()
            except httpx.HTTPError:
                return []

        data = resp.json()
        results: list[OntologyTerm] = []
        for item in data.get("collection", []):
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
        results.sort(key=lambda t: t.label)
        return results
