"""Map DomainError subtypes to HTTP responses.

Provides both a FastAPI exception handler (for uncaught domain errors)
and a ``result_to_response`` helper for the railway pattern.
"""

from __future__ import annotations

import math
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from returns.result import Failure, Result, Success

from cellar.domain.shared.errors import (
    AuthorizationError,
    ConcurrencyConflictError,
    ConflictError,
    DataLockedError,
    DomainError,
    GoneError,
    NotFoundError,
    ServiceUnavailableError,
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
    GoneError: 410,
    ServiceUnavailableError: 503,
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
    body.update(error.body_extras())
    return body


def _sanitize_non_finite(value: Any) -> Any:
    """Replace NaN/Infinity floats with their str repr, recursively.

    A rejected-as-invalid NaN/Infinity is echoed back in Pydantic's
    validation error ("input": nan) so the client can see what it sent.
    Starlette's JSONResponse renders with allow_nan=False, so leaving a raw
    non-finite float in the body would crash the *error* response itself.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {k: _sanitize_non_finite(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_non_finite(v) for v in value]
    return value


def register_error_handlers(app: FastAPI) -> None:
    """Install global handlers that convert DomainError / validation failures
    to JSON responses."""

    @app.exception_handler(DomainError)
    async def _domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        status = _error_to_status(exc)
        headers = {}
        if isinstance(exc, ConcurrencyConflictError):
            headers["Retry-After"] = "1"
        return JSONResponse(
            status_code=status,
            content=_error_to_body(exc),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_sanitize_non_finite(jsonable_encoder({"detail": exc.errors()})),
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


def result_or_default(result: Result[Any, DomainError], default: Any) -> Any:
    """Unwrap on Success, return the supplied default on Failure.

    Use for best-effort enrichment paths where a failure is non-fatal and
    must not bubble out as an HTTP error.
    """
    match result:
        case Success(value):
            return value
        case _:
            return default


def result_value_or_error(
    result: Result[Any, DomainError],
) -> tuple[Any, str | None]:
    """Return ``(value, None)`` on Success and ``(None, message)`` on Failure.

    Use in batch endpoints that aggregate per-row outcomes (where a single
    failure should not fail the whole request).
    """
    match result:
        case Success(value):
            return value, None
        case Failure(error):
            return None, getattr(error, "message", str(error))
