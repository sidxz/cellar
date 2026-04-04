"""Structure standardization via chembl-structure-pipeline + RDKit."""

from __future__ import annotations

from dataclasses import dataclass

from rdkit import Chem
from rdkit.Chem import MolToMolBlock, MolToSmiles, MolToCXSmiles
from rdkit.Chem.MolStandardize import rdMolStandardize
from returns.result import Failure, Result, Success

from chembl_structure_pipeline import checker, standardizer

from chem_vault.domain.shared.errors import DomainError
from chem_vault.infrastructure.rdkit.errors import InvalidSmilesError, StandardizationError


@dataclass(frozen=True)
class StandardizedMolecule:
    """Output of the standardization pipeline."""

    mol: object  # rdkit.Chem.Mol (not typed to avoid rdkit type dep in signatures)
    canonical_smiles: str
    cxsmiles: str
    inchi: str
    inchi_key: str
    molfile: str


@dataclass(frozen=True)
class QCResult:
    """Quality control check result."""

    total_penalty: int
    issues: list[str]

    @property
    def is_clean(self) -> bool:
        return self.total_penalty == 0


_tautomer_enumerator = rdMolStandardize.TautomerEnumerator()


class StructureStandardizer:
    """Standardizes chemical structures using chembl-structure-pipeline + RDKit.

    Pipeline: parse SMILES -> standardize -> get parent -> tautomer canonicalize
    -> generate canonical SMILES, InChI, InChIKey, molfile.
    """

    def standardize(self, raw_smiles: str) -> Result[StandardizedMolecule, DomainError]:
        # 1. Parse SMILES
        mol = Chem.MolFromSmiles(raw_smiles)
        if mol is None:
            return Failure(InvalidSmilesError(raw_smiles))

        try:
            # 2. chembl-structure-pipeline: standardize + get parent
            std_mol = standardizer.standardize_mol(mol)
            parent_mol, _ = standardizer.get_parent_mol(std_mol)

            # 3. RDKit tautomer canonicalization
            canon_mol = _tautomer_enumerator.Canonicalize(parent_mol)

            # 4. Generate representations
            canonical_smiles = MolToSmiles(canon_mol)
            cxsmiles = MolToCXSmiles(canon_mol)
            molfile = MolToMolBlock(canon_mol)

            inchi = Chem.MolToInchi(canon_mol)
            if inchi is None:
                return Failure(
                    StandardizationError(raw_smiles, "Failed to generate InChI")
                )

            inchi_key = Chem.InchiToInchiKey(inchi)
            if inchi_key is None:
                return Failure(
                    StandardizationError(raw_smiles, "Failed to generate InChIKey")
                )

            return Success(
                StandardizedMolecule(
                    mol=canon_mol,
                    canonical_smiles=canonical_smiles,
                    cxsmiles=cxsmiles,
                    inchi=inchi,
                    inchi_key=inchi_key,
                    molfile=molfile,
                )
            )
        except Exception as exc:
            return Failure(StandardizationError(raw_smiles, str(exc)))

    def check_molecule(self, mol: object) -> QCResult:
        """Run QC checks via chembl-structure-pipeline checker.

        Returns penalty score and list of issue descriptions.
        """
        try:
            molblock = MolToMolBlock(mol)  # type: ignore[arg-type]
            results = checker.check_molblock(molblock)
        except Exception:
            return QCResult(total_penalty=0, issues=[])

        total_penalty = 0
        issues: list[str] = []
        for penalty, message in results:
            total_penalty += penalty
            issues.append(message)

        return QCResult(total_penalty=total_penalty, issues=issues)
