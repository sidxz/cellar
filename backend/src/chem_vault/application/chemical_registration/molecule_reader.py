"""Read-model protocol for compound search queries.

Substructure / similarity / structured-query searches are pure read paths
— they live in a CQRS Reader rather than the write-side ``MoleculeRepository``.
The concrete implementation is in
``infrastructure.persistence.sqlalchemy.chemical_registration.molecule_reader``.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol, runtime_checkable

from chem_vault.domain.chemical_registration.molecule import Molecule


@runtime_checkable
class MoleculeReader(Protocol):
    """Application-layer protocol for molecule search read-model queries."""

    async def search_substructure(
        self, workspace_id: uuid.UUID, smarts: str
    ) -> list[Molecule]: ...

    async def search_similarity(
        self, workspace_id: uuid.UUID, smiles: str, threshold: float = 0.7
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
    ) -> list[Molecule]: ...

    async def count_by_query(
        self,
        workspace_id: uuid.UUID,
        query: dict[str, Any],
        *,
        project_ids: list[uuid.UUID] | None = None,
    ) -> int: ...
