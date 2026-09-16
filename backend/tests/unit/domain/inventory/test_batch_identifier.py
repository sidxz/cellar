"""Unit tests for BatchIdentifier domain entity."""

from __future__ import annotations

import uuid

import pytest

from cellar.domain.inventory.batch_identifier import BatchIdentifier
from cellar.domain.shared.errors import ValidationError


class TestBatchIdentifierCreate:

    def test_strips_whitespace(self) -> None:
        ident = BatchIdentifier.create(
            batch_id=uuid.uuid4(),
            identifier="  ABC-001  ",
            identifier_type="custom",
            source="user",
            registered_by=uuid.uuid4(),
        )
        assert ident.identifier == "ABC-001"

    def test_rejects_empty_identifier(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            BatchIdentifier.create(
                batch_id=uuid.uuid4(),
                identifier="",
                identifier_type="custom",
                source="user",
                registered_by=uuid.uuid4(),
            )

    def test_rejects_whitespace_only_identifier(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            BatchIdentifier.create(
                batch_id=uuid.uuid4(),
                identifier="   ",
                identifier_type="custom",
                source="user",
                registered_by=uuid.uuid4(),
            )


def test_create_accepts_derived_from_molecule_identifier_id():
    batch_id = uuid.uuid4()
    mol_ident_id = uuid.uuid4()
    actor = uuid.uuid4()

    bi = BatchIdentifier.create(
        batch_id=batch_id,
        identifier="SACC-0036913-001",
        identifier_type="custom",
        source="compound-syn",
        registered_by=actor,
        derived_from_molecule_identifier_id=mol_ident_id,
    )

    assert bi.derived_from_molecule_identifier_id == mol_ident_id

