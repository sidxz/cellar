"""CreateRelationship command — link two molecules with a semantic relationship."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.enums import RelationshipType
from cellar.domain.chemical_registration.molecule_relationship import MoleculeRelationship
from cellar.domain.chemical_registration.repository import (
    MoleculeRelationshipRepository,
    MoleculeRepository,
)
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError


@dataclass(frozen=True, kw_only=True)
class CreateRelationshipCommand(Command):
    workspace_id: uuid.UUID
    source_molecule_id: uuid.UUID
    target_molecule_id: uuid.UUID
    relationship_type: str
    notes: str | None = None
    created_by: uuid.UUID


class CreateRelationship:
    """Command use case: create a semantic relationship between two molecules."""

    def __init__(
        self,
        uow: UnitOfWork,
        molecule_repo: MoleculeRepository,
        relationship_repo: MoleculeRelationshipRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._molecule_repo = molecule_repo
        self._relationship_repo = relationship_repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: CreateRelationshipCommand,
        auth: AuthContext | None = None,
    ) -> Result[MoleculeRelationship, DomainError]:
        require_editor(auth)

        # Validate relationship_type enum
        try:
            rel_type = RelationshipType(input.relationship_type)
        except ValueError:
            return Failure(
                ValidationError(
                    f"Invalid relationship_type '{input.relationship_type}'. "
                    f"Must be one of: {', '.join(t.value for t in RelationshipType)}"
                )
            )

        async with self._uow:
            # Validate both molecules exist in workspace
            source = await self._molecule_repo.find_by_id_in_workspace(
                input.workspace_id, input.source_molecule_id
            )
            if source is None:
                return Failure(NotFoundError("Molecule", str(input.source_molecule_id)))

            target = await self._molecule_repo.find_by_id_in_workspace(
                input.workspace_id, input.target_molecule_id
            )
            if target is None:
                return Failure(NotFoundError("Molecule", str(input.target_molecule_id)))

            # Domain invariant: no self-relationships (enforced by MoleculeRelationship.__init__)
            rel = MoleculeRelationship.create(
                workspace_id=input.workspace_id,
                source_molecule_id=input.source_molecule_id,
                target_molecule_id=input.target_molecule_id,
                relationship_type=rel_type,
                notes=input.notes,
                created_by=input.created_by,
            )

            await self._relationship_repo.save(rel)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(rel)
