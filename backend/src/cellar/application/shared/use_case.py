"""UseCase protocol — the contract every use case implements.

Strict CQRS:
- Commands mutate state and return Result[T, DomainError]
- Queries read state and return Result[T, DomainError]

Both use the same protocol shape for DI simplicity.
"""

from __future__ import annotations

from typing import Protocol, TypeVar

from returns.result import Result

from cellar.domain.shared.errors import DomainError

TInput = TypeVar("TInput", contravariant=True)
TOutput = TypeVar("TOutput", covariant=True)


class UseCase(Protocol[TInput, TOutput]):
    """Protocol for application use cases.

    All use cases are async callables returning Result[T, DomainError].
    The railway pattern ensures expected failures are returned, not raised.
    """

    async def __call__(self, input: TInput) -> Result[TOutput, DomainError]: ...
