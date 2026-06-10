from __future__ import annotations

import uuid

import pytest

from cellar.infrastructure.rdkit.rgroup_decomposer import RGroupDecomposer


@pytest.fixture()
def decomposer():
    return RGroupDecomposer()


def test_monosubstituted_benzenes_decompose_against_benzene(decomposer):
    f_id, cl_id, me_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    result = decomposer.decompose(
        core_smiles="c1ccccc1",
        molecules=[(f_id, "Fc1ccccc1"), (cl_id, "Clc1ccccc1"), (me_id, "Cc1ccccc1")],
    )
    assert "R1" in result.rgroup_labels
    assert len(result.assignments) == 3
    assert result.unmatched_ids == []
    by_id = {a.molecule_id: a for a in result.assignments}
    # Each molecule's R-group set carries its substituent somewhere.
    assert any("F" in v for v in by_id[f_id].rgroups.values())
    assert any("Cl" in v for v in by_id[cl_id].rgroups.values())


def test_non_matching_molecule_is_unmatched(decomposer):
    benzene_sub, pyridine = uuid.uuid4(), uuid.uuid4()
    result = decomposer.decompose(
        core_smiles="c1ccccc1",
        molecules=[(benzene_sub, "Fc1ccccc1"), (pyridine, "c1ccncc1")],
    )
    assert pyridine in result.unmatched_ids
    assert benzene_sub not in result.unmatched_ids
    assert pyridine not in {x.molecule_id for x in result.assignments}


def test_unparseable_core_returns_all_unmatched(decomposer):
    a = uuid.uuid4()
    result = decomposer.decompose(core_smiles="not-a-smiles", molecules=[(a, "c1ccccc1")])
    assert result.unmatched_ids == [a]
    assert result.assignments == []


def test_unparseable_molecule_is_unmatched(decomposer):
    good, bad = uuid.uuid4(), uuid.uuid4()
    result = decomposer.decompose(
        core_smiles="c1ccccc1",
        molecules=[(good, "Fc1ccccc1"), (bad, "Q!Q!Q")],
    )
    assert bad in result.unmatched_ids
    assert good not in result.unmatched_ids


def test_empty_molecules_returns_empty(decomposer):
    result = decomposer.decompose(core_smiles="c1ccccc1", molecules=[])
    assert result.assignments == []
    assert result.unmatched_ids == []


def test_disubstituted_molecule_yields_two_rgroups(decomposer):
    mid = uuid.uuid4()
    result = decomposer.decompose(
        core_smiles="c1ccccc1",
        molecules=[(mid, "Fc1ccc(Cl)cc1")],
    )
    assert len(result.assignments) == 1
    assert len(result.rgroup_labels) >= 2
    values = " ".join(result.assignments[0].rgroups.values())
    assert "F" in values
    assert "Cl" in values


def test_midsequence_unmatched_preserves_alignment(decomposer):
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    result = decomposer.decompose(
        core_smiles="c1ccccc1",
        molecules=[(a, "Fc1ccccc1"), (b, "c1ccncc1"), (c, "Clc1ccccc1")],
    )
    assert b in result.unmatched_ids
    by_id = {x.molecule_id: x for x in result.assignments}
    assert set(by_id) == {a, c}
    assert any("F" in v for v in by_id[a].rgroups.values())
    assert any("Cl" in v for v in by_id[c].rgroups.values())
