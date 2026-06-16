"""AsyncJob — shared base aggregate for async compute jobs.

State machine: pending -> running -> {ready | failed | cancelled};
pending -> cancelled. ready/failed/cancelled are terminal.

Subclasses add their result / cache-key fields and a ``mark_ready`` that calls
``_enter_ready(now)`` then sets those result fields. Transitions mutate in place
and return ``None`` (codebase norm); ``version`` is owned by the repository's
optimistic-concurrency ``save()`` — a transition never touches it.

The aggregate is a mutable ``AggregateRoot`` subclass so job repositories can
reuse the existing ``SQLAlchemyRepository`` base (whose ``save()`` mutates
``aggregate.version``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.shared.errors import DomainError


class AsyncJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


JOB_TERMINAL_STATES = frozenset(
    {AsyncJobStatus.READY, AsyncJobStatus.FAILED, AsyncJobStatus.CANCELLED}
)


class InvalidJobTransition(DomainError):
    """Raised when an async-job state transition violates the lifecycle."""


class AsyncJob(AggregateRoot):
    """Base aggregate for async compute jobs.

    Subclasses add their result / cache-key fields and implement ``mark_ready``
    by calling ``_enter_ready(now)`` first, then setting those result fields.

    State machine::

        pending -> running -> {ready | failed | cancelled}
        pending            ->  cancelled

    ``ready`` / ``failed`` / ``cancelled`` are terminal.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        requested_by: uuid.UUID,
        requested_at: datetime,
        status: AsyncJobStatus = AsyncJobStatus.PENDING,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        self.workspace_id = workspace_id
        self.requested_by = requested_by
        self.requested_at = requested_at
        self.status = status
        self.started_at = started_at
        self.completed_at = completed_at
        self.error_message = error_message

    def mark_running(self, now: datetime) -> None:
        if self.status != AsyncJobStatus.PENDING:
            raise InvalidJobTransition(f"Cannot mark RUNNING from {self.status}")
        self.status = AsyncJobStatus.RUNNING
        self.started_at = now

    def mark_failed(self, error: str, now: datetime) -> None:
        if self.status in JOB_TERMINAL_STATES:
            raise InvalidJobTransition(f"Cannot mark FAILED from {self.status}")
        self.status = AsyncJobStatus.FAILED
        self.completed_at = now
        self.error_message = error

    def mark_cancelled(self, now: datetime) -> None:
        if self.status in JOB_TERMINAL_STATES:
            raise InvalidJobTransition(f"Cannot CANCEL terminal {self.status}")
        self.status = AsyncJobStatus.CANCELLED
        self.completed_at = now

    def _enter_ready(self, now: datetime) -> None:
        """Shared guard + common mutations for the READY transition.

        A subclass ``mark_ready`` calls this first, then sets its result fields.
        """
        if self.status != AsyncJobStatus.RUNNING:
            raise InvalidJobTransition(f"Cannot mark READY from {self.status}")
        self.status = AsyncJobStatus.READY
        self.completed_at = now
