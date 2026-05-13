"""DataLockingService — domain service for locking/unlocking runs."""

from __future__ import annotations

import uuid

from cellar.domain.screening_assay.run import Run


class DataLockingService:
    """Domain service that orchestrates run lock/unlock operations.

    Delegates to ``Run.lock()`` / ``Run.unlock()``.  Domain errors
    (``ConflictError``, ``ValidationError``) propagate as exceptions
    — callers in the application layer catch and wrap them in
    ``Failure`` as needed.
    """

    async def lock_run(
        self,
        run: Run,
        *,
        locked_by: uuid.UUID,
        reason: str,
    ) -> Run:
        """Lock a run. Returns the mutated run on success."""
        run.lock(locked_by=locked_by, reason=reason)
        return run

    async def unlock_run(
        self,
        run: Run,
        *,
        unlocked_by: uuid.UUID,
        reason: str,
    ) -> Run:
        """Unlock a run. Returns the mutated run on success."""
        run.unlock(unlocked_by=unlocked_by, reason=reason)
        return run
