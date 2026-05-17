"""Tests for StructureProcessor — end-to-end pipeline."""

import pytest
from returns.result import Failure, Success

from cellar.domain.chemical_registration.enums import Stereochemistry
from cellar.infrastructure.rdkit.errors import InvalidSmilesError, QCRejectedError
from cellar.infrastructure.rdkit.scaffold_calculator import MurckoScaffoldCalculator
from cellar.infrastructure.rdkit.structure_processor import StructureProcessor


@pytest.fixture
def processor() -> StructureProcessor:
    return StructureProcessor(scaffold_calculator=MurckoScaffoldCalculator())


class TestStructureProcessor:
    def test_process_aspirin(self, processor: StructureProcessor) -> None:
        result = processor.process("CC(=O)Oc1ccccc1C(O)=O")
        assert isinstance(result, Success)
        out = result.unwrap()

        # Structure VO
        assert out.structure.smiles is not None
        assert out.structure.inchi_key is not None
        assert out.structure.molfile is not None

        # Descriptors VO
        assert out.descriptors.molecular_formula == "C9H8O4"
        assert out.descriptors.molecular_weight > 0

        # Fingerprints
        assert isinstance(out.fingerprints.morgan, bytes)
        assert len(out.fingerprints.morgan) > 0

        # QC
        assert out.qc_result.is_clean

    def test_process_caffeine(self, processor: StructureProcessor) -> None:
        result = processor.process("Cn1c(=O)c2c(ncn2C)n(C)c1=O")
        assert isinstance(result, Success)
        out = result.unwrap()
        assert "RYYVLZVUVIJVGH" in out.structure.inchi_key

    def test_process_invalid_smiles(self, processor: StructureProcessor) -> None:
        result = processor.process("totally_invalid")
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), InvalidSmilesError)

    def test_qc_reject_threshold(self, processor: StructureProcessor) -> None:
        # A radical molecule should get a QC penalty
        result = processor.process("[CH2]C", qc_reject_threshold=1)
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), QCRejectedError)

    def test_qc_no_threshold_accepts_everything(
        self, processor: StructureProcessor
    ) -> None:
        # Without threshold, even radical passes
        result = processor.process("[CH2]C")
        assert isinstance(result, Success)

    def test_structure_vo_all_populated(self, processor: StructureProcessor) -> None:
        result = processor.process("c1ccccc1")
        assert isinstance(result, Success)
        s = result.unwrap().structure
        assert s.smiles is not None
        assert s.cxsmiles is not None
        assert s.inchi is not None
        assert s.inchi_key is not None
        assert s.molfile is not None
        assert s.is_disclosed

    def test_detected_salt_for_sodium_salt(self, processor: StructureProcessor) -> None:
        """Sodium aspirin: [Na+].CC(=O)Oc1ccccc1C(=O)[O-] should detect Na salt."""
        result = processor.process("[Na+].CC(=O)Oc1ccccc1C(=O)[O-]")
        assert isinstance(result, Success)
        out = result.unwrap()
        assert out.detected_salt is not None
        assert out.detected_salt.stoichiometry == 1
        assert out.detected_salt.salt_fragment_mw > 0

    def test_no_salt_for_simple_molecule(self, processor: StructureProcessor) -> None:
        """Aspirin (no salt) should return detected_salt=None."""
        result = processor.process("CC(=O)Oc1ccccc1C(O)=O")
        assert isinstance(result, Success)
        out = result.unwrap()
        assert out.detected_salt is None

    def test_deterministic_across_calls(self, processor: StructureProcessor) -> None:
        r1 = processor.process("CC(=O)Oc1ccccc1C(=O)O")
        r2 = processor.process("CC(=O)Oc1ccccc1C(=O)O")
        assert isinstance(r1, Success)
        assert isinstance(r2, Success)
        assert r1.unwrap().structure.inchi_key == r2.unwrap().structure.inchi_key
        assert r1.unwrap().descriptors == r2.unwrap().descriptors


class TestStereoClassification:
    """The processor populates Molecule.stereochemistry. Atom stereo and
    double-bond stereo both count toward the classification."""

    def test_achiral(self, processor: StructureProcessor) -> None:
        result = processor.process("CC(=O)Oc1ccccc1C(=O)O")  # aspirin
        assert isinstance(result, Success)
        assert result.unwrap().stereochemistry == Stereochemistry.ACHIRAL

    def test_single_atom_stereo(self, processor: StructureProcessor) -> None:
        result = processor.process("CC[C@H](C)O")  # (R)-2-butanol
        assert isinstance(result, Success)
        assert result.unwrap().stereochemistry == Stereochemistry.SINGLE_STEREO

    def test_multi_atom_stereo(self, processor: StructureProcessor) -> None:
        result = processor.process("C[C@@H](Cl)[C@@H](Cl)C")  # (2R,3R)-2,3-Cl-butane
        assert isinstance(result, Success)
        assert result.unwrap().stereochemistry == Stereochemistry.MULTI_STEREO

    def test_undefined(self, processor: StructureProcessor) -> None:
        result = processor.process("CCC(C)O")  # 2-butanol, no stereo specified
        assert isinstance(result, Success)
        assert result.unwrap().stereochemistry == Stereochemistry.UNDEFINED

    def test_mixed_defined_and_undefined(self, processor: StructureProcessor) -> None:
        result = processor.process("C[C@H](Cl)C(Cl)C")  # one center defined, one not
        assert isinstance(result, Success)
        assert result.unwrap().stereochemistry == Stereochemistry.UNDEFINED

    def test_l_alanine_now_preserves_stereo(self, processor: StructureProcessor) -> None:
        """Regression target: L-alanine used to classify as UNDEFINED because
        the dropped TautomerEnumerator step stripped its alpha-carbon stereo."""
        result = processor.process("N[C@@H](C)C(=O)O")
        assert isinstance(result, Success)
        assert result.unwrap().stereochemistry == Stereochemistry.SINGLE_STEREO

    def test_double_bond_stereo_counts(self, processor: StructureProcessor) -> None:
        """(E)-stilbene has a defined stereogenic double bond — SINGLE_STEREO."""
        result = processor.process("C(=C/c1ccccc1)\\c1ccccc1")
        assert isinstance(result, Success)
        assert result.unwrap().stereochemistry == Stereochemistry.SINGLE_STEREO

    def test_e_and_z_distinct_inchikeys(self, processor: StructureProcessor) -> None:
        """Fumarate (E) and maleate (Z) must produce different InChIKeys."""
        e = processor.process("OC(=O)/C=C/C(=O)O")
        z = processor.process("OC(=O)/C=C\\C(=O)O")
        assert isinstance(e, Success)
        assert isinstance(z, Success)
        assert e.unwrap().structure.inchi_key != z.unwrap().structure.inchi_key

    def test_atom_plus_bond_stereo_is_multi(self, processor: StructureProcessor) -> None:
        """A compound with both an atom stereocenter and a defined double bond
        is MULTI_STEREO."""
        result = processor.process("C[C@H](O)/C=C/c1ccccc1")
        assert isinstance(result, Success)
        assert result.unwrap().stereochemistry == Stereochemistry.MULTI_STEREO
