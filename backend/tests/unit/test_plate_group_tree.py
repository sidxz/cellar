"""Unit tests for plate-group tree building + cycle detection (pure logic)."""

from __future__ import annotations

import uuid

from cellar.application.inventory.plate_groups import build_tree, is_descendant
from cellar.domain.inventory.plate_group import PlateGroup

WS = uuid.uuid4()
ORG = uuid.uuid4()
USER = uuid.uuid4()


def _g(name: str, parent: uuid.UUID | None = None) -> PlateGroup:
    return PlateGroup.create(
        workspace_id=WS, owner_org_id=ORG, name=name, created_by=USER,
        parent_group_id=parent,
    )


def test_build_tree_nests_and_counts() -> None:
    root = _g("Root")
    a = _g("A", parent=root.id)
    b = _g("B", parent=root.id)
    leaf = _g("Leaf", parent=a.id)
    nodes = build_tree([root, a, b, leaf], {a.id: 2, leaf.id: 5})
    assert len(nodes) == 1
    assert nodes[0].group.id == root.id
    assert nodes[0].plate_count == 0
    kids = {n.group.name: n for n in nodes[0].children}
    assert set(kids) == {"A", "B"}
    assert kids["A"].plate_count == 2
    assert kids["A"].children[0].group.id == leaf.id
    assert kids["A"].children[0].plate_count == 5


def test_build_tree_orphan_parent_becomes_root() -> None:
    # Parent id points at a group not in the fetched set (e.g. data from
    # another org filter) — tolerate by promoting to root, never crash.
    orphan = _g("Orphan", parent=uuid.uuid4())
    nodes = build_tree([orphan], {})
    assert len(nodes) == 1
    assert nodes[0].group.id == orphan.id


def test_build_tree_sorts_siblings_by_name() -> None:
    b = _g("Beta")
    a = _g("Alpha")
    nodes = build_tree([b, a], {})
    assert [n.group.name for n in nodes] == ["Alpha", "Beta"]


def test_is_descendant() -> None:
    root = _g("Root")
    mid = _g("Mid", parent=root.id)
    leaf = _g("Leaf", parent=mid.id)
    by_id = {g.id: g for g in (root, mid, leaf)}
    assert is_descendant(by_id, root.id, leaf.id) is True
    assert is_descendant(by_id, mid.id, leaf.id) is True
    assert is_descendant(by_id, leaf.id, root.id) is False
    assert is_descendant(by_id, leaf.id, leaf.id) is True  # self counts


def test_is_descendant_tolerates_broken_chain() -> None:
    stray = _g("Stray", parent=uuid.uuid4())  # parent not in map
    by_id = {stray.id: stray}
    assert is_descendant(by_id, uuid.uuid4(), stray.id) is False
