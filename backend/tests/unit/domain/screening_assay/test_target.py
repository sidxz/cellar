"""Tests for Target entity (read-only mirror of prot-cellar)."""

import uuid

import pytest

from cellar.domain.screening_assay.enums import TargetType
from cellar.domain.screening_assay.target import Target
from cellar.domain.shared.errors import ValidationError


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


def _mirror(workspace_id: uuid.UUID, **overrides) -> Target:
    kwargs = dict(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        name="NadD",
        target_type=TargetType.SINGLE_PROTEIN,
        organism="Mycobacterium tuberculosis",
        chembl_id=None,
        source_version=1,
    )
    kwargs.update(overrides)
    return Target.from_mirror(**kwargs)


class TestTargetMirror:
    def test_from_mirror_uses_supplied_id_and_stores_source_fields(
        self, workspace_id: uuid.UUID
    ) -> None:
        tid = uuid.uuid4()
        t = _mirror(
            workspace_id, id=tid, name="  NadD ", chembl_id="CHEMBL4630874", source_version=3
        )
        assert t.id == tid
        assert t.workspace_id == workspace_id
        assert t.name == "NadD"
        assert t.target_type is TargetType.SINGLE_PROTEIN
        assert t.organism == "Mycobacterium tuberculosis"
        assert t.chembl_id == "CHEMBL4630874"
        assert t.source_version == 3

    def test_from_mirror_rejects_blank_name(self, workspace_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError):
            _mirror(workspace_id, name="  ")

    def test_no_local_mutation_api(self) -> None:
        # The catalog is owned by prot-cellar — no create/update on the mirror.
        assert not hasattr(Target, "create")
        assert not hasattr(Target, "update")

    def test_new_enum_values_exist(self) -> None:
        assert TargetType("domain") is TargetType.DOMAIN
        assert TargetType("protein_protein_interaction") is TargetType.PROTEIN_PROTEIN_INTERACTION
        assert TargetType("unknown") is TargetType.UNKNOWN

    def test_identity_equality(self, workspace_id: uuid.UUID) -> None:
        tid = uuid.uuid4()
        assert _mirror(workspace_id, id=tid) == _mirror(workspace_id, id=tid, name="Other")
        assert _mirror(workspace_id) != _mirror(workspace_id)
