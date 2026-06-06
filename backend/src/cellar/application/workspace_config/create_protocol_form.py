"""CreateProtocolForm command — create a new protocol form template."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_admin, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError
from cellar.domain.workspace_config.protocol_form import (
    ProtocolForm,
    ProtocolFormCondition,
    ProtocolFormOntologyDefault,
    ProtocolFormReadout,
)
from cellar.domain.workspace_config.repository import ProtocolFormRepository


@dataclass(frozen=True, kw_only=True)
class CreateProtocolFormCommand(Command):
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    protocol_type: str | None = None
    is_default: bool = False
    readout_templates: list[dict] = field(default_factory=list)
    condition_templates: list[dict] | None = None
    ontology_defaults: list[dict] | None = None


class CreateProtocolForm:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ProtocolFormRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: CreateProtocolFormCommand, auth: AuthContext | None = None
    ) -> Result[ProtocolForm, DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)

        readouts = [
            ProtocolFormReadout(
                name=r["name"],
                data_type=r["data_type"],
                unit=r.get("unit"),
                aggregation=r.get("aggregation", "none"),
                normalization=r.get("normalization", "none"),
                is_calculated=r.get("is_calculated", False),
                calculation_formula=r.get("calculation_formula"),
                pick_list_values=r.get("pick_list_values"),
                dose_response_config=r.get("dose_response_config"),
            )
            for r in input.readout_templates
        ]

        conditions = None
        if input.condition_templates:
            conditions = [
                ProtocolFormCondition(
                    name=c["name"],
                    data_type=c["data_type"],
                    unit=c.get("unit"),
                    pick_list_values=c.get("pick_list_values"),
                )
                for c in input.condition_templates
            ]

        ontology_defaults = None
        if input.ontology_defaults:
            ontology_defaults = [
                ProtocolFormOntologyDefault(
                    slot_name=o["slot_name"],
                    terms=o.get("terms", []),
                )
                for o in input.ontology_defaults
            ]

        async with self._uow:
            form = ProtocolForm.create(
                workspace_id=input.workspace_id,
                name=input.name,
                description=input.description,
                protocol_type=input.protocol_type,
                is_default=input.is_default,
                readout_templates=readouts,
                condition_templates=conditions,
                ontology_defaults=ontology_defaults,
            )
            await self._repo.save(form)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(form)
