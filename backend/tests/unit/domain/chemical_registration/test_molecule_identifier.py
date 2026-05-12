"""Tests for MoleculeIdentifier owned entity."""

import uuid

import pytest

from cellar.domain.chemical_registration.enums import IdentifierType
from cellar.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from cellar.domain.shared.errors import ValidationError


class TestMoleculeIdentifier:
    def test_create(self) -> None:
        mol_id = uuid.uuid4()
        user_id = uuid.uuid4()
        ident = MoleculeIdentifier.create(
            molecule_id=mol_id,
            identifier="CAS-50-78-2",
            identifier_type=IdentifierType.CAS_NUMBER,
            source="User registration",
            registered_by=user_id,
        )
        assert ident.molecule_id == mol_id
        assert ident.identifier == "CAS-50-78-2"
        assert ident.identifier_type == IdentifierType.CAS_NUMBER
        assert ident.source == "User registration"
        assert ident.registered_by == user_id
        assert ident.id is not None

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

    def test_equality_by_id(self) -> None:
        shared_id = uuid.uuid4()
        a = MoleculeIdentifier(
            id=shared_id,
            molecule_id=uuid.uuid4(),
            identifier="A",
            identifier_type=IdentifierType.CUSTOM,
            source="test",
            registered_by=uuid.uuid4(),
        )
        b = MoleculeIdentifier(
            id=shared_id,
            molecule_id=uuid.uuid4(),
            identifier="B",
            identifier_type=IdentifierType.CUSTOM,
            source="test",
            registered_by=uuid.uuid4(),
        )
        assert a == b

    def test_inequality_by_id(self) -> None:
        a = MoleculeIdentifier.create(
            molecule_id=uuid.uuid4(),
            identifier="A",
            identifier_type=IdentifierType.CUSTOM,
            source="test",
            registered_by=uuid.uuid4(),
        )
        b = MoleculeIdentifier.create(
            molecule_id=uuid.uuid4(),
            identifier="A",
            identifier_type=IdentifierType.CUSTOM,
            source="test",
            registered_by=uuid.uuid4(),
        )
        assert a != b
