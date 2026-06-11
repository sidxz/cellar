"""Streaming R-group decomposition.

A single stateful ``rdRGroupDecomposition.RGroupDecomposition`` accepts
molecules across many batches and labels them consistently only at
``finish()``. This is the streaming-correctness keystone: decomposing each
batch with an *independent* RDKit object could assign different R-labels to the
same physical position across batches (RDKit discovers labels from the set it
sees). One shared object avoids that — memory is O(matched set), which equals
the congeneric series, not the whole collection.
"""

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


class RGroupDecompositionSession:
    """Accumulate molecules, then decompose them against the core in one pass."""

    def __init__(self, core_smiles: str) -> None:
        self._core_smiles = core_smiles
        self._finished = False
        core = Chem.MolFromSmiles(core_smiles)
        self._added_ids: list[UUID] = []
        self._unmatched_ids: list[UUID] = []
        if core is None:
            logger.warning("streaming_rgroup_core_unparseable", core=core_smiles)
            self._rgd = None
        else:
            params = rdRGroupDecomposition.RGroupDecompositionParameters()
            self._rgd = rdRGroupDecomposition.RGroupDecomposition([core], params)

    def add(self, molecule_id: UUID, smiles: str) -> bool:
        """Add one molecule. Returns True if it matched the core and was added."""
        if self._rgd is None:
            self._unmatched_ids.append(molecule_id)
            return False
        mol = Chem.MolFromSmiles(smiles) if smiles else None
        if mol is None:
            self._unmatched_ids.append(molecule_id)
            return False
        if self._rgd.Add(mol) < 0:
            self._unmatched_ids.append(molecule_id)
            return False
        self._added_ids.append(molecule_id)
        return True

    def finish(self) -> RGroupDecompositionResult:
        if self._finished:
            raise RuntimeError("RGroupDecompositionSession.finish() called more than once")
        self._finished = True

        if self._rgd is None or not self._added_ids:
            return RGroupDecompositionResult(
                core_smiles=self._core_smiles,
                unmatched_ids=list(self._unmatched_ids),
            )
        try:
            processed = self._rgd.Process()
            if not processed:
                logger.warning(
                    "streaming_rgroup_process_failed",
                    core=self._core_smiles,
                    n_added=len(self._added_ids),
                )
                return RGroupDecompositionResult(
                    core_smiles=self._core_smiles,
                    unmatched_ids=[*self._added_ids, *self._unmatched_ids],
                )
            rows = self._rgd.GetRGroupsAsRows(asSmiles=True)
            seen: set[str] = set()
            for row in rows:
                for key in row:
                    if key.startswith("R") and key[1:].isdigit():
                        seen.add(key)
            labels = sorted(seen, key=lambda k: int(k[1:]))
            assignments = [
                RGroupAssignment(
                    molecule_id=mid,
                    rgroups={k: row[k] for k in labels if k in row},
                )
                for mid, row in zip(self._added_ids, rows)
            ]
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("streaming_rgroup_decompose_failed", core=self._core_smiles, exc=str(exc))
            return RGroupDecompositionResult(
                core_smiles=self._core_smiles,
                unmatched_ids=[*self._added_ids, *self._unmatched_ids],
            )
        return RGroupDecompositionResult(
            core_smiles=self._core_smiles,
            rgroup_labels=labels,
            assignments=assignments,
            unmatched_ids=list(self._unmatched_ids),
        )


class StreamingRGroupDecomposer:
    """Factory for one decomposition session per (core, member-stream)."""

    def session(self, *, core_smiles: str) -> RGroupDecompositionSession:
        return RGroupDecompositionSession(core_smiles)
