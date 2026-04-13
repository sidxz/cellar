"""Async Unit of Work — transaction boundary with domain event collection."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.events import DomainEvent


class AsyncUnitOfWork:
    """Wraps an async SQLAlchemy session with aggregate tracking.

    Usage::

        async with AsyncUnitOfWork(session_factory) as uow:
            repo = SomeRepository(uow)
            aggregate = await repo.find_by_id(some_id)
            aggregate.do_something()
            await repo.save(aggregate)
            events = await uow.commit()
            # dispatch events post-commit
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._tracked_aggregates: list[AggregateRoot] = []

    @property
    def is_active(self) -> bool:
        """True if the UoW context manager has been entered."""
        return self._session is not None

    @property
    def session(self) -> AsyncSession:
        """The active session. Raises if the UoW context is not entered."""
        if self._session is None:
            raise RuntimeError("UnitOfWork is not active. Use as an async context manager.")
        return self._session

    def track(self, aggregate: AggregateRoot) -> None:
        """Register an aggregate for event collection on commit.

        Called automatically by repositories on ``find_by_id`` and ``save``.
        """
        if aggregate not in self._tracked_aggregates:
            self._tracked_aggregates.append(aggregate)

    async def commit(self) -> list[DomainEvent]:
        """Flush, collect events, commit, clear events, return collected events."""
        await self.session.flush()
        events: list[DomainEvent] = []
        for aggregate in self._tracked_aggregates:
            events.extend(aggregate.collect_events())
        await self.session.commit()
        # Only clear after successful commit
        for aggregate in self._tracked_aggregates:
            aggregate.clear_events()
        return events

    async def rollback(self) -> None:
        """Roll back the current transaction."""
        await self.session.rollback()

    async def __aenter__(self) -> AsyncUnitOfWork:
        self._session = self._session_factory()
        self._tracked_aggregates = []
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            await self.rollback()
        if self._session is not None:
            await self._session.close()
        self._session = None
        self._tracked_aggregates = []
