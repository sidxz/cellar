"""Tests for DescriptorCalculator."""

import pytest
from rdkit import Chem

from chem_vault.infrastructure.rdkit.descriptor_calculator import DescriptorCalculator


@pytest.fixture
def calculator() -> DescriptorCalculator:
    return DescriptorCalculator()


class TestDescriptorCalculator:
    def test_aspirin_descriptors(self, calculator: DescriptorCalculator) -> None:
        mol = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
        desc = calculator.calculate(mol)
        assert desc.molecular_formula == "C9H8O4"
        assert 180.0 < desc.molecular_weight < 181.0
        assert desc.exact_mass is not None
        assert desc.logp is not None
        assert desc.tpsa > 0
        assert desc.hbd >= 0
        assert desc.hba >= 0
        assert desc.rotatable_bonds >= 0
        assert desc.aromatic_rings == 1
        assert desc.ring_count == 1
        assert desc.heavy_atom_count == 13
        assert desc.ro5_violations == 0

    def test_caffeine_descriptors(self, calculator: DescriptorCalculator) -> None:
        mol = Chem.MolFromSmiles("Cn1c(=O)c2c(ncn2C)n(C)c1=O")
        desc = calculator.calculate(mol)
        assert desc.molecular_formula == "C8H10N4O2"
        assert 194.0 < desc.molecular_weight < 195.0
        assert desc.aromatic_rings >= 1

    def test_benzene_descriptors(self, calculator: DescriptorCalculator) -> None:
        mol = Chem.MolFromSmiles("c1ccccc1")
        desc = calculator.calculate(mol)
        assert desc.molecular_formula == "C6H6"
        assert desc.aromatic_rings == 1
        assert desc.ring_count == 1
        assert desc.heavy_atom_count == 6
        assert desc.hbd == 0

    def test_returns_frozen_vo(self, calculator: DescriptorCalculator) -> None:
        mol = Chem.MolFromSmiles("CC")
        desc = calculator.calculate(mol)
        with pytest.raises(Exception):  # Pydantic frozen model
            desc.molecular_weight = 999.0  # type: ignore[misc]

    def test_large_molecule_ro5(self, calculator: DescriptorCalculator) -> None:
        # A molecule that violates Ro5: MW>500, LogP>5, HBD>5
        # Erythromycin (MW ~733, HBD=5, HBA=14)
        mol = Chem.MolFromSmiles(
            "CCC1OC(=O)C(C)C(OC2CC(C)(OC)C(O)C(C)O2)C(C)C(OC3OC(C)CC(N(C)C)C3O)"
            "C(C)(O)CC(C)C(=O)C(C)C(O)C1(C)O"
        )
        assert mol is not None
        desc = calculator.calculate(mol)
        assert desc.molecular_weight > 500
        assert desc.ro5_violations > 0
