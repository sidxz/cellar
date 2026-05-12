"""Tests for domain error hierarchy."""

import pytest

from cellar.domain.shared.errors import (
    AuthorizationError,
    ConcurrencyConflictError,
    ConflictError,
    DataLockedError,
    DomainError,
    NotFoundError,
    ValidationError,
)


class TestDomainError:
    def test_message(self) -> None:
        err = DomainError("something failed")
        assert err.message == "something failed"
        assert str(err) == "something failed"

    def test_detail(self) -> None:
        err = DomainError("failed", detail="extra info")
        assert err.detail == "extra info"

    def test_detail_defaults_none(self) -> None:
        assert DomainError("x").detail is None


class TestNotFoundError:
    def test_without_id(self) -> None:
        err = NotFoundError("Molecule")
        assert err.entity_type == "Molecule"
        assert err.entity_id is None
        assert "Molecule not found" in str(err)

    def test_with_id(self) -> None:
        err = NotFoundError("Molecule", "abc-123")
        assert err.entity_id == "abc-123"
        assert "Molecule 'abc-123' not found" in str(err)

    def test_is_domain_error(self) -> None:
        assert isinstance(NotFoundError("X"), DomainError)


class TestConcurrencyConflictError:
    def test_message(self) -> None:
        err = ConcurrencyConflictError("Molecule", "abc")
        assert "Concurrency conflict" in str(err)
        assert err.entity_type == "Molecule"
        assert err.entity_id == "abc"

    def test_is_domain_error(self) -> None:
        assert isinstance(ConcurrencyConflictError("X", "1"), DomainError)


class TestHierarchy:
    """All error types are subclasses of DomainError."""

    @pytest.mark.parametrize(
        "cls",
        [
            NotFoundError,
            ConflictError,
            ConcurrencyConflictError,
            ValidationError,
            AuthorizationError,
            DataLockedError,
        ],
    )
    def test_subclass(self, cls: type) -> None:
        assert issubclass(cls, DomainError)
