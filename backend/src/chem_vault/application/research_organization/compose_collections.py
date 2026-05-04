"""ComposeCollections — create new collection from boolean set operation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.research_organization.collection import (
    Collection,
    CollectionBooleanOp,
)
from chem_vault.domain.research_organization.repository import CollectionRepository
from chem_vault.domain.shared.errors import DomainError, ValidationError


@dataclass(frozen=True, kw_only=True)
class ComposeCollectionsCommand(Command):
    workspace_id: uuid.UUID
    operation: str
    collection_ids: list[uuid.UUID]
    result_name: str
    created_by: uuid.UUID


class ComposeCollections:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: CollectionRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: ComposeCollectionsCommand, auth: AuthContext | None = None
    ) -> Result[Collection, DomainError]:
        require_editor(auth)
        if len(input.collection_ids) < 2:
            return Failure(ValidationError("At least 2 collections required."))

        try:
            CollectionBooleanOp(input.operation)
        except ValueError:
            return Failure(ValidationError(f"Unknown operation: {input.operation}"))

        async with self._uow:
            molecule_ids = await self._repo.compose_molecule_ids(
                input.workspace_id, input.operation, input.collection_ids
            )

            collection = Collection.create(
                workspace_id=input.workspace_id,
                name=input.result_name,
                created_by=input.created_by,
            )
            await self._repo.save(collection)

            if molecule_ids:
                await self._repo.add_molecules(input.workspace_id, collection.id, molecule_ids)
            collection.molecule_count = len(molecule_ids)

            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(collection)
