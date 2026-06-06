"""UpdateProtocolForm command — update a protocol form template."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_admin, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.sentinel import UNSET
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError
from cellar.domain.workspace_config.protocol_form import (
    ProtocolForm,
    ProtocolFormCondition,
    ProtocolFormOntologyDefault,
    ProtocolFormReadout,
)
from cellar.domain.workspace_config.repository import ProtocolFormRepository


@dataclass(frozen=True, kw_only=True)
class UpdateProtocolFormCommand(Command):
    workspace_id: uuid.UUID
    form_id: uuid.UUID
    name: str | object = UNSET
    description: str | None | object = UNSET
    protocol_type: str | None | object = UNSET
    is_default: bool | object = UNSET
    readout_templates: list[dict] | None | object = UNSET
    condition_templates: list[dict] | None | object = UNSET
    ontology_defaults: list[dict] | None | object = UNSET


class UpdateProtocolForm:
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
        self, input: UpdateProtocolFormCommand, auth: AuthContext | None = None
    ) -> Result[ProtocolForm, DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            form = await self._repo.find_by_id_in_workspace(input.workspace_id, input.form_id)
            if form is None:
                return Failure(NotFoundError("ProtocolForm", str(input.form_id)))

            update_kwargs: dict = {}

            if input.name is not UNSET:
                update_kwargs["name"] = input.name
            if input.description is not UNSET:
                update_kwargs["description"] = input.description
            if input.protocol_type is not UNSET:
                update_kwargs["protocol_type"] = input.protocol_type
            if input.is_default is not UNSET:
                update_kwargs["is_default"] = input.is_default

            if input.readout_templates is not UNSET:
                if input.readout_templates:
                    update_kwargs["readout_templates"] = [
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
                else:
                    update_kwargs["readout_templates"] = None

            if input.condition_templates is not UNSET:
                if input.condition_templates:
                    update_kwargs["condition_templates"] = [
                        ProtocolFormCondition(
                            name=c["name"],
                            data_type=c["data_type"],
                            unit=c.get("unit"),
                            pick_list_values=c.get("pick_list_values"),
                        )
                        for c in input.condition_templates
                    ]
                else:
                    update_kwargs["condition_templates"] = None

            if input.ontology_defaults is not UNSET:
                if input.ontology_defaults:
                    update_kwargs["ontology_defaults"] = [
                        ProtocolFormOntologyDefault(
                            slot_name=o["slot_name"],
                            terms=o.get("terms", []),
                        )
                        for o in input.ontology_defaults
                    ]
                else:
                    update_kwargs["ontology_defaults"] = None

            if update_kwargs:
                form.update(**update_kwargs)

            await self._repo.save(form)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(form)
