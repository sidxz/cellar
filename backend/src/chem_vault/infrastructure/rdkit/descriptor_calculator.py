"""Molecular descriptor calculation via RDKit."""

from __future__ import annotations

from rdkit.Chem import Descriptors, Lipinski, rdMolDescriptors

from chem_vault.domain.shared.value_objects import ComputedDescriptors


class DescriptorCalculator:
    """Computes deterministic molecular descriptors from an RDKit Mol object."""

    def calculate(self, mol: object) -> ComputedDescriptors:
        """Calculate all descriptors and return the domain value object."""
        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        hbd = Descriptors.NumHDonors(mol)
        hba = Descriptors.NumHAcceptors(mol)

        ro5_violations = sum([
            mw > 500,
            logp > 5,
            hbd > 5,
            hba > 10,
        ])

        return ComputedDescriptors(
            molecular_formula=rdMolDescriptors.CalcMolFormula(mol),
            molecular_weight=round(mw, 4),
            exact_mass=round(Descriptors.ExactMolWt(mol), 6),
            logp=round(logp, 4),
            tpsa=round(Descriptors.TPSA(mol), 4),
            hbd=hbd,
            hba=hba,
            rotatable_bonds=Descriptors.NumRotatableBonds(mol),
            aromatic_rings=rdMolDescriptors.CalcNumAromaticRings(mol),
            ring_count=rdMolDescriptors.CalcNumRings(mol),
            heavy_atom_count=Lipinski.HeavyAtomCount(mol),
            ro5_violations=ro5_violations,
        )
