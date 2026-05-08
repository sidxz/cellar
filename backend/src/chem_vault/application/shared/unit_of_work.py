"""Unit of Work protocol — application layer abstraction over transactions.

Concrete implementation lives in infrastructure.persistence.unit_of_work.
"""

from __future__ import annotations

from types import TracebackType
from typing import TYPE_CHECKING, Protocol, Self

from chem_vault.domain.shared.events import DomainEvent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class UnitOfWork(Protocol):
    """Application-layer protocol for the Unit of Work pattern.

    Use cases depend on this protocol, not on the infrastructure
    implementation (AsyncUnitOfWork).
    """

    @property
    def is_active(self) -> bool: ...

    @property
    def session(self) -> "AsyncSession":
        """The active SQLAlchemy session.

        Accessible within an ``async with uow:`` block.  Infrastructure
        code (e.g. CascadeService implementations) may use this to pass
        the session to SQLAlchemy-level helpers.  Application-layer use
        cases should prefer repo/service abstractions over raw sessions.
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
