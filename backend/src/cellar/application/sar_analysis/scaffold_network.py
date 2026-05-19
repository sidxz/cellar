"""Application-layer port for the scaffold-network builder.

The concrete implementation lives in
``cellar.infrastructure.rdkit.scaffold_network_builder.ScaffoldNetworkBuilder``
and is wired in via DI. The application layer depends only on this Protocol +
the pure-data ``RawScaffoldNetwork`` shape so the layer-dependency rule
(application MUST NOT import infrastructure) is preserved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class RawScaffoldNetwork:
    """Pure-data result of a Schuffenhauer scaffold network build.

    Edge tuples are ``(parent_simpler, child_more_complex)`` — chemist-intuitive
    direction (benzene as parent, decorated descendants beneath).
    """

    node_smiles: list[str] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)


class ScaffoldNetworkBuilder(Protocol):
    """Builds a Schuffenhauer scaffold network from a list of mol objects.

    The concrete impl accepts ``rdkit.Chem.Mol`` instances; this Protocol
    leaves the element type as ``Any`` so the application layer doesn't
    declare its own rdkit dependency at the Protocol boundary.
    """

    def build(self, mols: list[Any]) -> RawScaffoldNetwork: ...
