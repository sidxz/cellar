from __future__ import annotations
import pytest
from rdkit import Chem
from cellar.infrastructure.rdkit.scaffold_calculator import MurckoScaffoldCalculator


@pytest.fixture()
def calc():
    return MurckoScaffoldCalculator()


def test_benzene_scaffold_is_benzene(calc):
    mol = Chem.MolFromSmiles("c1ccccc1")
    assert calc.compute(mol) == "c1ccccc1"


def test_ibuprofen_scaffold_is_benzene(calc):
    mol = Chem.MolFromSmiles("CC(C)Cc1ccc(cc1)C(C)C(=O)O")
    assert calc.compute(mol) == "c1ccccc1"


def test_acyclic_returns_empty_string(calc):
    mol = Chem.MolFromSmiles("CCCCC")
    assert calc.compute(mol) == ""


def test_biaryl_scaffold(calc):
    mol = Chem.MolFromSmiles("c1ccc(-c2ccccc2)cc1")
    assert calc.compute(mol) == "c1ccc(-c2ccccc2)cc1"


def test_fused_ring_naphthalene(calc):
    mol = Chem.MolFromSmiles("c1ccc2ccccc2c1")
    assert calc.compute(mol) == "c1ccc2ccccc2c1"


def test_diphenhydramine_keeps_aromatic_rings(calc):
    mol = Chem.MolFromSmiles("c1ccc(C(OCCN(C)C)c2ccccc2)cc1")
    scaffold = calc.compute(mol)
    assert scaffold is not None
    # Murcko keeps both rings + the linker carbon
    assert scaffold  # truthy — non-empty
    assert "ccccc1" in scaffold or "c1ccc" in scaffold


def test_invalid_mol_returns_none(calc):
    # Defensive: None input -> None output, no crash
    assert calc.compute(None) is None  # type: ignore[arg-type]
