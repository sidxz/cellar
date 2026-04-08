"""CreateOntologySlot command — create a new ontology slot definition."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_admin
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.errors import ConflictError, DomainError
from chem_vault.domain.workspace_config.ontology_slot_definition import OntologySlotDefinition
from chem_vault.domain.workspace_config.repository import OntologySlotDefinitionRepository


@dataclass(frozen=True, kw_only=True)
class CreateOntologySlotCommand(Command):
    workspace_id: uuid.UUID
    name: str
    label: str
    ontology_sources: list[str]
    is_required: bool = False
    allow_free_text: bool = True
    display_order: int = 0


class CreateOntologySlot:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: OntologySlotDefinitionRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: CreateOntologySlotCommand, auth: AuthContext | None = None
    ) -> Result[OntologySlotDefinition, DomainError]:
        require_admin(auth)

        async with self._uow:
            existing = await self._repo.find_by_name(input.workspace_id, input.name.strip())
            if existing is not None:
                return Failure(
                    ConflictError(
                        f"Ontology slot with name '{input.name.strip()}' already exists"
                    )
                )

            slot = OntologySlotDefinition.create(
                workspace_id=input.workspace_id,
                name=input.name,
                label=input.label,
                ontology_sources=input.ontology_sources,
                is_required=input.is_required,
                allow_free_text=input.allow_free_text,
                display_order=input.display_order,
            )
            await self._repo.save(slot)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(slot)
