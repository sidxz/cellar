"""Unit tests for BatchIdentifier domain entity."""

from __future__ import annotations

import uuid

import pytest

from cellar.domain.inventory.batch_identifier import BatchIdentifier
from cellar.domain.shared.errors import ValidationError


class TestBatchIdentifierCreate:
    def test_creates_with_required_fields(self) -> None:
        batch_id = uuid.uuid4()
        user_id = uuid.uuid4()
        ident = BatchIdentifier.create(
            batch_id=batch_id,
            identifier="SACC-009999-001",
            identifier_type="external_lot",
            source="CDD Vault sync",
            registered_by=user_id,
        )
        assert ident.batch_id == batch_id
        assert ident.identifier == "SACC-009999-001"
        assert ident.identifier_type == "external_lot"
        assert ident.source == "CDD Vault sync"
        assert ident.registered_by == user_id

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
