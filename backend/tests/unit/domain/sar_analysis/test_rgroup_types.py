from __future__ import annotations

import uuid

import pytest

from cellar.domain.sar_analysis.rgroup_types import (
    RGroupAssignment,
    RGroupDecompositionResult,
)


def test_assignment_holds_molecule_and_rgroups():
    mid = uuid.uuid4()
    a = RGroupAssignment(molecule_id=mid, rgroups={"R1": "F[*:1]"})
    assert a.molecule_id == mid
    assert a.rgroups["R1"] == "F[*:1]"


def test_result_defaults_are_empty():
    r = RGroupDecompositionResult(core_smiles="c1ccccc1")
    assert r.core_smiles == "c1ccccc1"
    assert r.rgroup_labels == []
    assert r.assignments == []
    assert r.unmatched_ids == []


def test_result_is_frozen():
    r = RGroupDecompositionResult(core_smiles="c1ccccc1")
    with pytest.raises(Exception):
        r.core_smiles = "c1ccncc1"  # type: ignore[misc]
