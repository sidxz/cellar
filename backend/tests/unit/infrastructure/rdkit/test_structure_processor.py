"""Tests for StructureProcessor — end-to-end pipeline."""

import pytest
from returns.result import Failure, Success

from chem_vault.infrastructure.rdkit.errors import InvalidSmilesError, QCRejectedError
from chem_vault.infrastructure.rdkit.structure_processor import StructureProcessor


@pytest.fixture
def processor() -> StructureProcessor:
    return StructureProcessor()


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
        assert "morgan" in out.fingerprints
        assert "maccs" in out.fingerprints
        assert len(out.fingerprints) == 5

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

    def test_deterministic_across_calls(self, processor: StructureProcessor) -> None:
        r1 = processor.process("CC(=O)Oc1ccccc1C(=O)O")
        r2 = processor.process("CC(=O)Oc1ccccc1C(=O)O")
        assert isinstance(r1, Success)
        assert isinstance(r2, Success)
        assert r1.unwrap().structure.inchi_key == r2.unwrap().structure.inchi_key
        assert r1.unwrap().descriptors == r2.unwrap().descriptors
