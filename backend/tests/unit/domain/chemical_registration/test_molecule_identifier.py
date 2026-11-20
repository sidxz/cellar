"""Tests for MoleculeIdentifier owned entity."""

import uuid

import pytest

from cellar.domain.chemical_registration.enums import IdentifierType
from cellar.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from cellar.domain.shared.errors import ValidationError


class TestMoleculeIdentifier:
    def test_identifier_is_stripped(self) -> None:
        ident = MoleculeIdentifier.create(
            molecule_id=uuid.uuid4(),
            identifier="  CAS-50-78-2  ",
            identifier_type=IdentifierType.CAS_NUMBER,
            source="test",
            registered_by=uuid.uuid4(),
        )
        assert ident.identifier == "CAS-50-78-2"

    def test_empty_identifier_raises(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            MoleculeIdentifier.create(
                molecule_id=uuid.uuid4(),
                identifier="",
                identifier_type=IdentifierType.CAS_NUMBER,
                source="test",
                registered_by=uuid.uuid4(),
            )

    def test_blank_identifier_raises(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            MoleculeIdentifier.create(
                molecule_id=uuid.uuid4(),
                identifier="   ",
                identifier_type=IdentifierType.CAS_NUMBER,
                source="test",
                registered_by=uuid.uuid4(),
            )
