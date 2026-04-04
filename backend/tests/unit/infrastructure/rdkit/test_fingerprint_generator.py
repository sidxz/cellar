"""Tests for FingerprintGenerator."""

import pytest
from rdkit import Chem

from chem_vault.infrastructure.rdkit.fingerprint_generator import FingerprintGenerator


@pytest.fixture
def generator() -> FingerprintGenerator:
    return FingerprintGenerator()


class TestFingerprintGenerator:
    def test_generate_all_returns_five_types(
        self, generator: FingerprintGenerator
    ) -> None:
        mol = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
        fps = generator.generate_all(mol)
        assert set(fps.keys()) == {
            "morgan", "rdkit", "maccs", "topological_torsion", "atom_pair"
        }

    def test_all_fingerprints_are_bytes(
        self, generator: FingerprintGenerator
    ) -> None:
        mol = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
        fps = generator.generate_all(mol)
        for name, fp in fps.items():
            assert isinstance(fp, bytes), f"{name} is not bytes"
            assert len(fp) > 0, f"{name} is empty"

    def test_morgan_2048_bits(self, generator: FingerprintGenerator) -> None:
        mol = Chem.MolFromSmiles("c1ccccc1")
        fps = generator.generate_all(mol)
        assert len(fps["morgan"]) == 256  # 2048 bits / 8 = 256 bytes

    def test_maccs_167_bits(self, generator: FingerprintGenerator) -> None:
        mol = Chem.MolFromSmiles("c1ccccc1")
        fps = generator.generate_all(mol)
        assert len(fps["maccs"]) == 21  # 167 bits -> ceil(167/8) = 21 bytes

    def test_deterministic(self, generator: FingerprintGenerator) -> None:
        mol = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
        fps1 = generator.generate_all(mol)
        fps2 = generator.generate_all(mol)
        for name in fps1:
            assert fps1[name] == fps2[name], f"{name} is not deterministic"

    def test_different_molecules_different_fingerprints(
        self, generator: FingerprintGenerator
    ) -> None:
        aspirin = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
        caffeine = Chem.MolFromSmiles("Cn1c(=O)c2c(ncn2C)n(C)c1=O")
        fps_a = generator.generate_all(aspirin)
        fps_c = generator.generate_all(caffeine)
        assert fps_a["morgan"] != fps_c["morgan"]

    def test_generate_morgan_standalone(
        self, generator: FingerprintGenerator
    ) -> None:
        mol = Chem.MolFromSmiles("c1ccccc1")
        fp = generator.generate_morgan(mol)
        assert isinstance(fp, bytes)
        assert len(fp) == 256
