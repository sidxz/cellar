"""SearchMolecules query — structure-based molecule search (exact, substructure, similarity)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum

from returns.result import Failure, Result, Success

from chem_vault.application.chemical_registration.protocols import ProcessedStructureDTO, StructureProcessorProtocol
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.molecule import Molecule
from chem_vault.domain.chemical_registration.repository import MoleculeRepository
from chem_vault.domain.shared.errors import DomainError, ValidationError


class SearchType(StrEnum):
    EXACT = "exact"
    SUBSTRUCTURE = "substructure"
    SIMILARITY = "similarity"


@dataclass(frozen=True, kw_only=True)
class SearchMoleculesQuery(Query):
    workspace_id: uuid.UUID
    search_type: str
    query: str
    threshold: float = 0.7


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
        structure_processor: StructureProcessorProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._structure_processor = structure_processor

    async def __call__(
        self, input: SearchMoleculesQuery
    ) -> Result[SearchResults, DomainError]:
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

        if not (0.0 <= input.threshold <= 1.0):
            return Failure(ValidationError("Similarity threshold must be between 0.0 and 1.0"))

        async with self._uow:
            if search_type == SearchType.EXACT:
                return await self._exact_search(input)
            elif search_type == SearchType.SUBSTRUCTURE:
                results = await self._repo.search_substructure(
                    input.workspace_id, input.query.strip()
                )
                return Success(results)
            else:
                scored = await self._repo.search_similarity(
                    input.workspace_id,
                    input.query.strip(),
                    threshold=input.threshold,
                )
                return Success(
                    [SimilarityResult(mol, sim) for mol, sim in scored]
                )

    async def _exact_search(
        self, input: SearchMoleculesQuery
    ) -> Result[list[Molecule], DomainError]:
        process_result = self._structure_processor.process(input.query.strip())
        if isinstance(process_result, Failure):
            return Failure(
                ValidationError(
                    f"Cannot process query SMILES: {process_result.failure().message}"
                )
            )
        processed: ProcessedStructureDTO = process_result.unwrap()
        inchi_key = processed.structure.inchi_key
        mol = await self._repo.find_by_inchi_key(input.workspace_id, inchi_key)
        return Success([mol] if mol else [])
