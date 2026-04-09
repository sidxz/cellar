"""Result unwrapping helpers for idempotent loading."""

from __future__ import annotations

from returns.result import Failure, Result


def unwrap(result: Result, label: str, key: str) -> object:
    """Unwrap a Result or raise with context."""
    if isinstance(result, Failure):
        raise RuntimeError(f"Failed to create {label} '{key}': {result.failure()}")
    return result.unwrap()


def unwrap_or_skip(result: Result, label: str, key: str) -> object | None:
    """Unwrap a Result, return None for conflict/duplicate errors (idempotency)."""
    if isinstance(result, Failure):
        err = result.failure()
        err_str = str(err).lower()
        err_type = type(err).__name__
        if "already exists" in err_str or "conflict" in err_type.lower() or "duplicate" in err_str:
            return None
        raise RuntimeError(f"Failed to create {label} '{key}': {err}")
    return result.unwrap()


async def try_create(coro, label: str, key: str):
    """Await a coroutine, return None on IntegrityError (idempotent skip)."""
    try:
        result = await coro
        return unwrap_or_skip(result, label, key)
    except Exception as exc:
        exc_str = str(exc).lower()
        if "unique" in exc_str or "duplicate" in exc_str or "integrity" in exc_str:
            return None
        raise
