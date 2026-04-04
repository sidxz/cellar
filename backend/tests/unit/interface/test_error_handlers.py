"""Unit tests for Result→HTTP error mapping."""

from __future__ import annotations

import pytest
from returns.result import Failure, Success

from chem_vault.domain.shared.errors import (
    AuthorizationError,
    ConcurrencyConflictError,
    ConflictError,
    DataLockedError,
    DomainError,
    NotFoundError,
    ValidationError,
)
from chem_vault.interface.error_handlers import (
    _error_to_body,
    _error_to_status,
    result_to_response,
)


class TestErrorToStatus:
    def test_not_found(self) -> None:
        assert _error_to_status(NotFoundError("Molecule")) == 404

    def test_validation(self) -> None:
        assert _error_to_status(ValidationError("bad input")) == 422

    def test_conflict(self) -> None:
        assert _error_to_status(ConflictError("duplicate")) == 409

    def test_concurrency_conflict(self) -> None:
        assert (
            _error_to_status(
                ConcurrencyConflictError("Molecule", "123")
            )
            == 409
        )

    def test_authorization(self) -> None:
        assert _error_to_status(AuthorizationError("forbidden")) == 403

    def test_data_locked(self) -> None:
        assert _error_to_status(DataLockedError("locked")) == 423

    def test_generic_domain_error(self) -> None:
        assert _error_to_status(DomainError("generic")) == 500


class TestErrorToBody:
    def test_basic_error(self) -> None:
        body = _error_to_body(NotFoundError("Molecule", "abc"))
        assert body["error"] == "NotFoundError"
        assert "Molecule" in body["message"]

    def test_error_with_detail(self) -> None:
        body = _error_to_body(
            ValidationError("bad input", detail="field X is invalid")
        )
        assert body["detail"] == "field X is invalid"

    def test_concurrency_error_has_retry(self) -> None:
        body = _error_to_body(
            ConcurrencyConflictError("Molecule", "123")
        )
        assert body["retry"] is True

    def test_error_without_detail_omits_key(self) -> None:
        body = _error_to_body(DomainError("generic"))
        assert "detail" not in body


class TestResultToResponse:
    def test_success_returns_value(self) -> None:
        result = Success({"id": "123"})
        assert result_to_response(result) == {"id": "123"}

    def test_failure_raises_domain_error(self) -> None:
        result = Failure(NotFoundError("Molecule", "abc"))
        with pytest.raises(NotFoundError):
            result_to_response(result)
