"""UpdateWorkspaceSettings command — partial update of workspace domain config."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.auth import AuthContext, require_admin
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.sentinel import UNSET
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.errors import DomainError
from chem_vault.domain.workspace_config.repository import WorkspaceSettingsRepository
from chem_vault.domain.workspace_config.workspace_settings import WorkspaceSettings


@dataclass(frozen=True, kw_only=True)
class UpdateWorkspaceSettingsCommand(Command):
    workspace_id: uuid.UUID
    registration_rules: dict | object = UNSET
    custom_field_definitions: dict | object = UNSET
    default_molecule_type: str | None | object = UNSET
    audit_reason_policy: dict | object = UNSET
    signature_required_for: list[str] | object = UNSET
    audit_retention_days: int | None | object = UNSET
    formulation_number_scheme: dict | object = UNSET


class UpdateWorkspaceSettings:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: WorkspaceSettingsRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: UpdateWorkspaceSettingsCommand, auth: AuthContext | None = None
    ) -> Result[WorkspaceSettings, DomainError]:
        require_admin(auth)

        async with self._uow:
            settings = await self._repo.find_by_id(input.workspace_id)
            if settings is None:
                settings = WorkspaceSettings.create_default(workspace_id=input.workspace_id)

            # Build kwargs — only include fields that were provided
            fields: dict[str, object] = {}
            for key in (
                "registration_rules", "custom_field_definitions", "default_molecule_type",
                "audit_reason_policy", "signature_required_for", "audit_retention_days",
                "formulation_number_scheme",
            ):
                val = getattr(input, key)
                if val is not UNSET:
                    fields[key] = val

            if fields:
                settings.update(**fields)
            await self._repo.save(settings)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(settings)
