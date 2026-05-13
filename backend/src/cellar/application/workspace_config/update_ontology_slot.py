"""UpdateOntologySlot command — update an ontology slot definition."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_admin
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.sentinel import UNSET
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError
from cellar.domain.workspace_config.ontology_slot_definition import OntologySlotDefinition
from cellar.domain.workspace_config.repository import OntologySlotDefinitionRepository


@dataclass(frozen=True, kw_only=True)
class UpdateOntologySlotCommand(Command):
    workspace_id: uuid.UUID
    slot_id: uuid.UUID
    label: str | object = UNSET
    ontology_sources: list[str] | object = UNSET
    root_concept_id: str | None | object = UNSET
    is_required: bool | object = UNSET
    allow_free_text: bool | object = UNSET
    display_order: int | object = UNSET


class UpdateOntologySlot:
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
        self, input: UpdateOntologySlotCommand, auth: AuthContext | None = None
    ) -> Result[OntologySlotDefinition, DomainError]:
        require_admin(auth)

        async with self._uow:
            slot = await self._repo.find_by_id_in_workspace(input.workspace_id, input.slot_id)
            if slot is None:
                return Failure(NotFoundError("OntologySlotDefinition", str(input.slot_id)))

            update_kwargs: dict = {}
            for attr in (
                "label",
                "ontology_sources",
                "root_concept_id",
                "is_required",
                "allow_free_text",
                "display_order",
            ):
                val = getattr(input, attr)
                if val is not UNSET:
                    update_kwargs[attr] = val

            if update_kwargs:
                slot.update(**update_kwargs)

            await self._repo.save(slot)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(slot)
