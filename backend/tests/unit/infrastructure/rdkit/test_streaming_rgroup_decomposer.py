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
    # A di-substituted molecule forces a 2nd R-position; the mono-substituted
    # ones must be handled consistently against it. Streaming (one shared RDKit
    # object) must equal the functional oracle on this multi-position set — the
    # §8.1 invariant a per-batch *independent* decomposition would break.
    ids = [uuid.uuid4() for _ in range(3)]
    mols = [(ids[0], "Fc1ccccc1"), (ids[1], "Clc1ccc(C)cc1"), (ids[2], "Cc1ccccc1")]

    res = _stream(mols)
    ref = RGroupDecomposer().decompose(core_smiles=CORE, molecules=mols)

    assert len(res.rgroup_labels) >= 2  # the multi-position scenario is real, not vacuous
    assert res.rgroup_labels == ref.rgroup_labels
    assert {a.molecule_id: a.rgroups for a in res.assignments} == {
        a.molecule_id: a.rgroups for a in ref.assignments
    }
    assert set(res.unmatched_ids) == set(ref.unmatched_ids)


def test_canonical_core_smiles_is_stable_across_equivalent_inputs():
    dec = StreamingRGroupDecomposer()
    # Two equivalent ways to write pyridine -> identical RDKit canonical SMILES.
    assert dec.canonical_core_smiles("c1ccncc1") == dec.canonical_core_smiles("n1ccccc1")


def test_canonical_core_smiles_distinguishes_different_cores():
    dec = StreamingRGroupDecomposer()
    assert dec.canonical_core_smiles("c1ccccc1") != dec.canonical_core_smiles("c1ccncc1")


def test_canonical_core_smiles_falls_back_to_stripped_raw_when_unparseable():
    dec = StreamingRGroupDecomposer()
    assert dec.canonical_core_smiles("  not-a-smiles  ") == "not-a-smiles"
