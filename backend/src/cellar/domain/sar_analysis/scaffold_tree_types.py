"""Pure-data result types for the scaffold tree view.

Serializable to JSON (round-trip via dataclasses.asdict + custom UUID handling).
No behavior — see application.sar_analysis.build_scaffold_network for compute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

NO_SCAFFOLD_SENTINEL = "__no_scaffold__"


@dataclass(frozen=True)
class ScaffoldTreeNode:
    scaffold_smiles: str  # canonical SMILES or NO_SCAFFOLD_SENTINEL
    molecule_ids: list[UUID]
    molecule_count: int
    subtree_molecule_count: int


@dataclass(frozen=True)
class ScaffoldTreeEdge:
    parent_smiles: str
    child_smiles: str


@dataclass(frozen=True)
class ScaffoldTreeStats:
    node_count: int
    elapsed_ms: int
    cache_hit: bool
    truncated: bool = False


@dataclass(frozen=True)
class ScaffoldTreeResult:
    nodes: list[ScaffoldTreeNode] = field(default_factory=list)
    edges: list[ScaffoldTreeEdge] = field(default_factory=list)
    stats: ScaffoldTreeStats = field(
        default_factory=lambda: ScaffoldTreeStats(node_count=0, elapsed_ms=0, cache_hit=False)
    )
