"""Map DomainError subtypes to HTTP responses.

Provides both a FastAPI exception handler (for uncaught domain errors)
and a ``result_to_response`` helper for the railway pattern.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from returns.result import Failure, Result, Success

from chem_vault.domain.shared.errors import (
    AuthorizationError,
    ConcurrencyConflictError,
    ConflictError,
    DataLockedError,
    DomainError,
    NotFoundError,
    ValidationError,
)

# Map each error type to an HTTP status code
_ERROR_STATUS_MAP: dict[type[DomainError], int] = {
    NotFoundError: 404,
    ValidationError: 422,
    ConflictError: 409,
    ConcurrencyConflictError: 409,
    AuthorizationError: 403,
    DataLockedError: 423,
}


def _error_to_status(error: DomainError) -> int:
    """Resolve the HTTP status code for a domain error."""
    for error_type, status in _ERROR_STATUS_MAP.items():
        if isinstance(error, error_type):
            return status
    return 500


def _error_to_body(error: DomainError) -> dict[str, Any]:
    """Build a JSON error body from a domain error."""
    body: dict[str, Any] = {
        "error": type(error).__name__,
        "message": error.message,
    }
    if error.detail:
        body["detail"] = error.detail
    if isinstance(error, ConcurrencyConflictError):
        body["retry"] = True
    return body


def register_error_handlers(app: FastAPI) -> None:
    """Install a global handler that converts DomainError to JSON responses."""

    @app.exception_handler(DomainError)
    async def _domain_error_handler(
        request: Request, exc: DomainError
    ) -> JSONResponse:
        status = _error_to_status(exc)
        headers = {}
        if isinstance(exc, ConcurrencyConflictError):
            headers["Retry-After"] = "1"
        return JSONResponse(
            status_code=status,
            content=_error_to_body(exc),
            headers=headers,
        )


def result_to_response(
    result: Result[Any, DomainError],
) -> Any:
    """Convert a Result to an HTTP response.

    Success -> return the value (FastAPI serializes it)
    Failure -> raise the DomainError (caught by the exception handler)
    """
    match result:
        case Success(value):
            return value
        case Failure(error):
            raise error
