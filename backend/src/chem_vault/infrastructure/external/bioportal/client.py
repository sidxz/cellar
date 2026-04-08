"""BioPortal ontology search client — implements OntologySearchService protocol."""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx

from chem_vault.domain.shared.ontology import OntologyTerm
from chem_vault.domain.shared.secret_provider import SecretProvider

BIOPORTAL_SEARCH_URL = "https://data.bioontology.org/search"


class BioPortalClient:
    """Search BioPortal for ontology terms.

    Resolves the API key via SecretProvider (workspace-scoped key named
    ``bioportal``), falling back to the ``BIOPORTAL_API_KEY`` env var.
    """

    def __init__(self, secret_provider: SecretProvider) -> None:
        self._secret_provider = secret_provider

    async def _get_api_key(self, workspace_id: uuid.UUID) -> str | None:
        """Try workspace-scoped secret first, then env fallback."""
        key = await self._secret_provider.get_secret(f"{workspace_id}:bioportal")
        if key:
            return key
        return os.environ.get("BIOPORTAL_API_KEY")

    async def search(
        self,
        query: str,
        ontology_sources: list[str],
        page_size: int = 10,
        *,
        workspace_id: uuid.UUID | None = None,
    ) -> list[OntologyTerm]:
        """Search BioPortal and map results to OntologyTerm VOs."""
        api_key = None
        if workspace_id is not None:
            api_key = await self._get_api_key(workspace_id)
        if not api_key:
            api_key = os.environ.get("BIOPORTAL_API_KEY")
        if not api_key:
            return []

        params: dict[str, Any] = {
            "q": query,
            "pagesize": page_size,
            "include": "prefLabel",
        }
        if ontology_sources:
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
