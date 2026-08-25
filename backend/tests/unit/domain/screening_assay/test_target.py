"""Tests for Target entity."""

import uuid

import pytest

from cellar.domain.screening_assay.enums import TargetType
from cellar.domain.screening_assay.target import Target
from cellar.domain.shared.errors import ValidationError


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_target(workspace_id: uuid.UUID, **kwargs) -> Target:
    defaults = dict(
        workspace_id=workspace_id,
        name="EGFR",
        target_type=TargetType.SINGLE_PROTEIN,
    )
    defaults.update(kwargs)
    return Target.create(**defaults)


class TestTargetCreation:
    def test_create_sets_fields(self, workspace_id: uuid.UUID) -> None:
        target = _make_target(
            workspace_id,
            name="BRAF V600E",
            target_type=TargetType.SINGLE_PROTEIN,
            organism="Homo sapiens",
            gene_name="BRAF",
            uniprot_id="P15056",
            ncbi_gene_id="673",
            description="Serine/threonine kinase",
            target_class="Kinase",
            sequence="MAALSGGGGGG",
        )

        assert target.workspace_id == workspace_id
        assert target.name == "BRAF V600E"
        assert target.target_type == TargetType.SINGLE_PROTEIN
        assert target.organism == "Homo sapiens"
        assert target.gene_name == "BRAF"
        assert target.uniprot_id == "P15056"
        assert target.ncbi_gene_id == "673"
        assert target.description == "Serine/threonine kinase"
        assert target.target_class == "Kinase"
        assert target.sequence == "MAALSGGGGGG"
        assert target.id is not None

    def test_create_minimal(self, workspace_id: uuid.UUID) -> None:
        target = _make_target(workspace_id)
        assert target.name == "EGFR"
        assert target.target_type == TargetType.SINGLE_PROTEIN
        assert target.organism is None
        assert target.gene_name is None

    def test_empty_name_raises(self, workspace_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="name must not be empty"):
            _make_target(workspace_id, name="")

    def test_whitespace_name_raises(self, workspace_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="name must not be empty"):
            _make_target(workspace_id, name="   ")

    def test_name_is_stripped(self, workspace_id: uuid.UUID) -> None:
        target = _make_target(workspace_id, name="  EGFR  ")
        assert target.name == "EGFR"

    def test_all_target_types(self, workspace_id: uuid.UUID) -> None:
        for tt in TargetType:
            target = _make_target(workspace_id, target_type=tt)
            assert target.target_type == tt


class TestTargetUpdate:
    def test_update_name(self, workspace_id: uuid.UUID) -> None:
        target = _make_target(workspace_id)
        old_updated = target.updated_at
        target.update(name="BRAF")
        assert target.name == "BRAF"
        assert target.updated_at >= old_updated

    def test_update_target_type(self, workspace_id: uuid.UUID) -> None:
        target = _make_target(workspace_id)
        target.update(target_type=TargetType.PROTEIN_COMPLEX)
        assert target.target_type == TargetType.PROTEIN_COMPLEX

    def test_update_empty_name_raises(self, workspace_id: uuid.UUID) -> None:
        target = _make_target(workspace_id)
        with pytest.raises(ValidationError, match="name must not be empty"):
            target.update(name="")

    def test_update_nullable_fields(self, workspace_id: uuid.UUID) -> None:
        target = _make_target(
            workspace_id,
            organism="Homo sapiens",
            gene_name="EGFR",
        )
        target.update(organism=None, gene_name=None)
        assert target.organism is None
        assert target.gene_name is None

    def test_update_preserves_unset_fields(self, workspace_id: uuid.UUID) -> None:
        target = _make_target(
            workspace_id,
            organism="Homo sapiens",
            description="A kinase",
        )
        target.update(name="New Name")
        assert target.organism == "Homo sapiens"
        assert target.description == "A kinase"


class TestTargetMirror:
    def test_from_mirror_uses_supplied_id_and_stores_source_fields(
        self, workspace_id: uuid.UUID
    ) -> None:
        tid = uuid.uuid4()
        t = Target.from_mirror(
            id=tid,
            workspace_id=workspace_id,
            name="  NadD ",
            target_type=TargetType.SINGLE_PROTEIN,
            organism="Mycobacterium tuberculosis",
            chembl_id="CHEMBL4630874",
            source_version=3,
        )
        assert t.id == tid
        assert t.name == "NadD"
        assert t.organism == "Mycobacterium tuberculosis"
        assert t.chembl_id == "CHEMBL4630874"
        assert t.source_version == 3

    def test_from_mirror_rejects_blank_name(self, workspace_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError):
            Target.from_mirror(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                name="  ",
                target_type=TargetType.DOMAIN,
                organism=None,
                chembl_id=None,
                source_version=1,
            )

    def test_new_enum_values_exist(self) -> None:
        assert TargetType("domain") is TargetType.DOMAIN
        assert TargetType("protein_protein_interaction") is TargetType.PROTEIN_PROTEIN_INTERACTION
        assert TargetType("unknown") is TargetType.UNKNOWN
