"""R-group decomposition. Stateless; wraps RDKit's rdRGroupDecomposition."""

from __future__ import annotations

from uuid import UUID

import structlog
from rdkit import Chem
from rdkit.Chem import rdRGroupDecomposition

from cellar.domain.sar_analysis.rgroup_types import (
    RGroupAssignment,
    RGroupDecompositionResult,
)

logger = structlog.get_logger(__name__)


class RGroupDecomposer:
    """Decompose a congeneric series against a core into R-group columns.

    Wraps ``rdkit.Chem.rdRGroupDecomposition.RGroupDecompose``. Stateless —
    safe to register as a DI Singleton. A bare Murcko ring scaffold (no
    explicit attachment points) is an acceptable core; RDKit assigns R-groups
    at the substituted ring positions. Molecules that do not contain the core,
    and unparseable SMILES, are returned as ``unmatched_ids`` — never dropped.
    """

    def decompose(
        self, *, core_smiles: str, molecules: list[tuple[UUID, str]]
    ) -> RGroupDecompositionResult:
        core = Chem.MolFromSmiles(core_smiles)
        if core is None:
            logger.warning("rgroup_core_unparseable", core=core_smiles)
            return RGroupDecompositionResult(
                core_smiles=core_smiles,
                unmatched_ids=[mid for mid, _ in molecules],
            )

        mol_ids: list[UUID] = []
        mols: list[Chem.Mol] = []
        bad_ids: list[UUID] = []
        for mid, smi in molecules:
            m = Chem.MolFromSmiles(smi) if smi else None
            if m is None:
                bad_ids.append(mid)
                continue
            mol_ids.append(mid)
            mols.append(m)

        if not mols:
            return RGroupDecompositionResult(core_smiles=core_smiles, unmatched_ids=bad_ids)

        try:
            rows, unmatched_idx = rdRGroupDecomposition.RGroupDecompose(
                [core], mols, asSmiles=True, asRows=True
            )
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("rgroup_decompose_failed", core=core_smiles, exc=str(exc))
            return RGroupDecompositionResult(
                core_smiles=core_smiles, unmatched_ids=[*mol_ids, *bad_ids]
            )

        unmatched_set = set(unmatched_idx)

        # Discover R-group labels across all rows (keys like "R1"; skip "Core").
        seen: set[str] = set()
        for row in rows:
            for key in row:
                if key.startswith("R") and key[1:].isdigit():
                    seen.add(key)
        labels = sorted(seen, key=lambda k: int(k[1:]))

        # rows align with matched mols in input order; unmatched indices skipped.
        assignments: list[RGroupAssignment] = []
        unmatched_ids: list[UUID] = list(bad_ids)
        row_iter = iter(rows)
        for i, mid in enumerate(mol_ids):
            if i in unmatched_set:
                unmatched_ids.append(mid)
                continue
            row = next(row_iter)
            rgroups = {k: row[k] for k in labels if k in row}
            assignments.append(RGroupAssignment(molecule_id=mid, rgroups=rgroups))

        return RGroupDecompositionResult(
            core_smiles=core_smiles,
            rgroup_labels=labels,
            assignments=assignments,
            unmatched_ids=unmatched_ids,
        )
