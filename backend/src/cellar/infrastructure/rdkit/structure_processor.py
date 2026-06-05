"""Orchestrates the full structure processing pipeline."""

from __future__ import annotations

from rdkit import Chem
from returns.result import Failure, Result, Success

from cellar.application.chemical_registration.protocols import (
    DetectedSaltDTO,
    ProcessedStructureDTO,
    QCResultDTO,
)
from cellar.domain.chemical_registration.enums import Stereochemistry
from cellar.domain.shared.errors import DomainError
from cellar.domain.shared.value_objects import ChemicalStructure
from cellar.infrastructure.rdkit.descriptor_calculator import DescriptorCalculator
from cellar.infrastructure.rdkit.errors import QCRejectedError
from cellar.infrastructure.rdkit.fingerprint_generator import FingerprintGenerator
from cellar.infrastructure.rdkit.scaffold_calculator import MurckoScaffoldCalculator
from cellar.infrastructure.rdkit.standardizer import StructureStandardizer


def _classify_stereochemistry(mol: object) -> Stereochemistry:
    """Classify the stereochemistry of a canonicalized mol.

    Counts both tetrahedral atom stereocenters and stereogenic double bonds.
    Returns:
        ACHIRAL          — no stereo elements at all
        SINGLE_STEREO    — exactly one fully-defined stereo element
        MULTI_STEREO     — multiple fully-defined stereo elements
        UNDEFINED        — at least one stereo element exists but is unassigned
    """
    atom_centers = Chem.FindMolChiralCenters(
        mol,  # type: ignore[arg-type]
        includeUnassigned=True,
        useLegacyImplementation=False,
    )
    atom_defined = sum(1 for _, tag in atom_centers if tag not in ("?", "Unassigned"))
    atom_total = len(atom_centers)

    bond_total = 0
    bond_defined = 0
    for bond in mol.GetBonds():  # type: ignore[union-attr]
        if bond.GetBondType() != Chem.BondType.DOUBLE:
            continue
        stereo = bond.GetStereo()
        if stereo == Chem.BondStereo.STEREONONE:
            continue
        bond_total += 1
        if stereo in (
            Chem.BondStereo.STEREOE,
            Chem.BondStereo.STEREOZ,
            Chem.BondStereo.STEREOCIS,
            Chem.BondStereo.STEREOTRANS,
        ):
            bond_defined += 1

    total = atom_total + bond_total
    defined = atom_defined + bond_defined

    if total == 0:
        return Stereochemistry.ACHIRAL
    if defined < total:
        return Stereochemistry.UNDEFINED
    return Stereochemistry.SINGLE_STEREO if defined == 1 else Stereochemistry.MULTI_STEREO


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
        *,
        scaffold_calculator: MurckoScaffoldCalculator,
    ) -> None:
        self._standardizer = standardizer or StructureStandardizer()
        self._descriptor_calc = descriptor_calculator or DescriptorCalculator()
        self._fp_gen = fingerprint_generator or FingerprintGenerator()
        self._scaffold_calculator = scaffold_calculator

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
        qc_result = QCResultDTO(total_penalty=raw_qc.total_penalty, issues=raw_qc.issues)

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

        # 7. Classify stereochemistry (atom centers + stereogenic double bonds)
        stereochemistry = _classify_stereochemistry(std_mol.mol)

        # 8. Compute Bemis-Murcko scaffold (post-standardization mol)
        scaffold = self._scaffold_calculator.compute(std_mol.mol)

        return Success(
            ProcessedStructureDTO(
                structure=structure,
                descriptors=descriptors,
                fingerprints=fingerprints,
                qc_result=qc_result,
                stereochemistry=stereochemistry,
                detected_salt=detected_salt_dto,
                bemis_murcko_smiles=scaffold,
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
