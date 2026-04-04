"""Assertion helpers for the railway pattern and domain events."""

from __future__ import annotations

from typing import Any, TypeVar

from returns.result import Failure, Result, Success

from chem_vault.domain.shared.errors import DomainError
from chem_vault.domain.shared.events import DomainEvent

T = TypeVar("T")


def assert_result_ok(result: Result[T, DomainError]) -> T:
    """Assert a Result is Success and return the inner value."""
    assert isinstance(result, Success), (
        f"Expected Success, got Failure: {result.failure()}"
    )
    return result.unwrap()


def assert_result_err(
    result: Result[Any, DomainError],
    error_type: type[DomainError] | None = None,
) -> DomainError:
    """Assert a Result is Failure and return the error.

    Optionally checks the error type.
    """
    assert isinstance(result, Failure), (
        f"Expected Failure, got Success: {result.unwrap()}"
    )
    error = result.failure()
    if error_type is not None:
        assert isinstance(error, error_type), (
            f"Expected {error_type.__name__}, got {type(error).__name__}: {error}"
        )
    return error


def assert_event_emitted(
    events: list[DomainEvent],
    event_type: type[DomainEvent],
    **field_checks: Any,
) -> DomainEvent:
    """Assert that an event of the given type was emitted.

    Optionally checks field values on the event.
    Returns the matched event.
    """
    matches = [e for e in events if isinstance(e, event_type)]
    assert len(matches) > 0, (
        f"No {event_type.__name__} found in {[type(e).__name__ for e in events]}"
    )
    event = matches[0]

    for field, expected in field_checks.items():
        actual = getattr(event, field, _SENTINEL)
        assert actual is not _SENTINEL, (
            f"{event_type.__name__} has no field '{field}'"
        )
        assert actual == expected, (
            f"{event_type.__name__}.{field}: expected {expected!r}, got {actual!r}"
        )

    return event


_SENTINEL = object()
