"""MaxMinPickerAdapter — picks N diverse indices via RDKit SimDivFilters."""

from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import AllChem

from cellar.infrastructure.rdkit.maxmin_picker import MaxMinPickerAdapter


def _ecfp4(smiles: str):
    mol = Chem.MolFromSmiles(smiles)
    return AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048)


def test_maxmin_picks_distinct_indices_in_range() -> None:
    smiles = ["c1ccccc1", "Cc1ccccc1", "CCc1ccccc1", "c1ccncc1", "Cc1ccncc1", "CCO", "O=C(O)CCC"]
    fps = [_ecfp4(s) for s in smiles]
    picker = MaxMinPickerAdapter()
    picks = picker.pick(fps, n=4)
    assert len(picks) == 4
    assert len(set(picks)) == 4
    assert all(0 <= p < len(fps) for p in picks)


def test_maxmin_returns_all_when_n_exceeds_size() -> None:
    smiles = ["c1ccccc1", "CCO"]
    fps = [_ecfp4(s) for s in smiles]
    picker = MaxMinPickerAdapter()
    picks = picker.pick(fps, n=10)
    assert sorted(picks) == [0, 1]
