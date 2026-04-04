"""DataLockingService — domain service for locking/unlocking runs."""

from __future__ import annotations

import uuid

from returns.result import Failure, Result, Success

from chem_vault.domain.screening_assay.run import Run
from chem_vault.domain.shared.errors import DomainError


class DataLockingService:
    """Domain service that orchestrates run lock/unlock operations.

    Delegates to ``Run.lock()`` / ``Run.unlock()`` and wraps domain
    exceptions in Railway ``Failure`` results.
    """

    async def lock_run(
        self,
        run: Run,
        *,
        locked_by: uuid.UUID,
        reason: str,
    ) -> Result[Run, DomainError]:
        """Lock a run. Returns the mutated run on success."""
        try:
            run.lock(locked_by=locked_by, reason=reason)
        except DomainError as exc:
            return Failure(exc)
        return Success(run)

    async def unlock_run(
        self,
        run: Run,
        *,
        unlocked_by: uuid.UUID,
        reason: str,
    ) -> Result[Run, DomainError]:
        """Unlock a run. Returns the mutated run on success."""
        try:
            run.unlock(unlocked_by=unlocked_by, reason=reason)
        except DomainError as exc:
            return Failure(exc)
        return Success(run)
