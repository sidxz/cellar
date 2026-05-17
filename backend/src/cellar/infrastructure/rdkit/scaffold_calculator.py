"""Bemis-Murcko scaffold computation. Stateless; wraps RDKit."""

from __future__ import annotations

import structlog
from rdkit import Chem
from rdkit.Chem.Scaffolds import MurckoScaffold

logger = structlog.get_logger(__name__)


class MurckoScaffoldCalculator:
    """Compute the Bemis-Murcko scaffold SMILES for an RDKit mol.

    Returns:
        canonical SMILES of the scaffold for ringed molecules,
        "" for acyclic molecules (RDKit convention),
        None on parse / compute failure (logs at warning level).
    """

    def compute(self, mol: Chem.Mol | None) -> str | None:
        if mol is None:
            logger.warning("scaffold_compute_called_with_none")
            return None
        try:
            return MurckoScaffold.MurckoScaffoldSmiles(mol=mol)
        except Exception as exc:  # pragma: no cover — defensive
            try:
                source = Chem.MolToSmiles(mol)
            except Exception:
                source = "<unrenderable>"
            logger.warning("scaffold_compute_failed", smiles=source, exc=str(exc))
            return None
