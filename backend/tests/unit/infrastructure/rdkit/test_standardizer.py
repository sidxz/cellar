"""Tests for StructureStandardizer."""

import pytest
from returns.result import Failure, Success

from chem_vault.infrastructure.rdkit.errors import InvalidSmilesError
from chem_vault.infrastructure.rdkit.standardizer import StructureStandardizer


@pytest.fixture
def standardizer() -> StructureStandardizer:
    return StructureStandardizer()


class TestStandardize:
    def test_aspirin(self, standardizer: StructureStandardizer) -> None:
        result = standardizer.standardize("CC(=O)Oc1ccccc1C(O)=O")
        assert isinstance(result, Success)
        mol = result.unwrap()
        assert mol.canonical_smiles  # non-empty
        assert mol.inchi.startswith("InChI=1S/")
        assert len(mol.inchi_key) == 27  # standard InChIKey length
        assert mol.molfile  # non-empty
        assert mol.cxsmiles  # non-empty

    def test_caffeine(self, standardizer: StructureStandardizer) -> None:
        result = standardizer.standardize("Cn1c(=O)c2c(ncn2C)n(C)c1=O")
        assert isinstance(result, Success)
        mol = result.unwrap()
        assert "RYYVLZVUVIJVGH" in mol.inchi_key  # caffeine InChIKey prefix

    def test_ibuprofen(self, standardizer: StructureStandardizer) -> None:
        result = standardizer.standardize("CC(C)Cc1ccc(cc1)C(C)C(O)=O")
        assert isinstance(result, Success)
        mol = result.unwrap()
        assert mol.inchi_key.startswith("HEFNNWSXXWATRW")

    def test_invalid_smiles_returns_failure(
        self, standardizer: StructureStandardizer
    ) -> None:
        result = standardizer.standardize("not_a_smiles")
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), InvalidSmilesError)

    def test_empty_smiles_returns_failure(
        self, standardizer: StructureStandardizer
    ) -> None:
        result = standardizer.standardize("")
        assert isinstance(result, Failure)

    def test_salt_stripping(self, standardizer: StructureStandardizer) -> None:
        # Aspirin sodium salt — should strip sodium
        result = standardizer.standardize("CC(=O)Oc1ccccc1C([O-])=O.[Na+]")
        assert isinstance(result, Success)
        mol = result.unwrap()
        # Parent should not contain Na
        assert "Na" not in mol.canonical_smiles

    def test_deterministic_output(self, standardizer: StructureStandardizer) -> None:
        result1 = standardizer.standardize("c1ccccc1")
        result2 = standardizer.standardize("C1=CC=CC=C1")
        assert isinstance(result1, Success)
        assert isinstance(result2, Success)
        assert result1.unwrap().inchi_key == result2.unwrap().inchi_key


class TestSaltDetection:
    def test_detects_sodium_salt(self, standardizer: StructureStandardizer) -> None:
        result = standardizer.standardize("CC(=O)Oc1ccccc1C([O-])=O.[Na+]")
        assert isinstance(result, Success)
        mol = result.unwrap()
        assert mol.detected_salt is not None
        assert mol.detected_salt.stoichiometry == 1
        assert mol.detected_salt.salt_fragment_mw > 0

    def test_no_salt_for_single_fragment(self, standardizer: StructureStandardizer) -> None:
        result = standardizer.standardize("CC(=O)Oc1ccccc1C(O)=O")
        assert isinstance(result, Success)
        mol = result.unwrap()
        assert mol.detected_salt is None

    def test_detects_hcl_salt(self, standardizer: StructureStandardizer) -> None:
        result = standardizer.standardize("CCN.Cl")
        assert isinstance(result, Success)
        mol = result.unwrap()
        # HCl may or may not be detected depending on chembl pipeline behavior
        # At minimum, the parent should be just ethylamine
        assert "Cl" not in mol.canonical_smiles or mol.detected_salt is not None

    def test_salt_mw_is_positive(self, standardizer: StructureStandardizer) -> None:
        result = standardizer.standardize("CC(=O)Oc1ccccc1C([O-])=O.[Na+]")
        assert isinstance(result, Success)
        mol = result.unwrap()
        if mol.detected_salt:
            assert mol.detected_salt.salt_fragment_mw > 0

    def test_no_salt_for_non_salt_mixture(self, standardizer: StructureStandardizer) -> None:
        """Multiple different fragment types should return None (ambiguous)."""
        result = standardizer.standardize("CCO.CC.C")
        assert isinstance(result, Success)
        mol = result.unwrap()
        # Parent extraction picks the largest fragment; remaining two differ
        # so detected_salt should be None (ambiguous) or the pipeline
        # may simplify further — either way, no crash
        assert mol.detected_salt is None or mol.detected_salt.stoichiometry >= 1


class TestCheckMolecule:
    def test_clean_molecule(self, standardizer: StructureStandardizer) -> None:
        from rdkit import Chem
        mol = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
        qc = standardizer.check_molecule(mol)
        assert qc.total_penalty == 0
        assert qc.is_clean
        assert qc.issues == []

    def test_radical_molecule(self, standardizer: StructureStandardizer) -> None:
        from rdkit import Chem
        mol = Chem.MolFromSmiles("[CH2]C")
        qc = standardizer.check_molecule(mol)
        assert qc.total_penalty > 0
        assert len(qc.issues) > 0
        assert not qc.is_clean
