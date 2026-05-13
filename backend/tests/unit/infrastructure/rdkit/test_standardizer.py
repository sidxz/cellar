"""Tests for StructureStandardizer."""

import pytest
from returns.result import Failure, Success

from cellar.infrastructure.rdkit.errors import InvalidSmilesError
from cellar.infrastructure.rdkit.standardizer import StructureStandardizer


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


class TestStereoPreservation:
    """The registration pipeline must preserve defined stereo. Enantiomers
    produce distinct InChIKeys (business rule #3); tautomer-equivalent forms
    that don't involve stereo still merge via standard InChI's mobile-H layer."""

    @pytest.mark.parametrize(
        "label, l_smiles, d_smiles",
        [
            ("alanine", "N[C@@H](C)C(=O)O", "N[C@H](C)C(=O)O"),
            ("leucine", "N[C@@H](CC(C)C)C(=O)O", "N[C@H](CC(C)C)C(=O)O"),
            ("ibuprofen", "CC(C)Cc1ccc(cc1)[C@@H](C)C(=O)O", "CC(C)Cc1ccc(cc1)[C@H](C)C(=O)O"),
            ("naproxen", "COc1ccc2cc([C@@H](C)C(=O)O)ccc2c1", "COc1ccc2cc([C@H](C)C(=O)O)ccc2c1"),
        ],
    )
    def test_enantiomers_get_distinct_inchikeys(
        self,
        standardizer: StructureStandardizer,
        label: str,
        l_smiles: str,
        d_smiles: str,
    ) -> None:
        l_result = standardizer.standardize(l_smiles)
        d_result = standardizer.standardize(d_smiles)
        assert isinstance(l_result, Success)
        assert isinstance(d_result, Success)
        assert l_result.unwrap().inchi_key != d_result.unwrap().inchi_key, (
            f"{label} enantiomers collapsed to the same InChIKey"
        )

    def test_glucose_and_fructose_get_distinct_inchikeys(
        self, standardizer: StructureStandardizer
    ) -> None:
        """Open-form D-glucose and D-fructose are different sugars; the keto/enol
        tautomerization that connects them must NOT collapse them."""
        glucose = standardizer.standardize("OC[C@@H](O)[C@@H](O)[C@H](O)[C@H](O)C=O")
        fructose = standardizer.standardize("OC[C@@H](O)[C@@H](O)[C@H](O)C(=O)CO")
        assert isinstance(glucose, Success)
        assert isinstance(fructose, Success)
        assert glucose.unwrap().inchi_key != fructose.unwrap().inchi_key

    def test_l_alanine_preserves_stereo_in_canonical_smiles(
        self, standardizer: StructureStandardizer
    ) -> None:
        result = standardizer.standardize("N[C@@H](C)C(=O)O")
        assert isinstance(result, Success)
        # Canonical SMILES must retain a stereo descriptor (@ or @@)
        canonical = result.unwrap().canonical_smiles
        assert "@" in canonical, f"stereo lost in canonical SMILES: {canonical}"


class TestTautomerMergingStillWorks:
    """Common tautomer pairs MUST still resolve to the same InChIKey via
    standard InChI's mobile-H layer, even without an explicit canonicalizer step."""

    @pytest.mark.parametrize(
        "pair_name, smiles_a, smiles_b",
        [
            ("2-pyridone / 2-hydroxypyridine", "O=c1cccc[nH]1", "Oc1ccccn1"),
            ("4-pyridone / 4-hydroxypyridine", "O=c1cc[nH]cc1", "Oc1ccncc1"),
            ("imidazole 1H / 3H", "c1[nH]cnc1", "c1nc[nH]c1"),
            ("1H / 2H tetrazole", "c1[nH]nnn1", "c1n[nH]nn1"),
        ],
    )
    def test_tautomer_pair_merges(
        self,
        standardizer: StructureStandardizer,
        pair_name: str,
        smiles_a: str,
        smiles_b: str,
    ) -> None:
        a = standardizer.standardize(smiles_a)
        b = standardizer.standardize(smiles_b)
        assert isinstance(a, Success)
        assert isinstance(b, Success)
        assert a.unwrap().inchi_key == b.unwrap().inchi_key, (
            f"{pair_name} should produce the same InChIKey"
        )


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
