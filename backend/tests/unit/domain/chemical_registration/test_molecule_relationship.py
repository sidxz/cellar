"""Tests for MoleculeRelationship standalone entity."""

import uuid

import pytest

from cellar.domain.chemical_registration.enums import RelationshipType
from cellar.domain.chemical_registration.molecule_relationship import MoleculeRelationship
from cellar.domain.shared.errors import ValidationError


class TestMoleculeRelationship:
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
