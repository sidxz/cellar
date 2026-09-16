"""UpdateWorkspaceSettings command — partial update of workspace domain config."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_admin, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.sentinel import UNSET
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError
from cellar.domain.workspace_config.repository import WorkspaceSettingsRepository
from cellar.domain.workspace_config.workspace_settings import WorkspaceSettings


@dataclass(frozen=True, kw_only=True)
class UpdateWorkspaceSettingsCommand(Command):
    workspace_id: uuid.UUID
    registration_rules: dict[str, Any] | object = UNSET
    custom_field_definitions: list[dict[str, Any]] | object = UNSET
    default_molecule_type: str | object | None = UNSET
    audit_reason_policy: str | object | None = UNSET
    signature_required_for: list[str] | object = UNSET
    audit_retention_days: int | object | None = UNSET
    formulation_number_scheme: str | object | None = UNSET


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
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            settings = await self._repo.find_by_workspace_id(input.workspace_id)
            if settings is None:
                settings = WorkspaceSettings.create_default(workspace_id=input.workspace_id)

            # Build kwargs — only include fields that were provided
            fields: dict[str, Any] = {}
            for key in (
                "registration_rules",
                "custom_field_definitions",
                "default_molecule_type",
                "audit_reason_policy",
                "signature_required_for",
                "audit_retention_days",
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
