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
        sort_by: str | None = None,
        sort_dir: str | None = None,
        include_similarity_score: bool = False,
    ) -> list[Molecule] | list[tuple[Molecule, float | None]]: ...

    async def count_by_query(
        self,
        workspace_id: uuid.UUID,
        query: dict[str, Any],
        *,
        project_ids: list[uuid.UUID] | None = None,
    ) -> int: ...
