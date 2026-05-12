"""Merge side-effect registry.

External bounded contexts register handlers that are called during a molecule
merge so they can update their own tables (e.g., re-point Batch.molecule_id,
Run result FKs, etc.) within the same transaction.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from cellar.application.shared.unit_of_work import UnitOfWork


class MergeSideEffectHandler(Protocol):
    """Handler that relocates data from source to target molecule.

    Handlers receive the UnitOfWork so they can operate within the same
    transaction as the merge. Infrastructure implementations extract the
    session internally.
    """

    async def on_merge(
        self,
        uow: UnitOfWork,
        source_molecule_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
    ) -> None: ...


class MergeSideEffectRegistry:
    """Collects and executes all registered merge side-effect handlers."""

    def __init__(self, handlers: list[MergeSideEffectHandler] | None = None) -> None:
        self._handlers: list[MergeSideEffectHandler] = list(handlers or [])

    def register(self, handler: MergeSideEffectHandler) -> None:
        """Register a handler to be called on every merge."""
        self._handlers.append(handler)

    async def execute_all(
        self,
        uow: UnitOfWork,
        source_molecule_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
    ) -> None:
        """Execute all registered handlers in order."""
        for handler in self._handlers:
            await handler.on_merge(uow, source_molecule_id, target_molecule_id)
