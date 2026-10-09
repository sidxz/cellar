"""Add the shipped default forms a workspace lacks. Never edits existing forms."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_admin, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError
from cellar.domain.workspace_config.default_protocol_forms import BAO, DEFAULT_PROTOCOL_FORMS
from cellar.domain.workspace_config.protocol_form import ProtocolForm, ProtocolFormOntologyDefault
from cellar.domain.workspace_config.repository import (
    ProtocolCategoryRepository,
    ProtocolFormRepository,
)


async def seed_default_forms(
    form_repo: ProtocolFormRepository,
    category_repo: ProtocolCategoryRepository,
    workspace_id: uuid.UUID,
) -> list[ProtocolForm]:
    """Create each shipped form whose category exists and whose name the category lacks."""
    categories = {c.label.lower(): c for c in await category_repo.find_by_workspace(workspace_id)}
    existing = await form_repo.find_by_workspace(workspace_id)
    have = {(f.category_id, f.name.lower()) for f in existing}
    defaults = {f.category_id for f in existing if f.is_default}
    created: list[ProtocolForm] = []
    for spec in DEFAULT_PROTOCOL_FORMS:
        category = categories.get(spec.category.lower())
        if category is None or (category.id, spec.name.lower()) in have:
            continue
        ontology_defaults = (
            [
                ProtocolFormOntologyDefault(
                    slot_name="assay_format",
                    terms=[
                        {
                            "term_id": f"{BAO}{spec.assay_format[0]}",
                            "label": spec.assay_format[1],
                            "ontology_source": "BAO",
                            "uri": f"{BAO}{spec.assay_format[0]}",
                        }
                    ],
                )
            ]
            if spec.assay_format
            else None
        )
        form = ProtocolForm.create(
            workspace_id=workspace_id,
            name=spec.name,
            protocol_type=spec.protocol_type,
            category_id=category.id,
            assay_format_from_target=spec.assay_format_from_target,
            is_default=spec.is_default and category.id not in defaults,
            readout_templates=list(spec.readouts),
            condition_templates=list(spec.conditions) or None,
            ontology_defaults=ontology_defaults,
        )
        await form_repo.save(form)
        created.append(form)
    return created


@dataclass(frozen=True, kw_only=True)
class SeedDefaultProtocolFormsCommand(Command):
    workspace_id: uuid.UUID


class SeedDefaultProtocolForms:
    def __init__(
        self,
        uow: UnitOfWork,
        form_repo: ProtocolFormRepository,
        category_repo: ProtocolCategoryRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._forms = form_repo
        self._categories = category_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: SeedDefaultProtocolFormsCommand, auth: AuthContext | None = None
    ) -> Result[list[ProtocolForm], DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            await seed_default_forms(self._forms, self._categories, input.workspace_id)
            forms = await self._forms.find_by_workspace(input.workspace_id)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(forms)
