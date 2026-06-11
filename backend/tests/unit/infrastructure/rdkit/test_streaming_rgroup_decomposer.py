from __future__ import annotations

import uuid

from cellar.infrastructure.rdkit.rgroup_decomposer import RGroupDecomposer
from cellar.infrastructure.rdkit.streaming_rgroup_decomposer import (
    StreamingRGroupDecomposer,
)

CORE = "c1ccccc1"


def _stream(mols):
    session = StreamingRGroupDecomposer().session(core_smiles=CORE)
    for mid, smi in mols:
        session.add(mid, smi)
    return session.finish()


def test_streaming_matches_functional_oracle():
    f_id, cl_id, me_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    mols = [(f_id, "Fc1ccccc1"), (cl_id, "Clc1ccccc1"), (me_id, "Cc1ccccc1")]

    streamed = _stream(mols)
    ref = RGroupDecomposer().decompose(core_smiles=CORE, molecules=mols)

    assert streamed.rgroup_labels == ref.rgroup_labels
    assert {a.molecule_id: a.rgroups for a in streamed.assignments} == {
        a.molecule_id: a.rgroups for a in ref.assignments
    }
    assert set(streamed.unmatched_ids) == set(ref.unmatched_ids)


def test_unmatched_molecule_is_surfaced_not_dropped():
    good, bad, no_smi = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    res = _stream([(good, "Fc1ccccc1"), (bad, "CCO"), (no_smi, "")])

    assert good in {a.molecule_id for a in res.assignments}
    assert bad in res.unmatched_ids       # aliphatic — no benzene core
    assert no_smi in res.unmatched_ids    # empty SMILES
    accounted = {a.molecule_id for a in res.assignments} | set(res.unmatched_ids)
    assert accounted == {good, bad, no_smi}


def test_unparseable_core_marks_all_unmatched():
    a, b = uuid.uuid4(), uuid.uuid4()
    session = StreamingRGroupDecomposer().session(core_smiles="not-a-smiles")
    session.add(a, "Fc1ccccc1")
    session.add(b, "Clc1ccccc1")
    res = session.finish()

    assert res.assignments == []
    assert set(res.unmatched_ids) == {a, b}


def test_labels_consistent_across_molecules_substituting_different_positions():
    # Each molecule varies a different ring position. A per-batch *independent*
    # decomposition could disagree on the label set; the single session must give
    # every assignment labels drawn from one shared, consistent set.
    ids = [uuid.uuid4() for _ in range(3)]
    res = _stream(
        [(ids[0], "Fc1ccccc1"), (ids[1], "Clc1ccc(C)cc1"), (ids[2], "Cc1ccccc1")]
    )
    for asg in res.assignments:
        assert set(asg.rgroups).issubset(set(res.rgroup_labels))
