"""SearchMolecules query — structure-based molecule search (exact, substructure, similarity)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.chemical_registration.molecule_reader import MoleculeReader
from cellar.application.chemical_registration.protocols import (
    ProcessedStructureDTO,
    StructureProcessorProtocol,
)
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.sar_analysis.search_modes import SearchMode
from cellar.domain.sar_analysis.similarity_metric import SimilarityMetric
from cellar.domain.shared.errors import DomainError, ValidationError


class SearchType(StrEnum):
    EXACT = "exact"
    SUBSTRUCTURE = "substructure"
    SIMILARITY = "similarity"


@dataclass(frozen=True, kw_only=True)
class SearchMoleculesQuery(Query):
    workspace_id: uuid.UUID
    search_type: str
    query: str
    threshold: float | None = None
    mode: SearchMode = SearchMode.SIMILAR
    algorithm: str | None = None
    metric: SimilarityMetric | None = None
    cursor_id: uuid.UUID | None = None
    limit: int | None = None
    # SUBSTRUCTURE only: how the cartridge interprets `query`. None falls
    # back to the legacy aromatize-helper SMARTS path.
    query_kind: str | None = None


@dataclass(frozen=True)
class SimilarityResult:
    """A molecule with its Tanimoto similarity score."""

    molecule: Molecule
    similarity: float


# Union return type: plain molecules for exact/substructure, scored for similarity
SearchResults = list[Molecule] | list[SimilarityResult]


class SearchMolecules:
    """Query use case: search molecules by structure.

    - exact: converts SMILES to InChIKey, finds by InChIKey
    - substructure: RDKit cartridge mol @> match
    - similarity: RDKit cartridge Tanimoto similarity
    """

    def __init__(
        self,
        uow: UnitOfWork,
        repo: MoleculeRepository,
        reader: MoleculeReader,
        structure_processor: StructureProcessorProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._reader = reader
        self._structure_processor = structure_processor

    async def __call__(
        self, input: SearchMoleculesQuery, auth: AuthContext | None = None
    ) -> Result[SearchResults, DomainError]:
        require_workspace_role(auth, "viewer")
        try:
            search_type = SearchType(input.search_type)
        except ValueError:
            return Failure(
                ValidationError(
                    f"Invalid search_type '{input.search_type}'. "
                    f"Must be one of: {', '.join(SearchType)}"
                )
            )

        if not input.query or not input.query.strip():
            return Failure(ValidationError("Search query must not be empty"))

        if input.threshold is not None and not (0.0 <= input.threshold <= 1.0):
            return Failure(ValidationError("Similarity threshold must be between 0.0 and 1.0"))

        async with self._uow:
            if search_type == SearchType.EXACT:
                return await self._exact_search(input)
            elif search_type == SearchType.SUBSTRUCTURE:
                results = await self._reader.search_substructure(
                    input.workspace_id,
                    input.query.strip(),
                    kind=input.query_kind,
                )
                return Success(results)
            else:
                scored = await self._reader.search_similarity(
                    input.workspace_id,
                    input.query.strip(),
                    mode=input.mode,
                    threshold=input.threshold,
                    algorithm=input.algorithm,
                    metric=input.metric,
                    cursor_id=input.cursor_id,
                    limit=input.limit,
                )
                return Success([SimilarityResult(mol, sim) for mol, sim in scored])

    async def _exact_search(
        self, input: SearchMoleculesQuery
    ) -> Result[list[Molecule], DomainError]:
        process_result = self._structure_processor.process(input.query.strip())
        if isinstance(process_result, Failure):
            return Failure(
                ValidationError(f"Cannot process query SMILES: {process_result.failure().message}")
            )
        processed: ProcessedStructureDTO = process_result.unwrap()
        inchi_key = processed.structure.inchi_key
        mol = await self._repo.find_by_inchi_key(input.workspace_id, inchi_key)
        return Success([mol] if mol else [])
