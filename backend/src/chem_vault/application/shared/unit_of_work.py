"""Unit of Work protocol — application layer abstraction over transactions.

Concrete implementation lives in infrastructure.persistence.unit_of_work.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self

from chem_vault.domain.shared.events import DomainEvent


class UnitOfWork(Protocol):
    """Application-layer protocol for the Unit of Work pattern.

    Use cases depend on this protocol, not on the infrastructure
    implementation (AsyncUnitOfWork).
    """

    @property
    def is_active(self) -> bool: ...

    async def commit(self) -> list[DomainEvent]: ...

    async def rollback(self) -> None: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None: ...
