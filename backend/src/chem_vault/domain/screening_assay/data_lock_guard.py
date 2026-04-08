"""DataLockGuard — domain service that prevents writes to locked run data."""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from chem_vault.domain.shared.errors import DataLockedError


@runtime_checkable
class RunLockChecker(Protocol):
    """Port for checking whether a run is locked.

    Implemented by the RunRepository at the infrastructure layer.
    """

    async def is_locked(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> bool: ...


class DataLockGuard:
    """Domain service that guards writes against locked run data.

    Raises ``DataLockedError`` if the run is locked.

    Usage in application layer use cases::

        try:
            await guard.guard_write(workspace_id, run_id)
        except DataLockedError:
            return Failure(exc)
    """

    def __init__(self, lock_checker: RunLockChecker) -> None:
        self._lock_checker = lock_checker

    async def guard_write(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> None:
        """Check if the run is locked; raise DataLockedError if so."""
        locked = await self._lock_checker.is_locked(workspace_id, run_id)
        if locked:
            raise DataLockedError(
                f"Run '{run_id}' is locked — data modifications are not allowed"
            )
