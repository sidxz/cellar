"""Wraps RDKit rdScaffoldNetwork.CreateScaffoldNetwork into a pure-data result.

The use case layer maps node SMILES back to owning molecule IDs using the
stored bemis_murcko_smiles column.  This module returns the raw network
shape only — no membership information.

Edge direction: (parent_smiles, child_smiles) following RDKit's convention
where beginIdx → endIdx runs from a more-complex scaffold down toward a
simpler parent (i.e. the scaffold at beginIdx *contains* endIdx as a parent).
Callers that want to render a hierarchy tree should treat the tuple's second
element as the parent node.

Note on fused ring systems: RDKit's Schuffenhauer algorithm does not fragment
fused bicyclics (e.g. naphthalene) into their component rings — such molecules
produce a single node with no edges.  Fragmentation occurs when separate rings
are connected by rotatable bonds (e.g. biphenyl → benzene parent).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog
from rdkit import Chem
from rdkit.Chem.Scaffolds import rdScaffoldNetwork

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RawScaffoldNetwork:
    node_smiles: list[str] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)  # (parent, child)


class ScaffoldNetworkBuilder:
    """Build a Schuffenhauer scaffold network from a collection of RDKit mols.

    Pre-filters None and acyclic inputs (rdScaffoldNetwork raises on them).
    Returns an empty network on RDKit failure rather than propagating the
    exception, so callers can degrade gracefully.
    """

    def __init__(self) -> None:
        # Default ScaffoldNetworkParams() — Schuffenhauer-style hierarchy.
        # Pinned explicitly so RDKit upgrades can't silently shift behavior.
        self._params = rdScaffoldNetwork.ScaffoldNetworkParams()

    def build(self, mols: list[Chem.Mol | None]) -> RawScaffoldNetwork:
        """Return the scaffold network for *mols*.

        Args:
            mols: Any mixture of valid RDKit mols and None values.  None entries
                  and acyclic molecules are silently skipped.

        Returns:
            RawScaffoldNetwork with node_smiles and (parent, child) edges.
        """
        ringed = [
            m
            for m in mols
            if m is not None and m.GetRingInfo().NumRings() > 0
        ]
        if not ringed:
            return RawScaffoldNetwork(node_smiles=[], edges=[])

        try:
            net = rdScaffoldNetwork.CreateScaffoldNetwork(ringed, self._params)
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("scaffold_network_build_failed", exc=str(exc))
            return RawScaffoldNetwork(node_smiles=[], edges=[])

        node_smiles: list[str] = [str(n) for n in net.nodes]

        edges: list[tuple[str, str]] = []
        for edge in net.edges:
            try:
                parent = node_smiles[edge.beginIdx]
                child = node_smiles[edge.endIdx]
            except IndexError:  # pragma: no cover
                continue
            edges.append((parent, child))

        return RawScaffoldNetwork(node_smiles=node_smiles, edges=edges)
