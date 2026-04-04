"""DataLockGuard — domain service that prevents writes to locked run data."""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from returns.result import Failure, Result, Success

from chem_vault.domain.shared.errors import DataLockedError, DomainError


@runtime_checkable
class RunLockChecker(Protocol):
    """Port for checking whether a run is locked.

    Implemented by the RunRepository at the infrastructure layer.
    """

    async def is_locked(self, run_id: uuid.UUID) -> bool: ...


class DataLockGuard:
    """Domain service that guards writes against locked run data.

    Usage in application layer use cases:
        result = await guard.guard_write(run_id)
        if isinstance(result, Failure):
            return result
        # ... proceed with write
    """

    def __init__(self, lock_checker: RunLockChecker) -> None:
        self._lock_checker = lock_checker

    async def guard_write(self, run_id: uuid.UUID) -> Result[None, DomainError]:
        """Check if the run is locked; return Failure if so."""
        locked = await self._lock_checker.is_locked(run_id)
        if locked:
            return Failure(
                DataLockedError(
                    f"Run '{run_id}' is locked — data modifications are not allowed"
                )
            )
        return Success(None)
