"""Read-model protocol for compound search queries.

Substructure / similarity / structured-query searches are pure read paths
— they live in a CQRS Reader rather than the write-side ``MoleculeRepository``.
The concrete implementation is in
``infrastructure.persistence.sqlalchemy.chemical_registration.molecule_reader``.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol, runtime_checkable

from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.sar_analysis.search_modes import SearchMode
from cellar.domain.sar_analysis.similarity_metric import SimilarityMetric


@runtime_checkable
class MoleculeReader(Protocol):
    """Application-layer protocol for molecule search read-model queries."""

    async def search_substructure(
        self,
        workspace_id: uuid.UUID,
        query: str,
        *,
        kind: str | None = None,
    ) -> list[Molecule]: ...

    async def search_similarity(
        self,
        workspace_id: uuid.UUID,
        smiles: str,
        *,
        mode: SearchMode = SearchMode.SIMILAR,
        threshold: float | None = None,
        algorithm: str | None = None,
        metric: SimilarityMetric | None = None,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
    ) -> list[tuple[Molecule, float]]: ...

    async def search_by_query(
        self,
        workspace_id: uuid.UUID,
        query: dict[str, Any],
        *,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
        project_ids: list[uuid.UUID] | None = None,
    ) -> list[Molecule]:
        """One page of matches in id order, after ``cursor_id``."""
        ...

    async def ranked_ids_by_query(
        self,
        workspace_id: uuid.UUID,
        query: dict[str, Any],
        *,
        project_ids: list[uuid.UUID] | None = None,
        sort_by: str | None = None,
        sort_dir: str | None = None,
    ) -> list[tuple[uuid.UUID, float | None]]:
        """Every matching id in result order (molecule column or similarity
        sort; default similarity-desc when the query has a similarity
        criterion, else id), with its similarity score. Raises ``ValueError``
        on an unknown sort field."""
        ...

    async def find_by_ids_ordered(
        self, workspace_id: uuid.UUID, ids: list[uuid.UUID]
    ) -> list[Molecule]: ...

    async def count_by_query(
        self,
        workspace_id: uuid.UUID,
        query: dict[str, Any],
        *,
        project_ids: list[uuid.UUID] | None = None,
    ) -> int: ...
