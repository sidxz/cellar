"""purge_expired_exports — system task that deletes READY files past their TTL."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime

from cellar.application.attachment.storage import StorageClient
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.export.repository import ExportJobRepository


class PurgeExpiredExports:
    """Delete expired export files from storage and transition jobs to EXPIRED.

    Intended to run as a periodic background task (cron / Temporal schedule).
    No auth guard — caller is a system worker, not a user request.
    Returns the count of successfully purged jobs.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        repo: ExportJobRepository,
        storage: StorageClient,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._storage = storage

    async def __call__(self) -> int:
        now = datetime.now(UTC)

        async with self._uow:
            jobs = await self._repo.find_expired_ready(now)

        purged = 0
        for job in jobs:
            if job.file_key:
                # already gone — continue to mark EXPIRED
                with contextlib.suppress(FileNotFoundError):
                    await self._storage.delete(job.file_key)

            async with self._uow:
                fresh = await self._repo.find_by_id_in_workspace(job.workspace_id, job.id)
                if fresh is None:
                    continue  # deleted between list and re-fetch; skip
                fresh.mark_expired()
                await self._repo.save(fresh)
                await self._uow.commit()

            purged += 1

        return purged
