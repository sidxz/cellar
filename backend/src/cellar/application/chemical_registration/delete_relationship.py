"""DeleteRelationship command — remove a molecule relationship."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.repository import MoleculeRelationshipRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class DeleteRelationshipCommand(Command):
    workspace_id: uuid.UUID
    relationship_id: uuid.UUID


class DeleteRelationship:
    """Command use case: delete a molecule relationship by ID."""

    def __init__(
        self,
        uow: UnitOfWork,
        relationship_repo: MoleculeRelationshipRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._relationship_repo = relationship_repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: DeleteRelationshipCommand,
        auth: AuthContext | None = None,
    ) -> Result[None, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            rel = await self._relationship_repo.find_by_id_in_workspace(
                input.workspace_id, input.relationship_id
            )
            if rel is None:
                return Failure(NotFoundError("MoleculeRelationship", str(input.relationship_id)))

            await self._relationship_repo.delete(input.workspace_id, input.relationship_id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)
