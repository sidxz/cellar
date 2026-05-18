"""Wraps RDKit rdScaffoldNetwork.CreateScaffoldNetwork into a pure-data result.

The use case layer maps node SMILES back to owning molecule IDs using the
stored bemis_murcko_smiles column.  This module returns the raw network
shape only — no membership information.

Edge direction (chemist-facing semantics): (parent_smiles, child_smiles)
means *parent is the simpler / more general scaffold (ancestor) and child
is the more elaborated descendant*. This is the convention chemists expect
when reading a scaffold tree top-down (benzene at the root, decorated /
fused / bridged ring systems beneath it).

RDKit's internal edge representation is the other way around — `beginIdx`
is the more complex scaffold and `endIdx` is the simpler parent. We flip
the tuple at construction so the wire shape is unambiguous downstream.

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
        # Default ScaffoldNetworkParams() emits FOUR variants per scaffold:
        # the bare ring skeleton, a `*`-marked "with attachments" form, and
        # generic / generic-bond variants where atoms or bonds are replaced
        # by `*`. For chemist-facing tree rendering we only want the bare
        # ring skeleton (matches stored bemis_murcko_smiles). Disable the
        # other three explicitly so RDKit upgrades can't silently re-add them.
        self._params = rdScaffoldNetwork.ScaffoldNetworkParams()
        self._params.includeScaffoldsWithAttachments = False
        self._params.includeScaffoldsWithoutAttachments = True
        self._params.includeGenericScaffolds = False
        self._params.includeGenericBondScaffolds = False
        self._params.keepOnlyFirstFragment = True
        self._params.pruneBeforeFragmenting = True
        self._params.flattenChirality = True
        self._params.flattenIsotopes = True
        self._params.flattenKeepLargest = True

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

        # Flip RDKit's convention so (parent, child) means (ancestor, descendant)
        # in chemist terms. RDKit emits beginIdx=complex, endIdx=simpler ancestor;
        # we re-tuple as (parent=simpler, child=more-complex). See module docstring.
        edges: list[tuple[str, str]] = []
        for edge in net.edges:
            try:
                more_complex = node_smiles[edge.beginIdx]
                simpler_ancestor = node_smiles[edge.endIdx]
            except IndexError:  # pragma: no cover
                continue
            edges.append((simpler_ancestor, more_complex))

        return RawScaffoldNetwork(node_smiles=node_smiles, edges=edges)
