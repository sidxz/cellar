"""DeleteRelationship command — remove a molecule relationship."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.repository import MoleculeRelationshipRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError


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

        async with self._uow:
            rel = await self._relationship_repo.find_by_id_in_workspace(input.workspace_id, input.relationship_id)
            if rel is None:
                return Failure(
                    NotFoundError("MoleculeRelationship", str(input.relationship_id))
                )

            await self._relationship_repo.delete(input.workspace_id, input.relationship_id)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)

            return Success(None)
