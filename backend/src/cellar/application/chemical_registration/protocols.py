"""Application-layer protocols for chemical registration dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from returns.result import Result

from cellar.domain.chemical_registration.enums import Stereochemistry
from cellar.domain.shared.errors import DomainError
from cellar.domain.shared.value_objects import ChemicalStructure, ComputedDescriptors


@dataclass(frozen=True)
class Fingerprints:
    """Computed fingerprints for a single molecule — application-layer DTO.

    Only Morgan is computed in Python (stereo-aware). FCFP is computed by
    a Postgres trigger from the canonical SMILES.
    """

    morgan: bytes


@dataclass(frozen=True)
class QCResultDTO:
    """QC check result — application-layer DTO."""

    total_penalty: int
    issues: list[str]

    @property
    def is_clean(self) -> bool:
        return self.total_penalty == 0


@dataclass(frozen=True)
class DetectedSaltDTO:
    """Salt fragment detected during standardization — application-layer DTO."""

    salt_smiles: str
    salt_fragment_mw: float
    stoichiometry: int


@dataclass(frozen=True)
class ProcessedStructureDTO:
    """Processed structure — application-layer DTO."""

    structure: ChemicalStructure
    descriptors: ComputedDescriptors
    fingerprints: Fingerprints
    qc_result: QCResultDTO
    stereochemistry: Stereochemistry
    detected_salt: DetectedSaltDTO | None = None
    bemis_murcko_smiles: str | None = None


class StructureProcessorProtocol(Protocol):
    """Protocol for structure processing — implemented by infrastructure layer."""

    def process(
        self,
        raw_smiles: str,
        *,
        qc_reject_threshold: int | None = None,
    ) -> Result[ProcessedStructureDTO, DomainError]: ...

    def smiles_to_mol_block(self, smiles: str) -> str | None:
        """Convert a SMILES string to a V2000 MOL block, or None if invalid."""
        ...
