"""Tests for MoleculeRelationship standalone entity."""

import uuid

import pytest

from cellar.domain.chemical_registration.enums import RelationshipType
from cellar.domain.chemical_registration.molecule_relationship import MoleculeRelationship
from cellar.domain.shared.errors import ValidationError


class TestMoleculeRelationship:
    def test_create(self) -> None:
        ws_id = uuid.uuid4()
        source_id = uuid.uuid4()
        target_id = uuid.uuid4()
        user_id = uuid.uuid4()
        rel = MoleculeRelationship.create(
            workspace_id=ws_id,
            source_molecule_id=source_id,
            target_molecule_id=target_id,
            relationship_type=RelationshipType.METABOLITE_OF,
            notes="Phase I metabolite",
            created_by=user_id,
        )
        assert rel.workspace_id == ws_id
        assert rel.source_molecule_id == source_id
        assert rel.target_molecule_id == target_id
        assert rel.relationship_type == RelationshipType.METABOLITE_OF
        assert rel.notes == "Phase I metabolite"
        assert rel.created_by == user_id
        assert rel.id is not None

    def test_self_relationship_raises(self) -> None:
        mol_id = uuid.uuid4()
        with pytest.raises(ValidationError, match="relationship with itself"):
            MoleculeRelationship.create(
                workspace_id=uuid.uuid4(),
                source_molecule_id=mol_id,
                target_molecule_id=mol_id,
                relationship_type=RelationshipType.ANALOG_OF,
                created_by=uuid.uuid4(),
            )

    def test_notes_optional(self) -> None:
        rel = MoleculeRelationship.create(
            workspace_id=uuid.uuid4(),
            source_molecule_id=uuid.uuid4(),
            target_molecule_id=uuid.uuid4(),
            relationship_type=RelationshipType.SALT_OF,
            created_by=uuid.uuid4(),
        )
        assert rel.notes is None

    def test_equality_by_id(self) -> None:
        shared_id = uuid.uuid4()
        a = MoleculeRelationship(
            id=shared_id,
            workspace_id=uuid.uuid4(),
            source_molecule_id=uuid.uuid4(),
            target_molecule_id=uuid.uuid4(),
            relationship_type=RelationshipType.ANALOG_OF,
            created_by=uuid.uuid4(),
        )
        b = MoleculeRelationship(
            id=shared_id,
            workspace_id=uuid.uuid4(),
            source_molecule_id=uuid.uuid4(),
            target_molecule_id=uuid.uuid4(),
            relationship_type=RelationshipType.PRODRUG_OF,
            created_by=uuid.uuid4(),
        )
        assert a == b

    def test_all_relationship_types(self) -> None:
        for rt in RelationshipType:
            rel = MoleculeRelationship.create(
                workspace_id=uuid.uuid4(),
                source_molecule_id=uuid.uuid4(),
                target_molecule_id=uuid.uuid4(),
                relationship_type=rt,
                created_by=uuid.uuid4(),
            )
            assert rel.relationship_type == rt
