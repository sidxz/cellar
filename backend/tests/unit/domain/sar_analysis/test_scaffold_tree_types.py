from __future__ import annotations
import uuid

from cellar.domain.sar_analysis.scaffold_tree_types import (
    NO_SCAFFOLD_SENTINEL,
    ScaffoldTreeEdge,
    ScaffoldTreeNode,
    ScaffoldTreeResult,
    ScaffoldTreeStats,
)


def test_no_scaffold_sentinel_value():
    assert NO_SCAFFOLD_SENTINEL == "__no_scaffold__"


def test_node_round_trip_dict():
    mid = uuid.uuid4()
    node = ScaffoldTreeNode(
        scaffold_smiles="c1ccccc1",
        molecule_ids=[mid],
        molecule_count=1,
        subtree_molecule_count=1,
    )
    assert node.scaffold_smiles == "c1ccccc1"
    assert node.molecule_ids == [mid]


def test_result_has_nodes_edges_stats():
    result = ScaffoldTreeResult(
        nodes=[],
        edges=[],
        stats=ScaffoldTreeStats(node_count=0, elapsed_ms=10, cache_hit=False),
    )
    assert result.nodes == []
    assert result.stats.cache_hit is False


def test_edge_parent_child():
    e = ScaffoldTreeEdge(parent_smiles="c1ccccc1", child_smiles="c1ccc2ccccc2c1")
    assert e.parent_smiles == "c1ccccc1"
    assert e.child_smiles == "c1ccc2ccccc2c1"


def test_stats_truncated_default_false():
    s = ScaffoldTreeStats(node_count=0, elapsed_ms=0, cache_hit=False)
    assert s.truncated is False


def test_result_default_empty():
    r = ScaffoldTreeResult()
    assert r.nodes == []
    assert r.edges == []
    assert r.stats.node_count == 0
