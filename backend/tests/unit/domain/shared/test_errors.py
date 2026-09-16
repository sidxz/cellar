"""Tests for domain error hierarchy."""


from cellar.domain.shared.errors import (
    NotFoundError,
)



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
