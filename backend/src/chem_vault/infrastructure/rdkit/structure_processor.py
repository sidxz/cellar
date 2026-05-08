"""Orchestrates the full structure processing pipeline."""

from __future__ import annotations

from returns.result import Failure, Result, Success

from chem_vault.application.chemical_registration.protocols import (
    DetectedSaltDTO,
    ProcessedStructureDTO,
    QCResultDTO,
)
from chem_vault.domain.shared.errors import DomainError
from chem_vault.domain.shared.value_objects import ChemicalStructure
from chem_vault.infrastructure.rdkit.descriptor_calculator import DescriptorCalculator
from chem_vault.infrastructure.rdkit.errors import QCRejectedError
from chem_vault.infrastructure.rdkit.fingerprint_generator import FingerprintGenerator
from chem_vault.infrastructure.rdkit.standardizer import StructureStandardizer


class StructureProcessor:
    """Single entry point for processing a raw SMILES string.

    Pipeline: standardize -> QC check -> compute descriptors -> generate fingerprints.
    Returns application-layer DTOs to satisfy StructureProcessorProtocol.
    """

    def __init__(
        self,
        standardizer: StructureStandardizer | None = None,
        descriptor_calculator: DescriptorCalculator | None = None,
        fingerprint_generator: FingerprintGenerator | None = None,
    ) -> None:
        self._standardizer = standardizer or StructureStandardizer()
        self._descriptor_calc = descriptor_calculator or DescriptorCalculator()
        self._fp_gen = fingerprint_generator or FingerprintGenerator()

    def process(
        self,
        raw_smiles: str,
        *,
        qc_reject_threshold: int | None = None,
    ) -> Result[ProcessedStructureDTO, DomainError]:
        """Process a raw SMILES through the full pipeline.

        Args:
            raw_smiles: Input SMILES string.
            qc_reject_threshold: If set, reject molecules with QC penalty >= this value.

        Returns:
            Result with ProcessedStructureDTO on success.
        """
        # 1. Standardize
        std_result = self._standardizer.standardize(raw_smiles)
        if isinstance(std_result, Failure):
            return std_result

        std_mol = std_result.unwrap()

        # 2. QC check
        raw_qc = self._standardizer.check_molecule(std_mol.mol)
        qc_result = QCResultDTO(
            total_penalty=raw_qc.total_penalty, issues=raw_qc.issues
        )

        if qc_reject_threshold is not None and qc_result.total_penalty >= qc_reject_threshold:
            return Failure(
                QCRejectedError(
                    smiles=raw_smiles,
                    score=qc_result.total_penalty,
                    issues=qc_result.issues,
                    threshold=qc_reject_threshold,
                )
            )

        # 3. Compute descriptors
        descriptors = self._descriptor_calc.calculate(std_mol.mol)

        # 4. Generate fingerprints
        fingerprints = self._fp_gen.compute(std_mol.mol)

        # 5. Build domain VOs
        structure = ChemicalStructure(
            smiles=std_mol.canonical_smiles,
            cxsmiles=std_mol.cxsmiles,
            inchi=std_mol.inchi,
            inchi_key=std_mol.inchi_key,
            molfile=std_mol.molfile,
        )

        # 6. Map detected salt (if any)
        detected_salt_dto: DetectedSaltDTO | None = None
        if std_mol.detected_salt is not None:
            detected_salt_dto = DetectedSaltDTO(
                salt_smiles=std_mol.detected_salt.salt_smiles,
                salt_fragment_mw=std_mol.detected_salt.salt_fragment_mw,
                stoichiometry=std_mol.detected_salt.stoichiometry,
            )

        return Success(
            ProcessedStructureDTO(
                structure=structure,
                descriptors=descriptors,
                fingerprints=fingerprints,
                qc_result=qc_result,
                detected_salt=detected_salt_dto,
            )
        )

    def smiles_to_mol_block(self, smiles: str) -> str | None:
        """Convert a SMILES string to a V2000 MOL block, or None if invalid."""
        from rdkit import Chem
        from rdkit.Chem import MolToMolBlock

        rdmol = Chem.MolFromSmiles(smiles)
        if rdmol is None:
            return None
        return MolToMolBlock(rdmol)
