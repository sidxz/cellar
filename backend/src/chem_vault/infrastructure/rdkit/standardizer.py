"""Structure standardization via chembl-structure-pipeline + RDKit."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from rdkit import Chem
from rdkit.Chem import Descriptors, GetMolFrags, MolToMolBlock, MolToSmiles, MolToCXSmiles
from rdkit.Chem.MolStandardize import rdMolStandardize
from returns.result import Failure, Result, Success

from chembl_structure_pipeline import checker, standardizer

from chem_vault.domain.shared.errors import DomainError
from chem_vault.infrastructure.rdkit.errors import InvalidSmilesError, StandardizationError


@dataclass(frozen=True)
class DetectedSalt:
    """Salt fragment stripped during standardization."""

    salt_smiles: str
    salt_fragment_mw: float
    stoichiometry: int  # count of identical salt fragments


@dataclass(frozen=True)
class StandardizedMolecule:
    """Output of the standardization pipeline."""

    mol: object  # rdkit.Chem.Mol (not typed to avoid rdkit type dep in signatures)
    canonical_smiles: str
    cxsmiles: str
    inchi: str
    inchi_key: str
    molfile: str
    detected_salt: DetectedSalt | None = None


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

    @staticmethod
    def _detect_salt(pre_parent_mol: object, parent_mol: object) -> DetectedSalt | None:
        """Compare fragments before/after parent extraction to identify stripped salts.

        Returns a DetectedSalt when exactly one unique non-parent fragment type
        was removed. Returns None for single-fragment inputs or ambiguous
        multi-salt cases.

        Uses heavy-atom count to match pre-parent fragments to the parent
        (get_parent_mol may neutralize charges, so SMILES comparison is unreliable).
        """
        pre_frags = GetMolFrags(pre_parent_mol, asMols=True)  # type: ignore[arg-type]
        if len(pre_frags) <= 1:
            return None

        parent_heavy = parent_mol.GetNumHeavyAtoms()  # type: ignore[union-attr]

        # Fragments whose heavy-atom count differs from the parent are salt candidates.
        # We allow at most one parent-matching fragment (the first match); any extra
        # same-size fragments are treated as salt candidates too.
        parent_matched = False
        salt_frags: list[object] = []
        for frag in pre_frags:
            if not parent_matched and frag.GetNumHeavyAtoms() == parent_heavy:
                parent_matched = True
            else:
                salt_frags.append(frag)

        if not salt_frags:
            return None

        salt_smiles_list = [MolToSmiles(f) for f in salt_frags]  # type: ignore[arg-type]
        unique_salts = set(salt_smiles_list)
        if len(unique_salts) != 1:
            return None  # multiple different salt types — ambiguous

        canonical_salt = unique_salts.pop()
        mw = Descriptors.ExactMolWt(salt_frags[0])
        return DetectedSalt(
            salt_smiles=canonical_salt,
            salt_fragment_mw=round(mw, 4),
            stoichiometry=len(salt_frags),
        )

    def standardize(self, raw_smiles: str) -> Result[StandardizedMolecule, DomainError]:
        # 1. Parse SMILES
        mol = Chem.MolFromSmiles(raw_smiles)
        if mol is None:
            return Failure(InvalidSmilesError(raw_smiles))

        try:
            # 2. chembl-structure-pipeline: standardize + get parent
            std_mol = standardizer.standardize_mol(mol)
            parent_mol, _ = standardizer.get_parent_mol(std_mol)

            # 2b. Detect salt fragments stripped during parent extraction
            detected_salt = self._detect_salt(std_mol, parent_mol)

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
                    detected_salt=detected_salt,
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
            logging.getLogger(__name__).warning(
                "QC check failed — returning zero penalty", exc_info=True,
            )
            return QCResult(total_penalty=0, issues=[])

        total_penalty = 0
        issues: list[str] = []
        for penalty, message in results:
            total_penalty += penalty
            issues.append(message)

        return QCResult(total_penalty=total_penalty, issues=issues)
