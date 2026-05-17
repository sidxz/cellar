from __future__ import annotations

import pytest
from rdkit import Chem

from cellar.infrastructure.rdkit.scaffold_network_builder import (
    RawScaffoldNetwork,
    ScaffoldNetworkBuilder,
)


@pytest.fixture()
def builder():
    return ScaffoldNetworkBuilder()


def test_empty_list_returns_empty_network(builder):
    net = builder.build([])
    assert net.node_smiles == []
    assert net.edges == []


def test_single_benzene_yields_benzene_node(builder):
    net = builder.build([Chem.MolFromSmiles("c1ccccc1")])
    assert "c1ccccc1" in net.node_smiles


def test_biphenyl_yields_benzene_parent(builder):
    # Biphenyl (two phenyl rings joined by a bond) — the Schuffenhauer algorithm
    # fragments it into benzene as a parent scaffold.  Naphthalene (a single fused
    # ring system) yields only one node in RDKit's implementation; biphenyl is the
    # canonical two-benzene example that actually produces a parent edge.
    net = builder.build([Chem.MolFromSmiles("c1ccc(-c2ccccc2)cc1")])
    assert "c1ccccc1" in net.node_smiles
    assert "c1ccc(-c2ccccc2)cc1" in net.node_smiles
    # At least one edge has benzene as the parent (beginIdx side)
    assert any(e[0] == "c1ccccc1" for e in net.edges)


def test_skips_unparseable_mols(builder):
    mols = [Chem.MolFromSmiles("c1ccccc1"), None]
    net = builder.build(mols)
    assert "c1ccccc1" in net.node_smiles


def test_skips_acyclic_mols(builder):
    # Acyclic (pentane) has no rings — rdScaffoldNetwork would raise on it, so we
    # pre-filter.  The benzene mol should still produce its node.
    mols = [Chem.MolFromSmiles("c1ccccc1"), Chem.MolFromSmiles("CCCCC")]
    net = builder.build(mols)
    assert "c1ccccc1" in net.node_smiles
