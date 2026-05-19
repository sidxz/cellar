"""Unit of Work protocol — application layer abstraction over transactions.

Concrete implementation lives in infrastructure.persistence.unit_of_work.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self

from cellar.application.shared.transaction_context import TransactionContext
from cellar.domain.shared.events import DomainEvent


class UnitOfWork(Protocol):
    """Application-layer protocol for the Unit of Work pattern.

    Use cases depend on this protocol, not on the infrastructure
    implementation (AsyncUnitOfWork).
    """

    @property
    def is_active(self) -> bool: ...

    @property
    def session(self) -> TransactionContext:
        """The active transaction context.

        Accessible within an ``async with uow:`` block. Audit and cascade
        helpers may thread this into ``repo.save_with_session(...)`` calls
        so the participating write rolls back with the surrounding
        transaction. Application use cases should prefer repo abstractions
        over the raw context.

        The concrete return type is ``sqlalchemy.ext.asyncio.AsyncSession``
        (which satisfies ``TransactionContext`` structurally), but the
        application layer must not name that infra type.
        """
        ...

    async def commit(self) -> list[DomainEvent]: ...

    async def rollback(self) -> None: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None: ...
