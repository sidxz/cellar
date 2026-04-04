"""UpdateWorkspaceSettings command — partial update of workspace domain config."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.shared.command import Command
from chem_vault.domain.shared.errors import DomainError
from chem_vault.domain.workspace_config.repository import WorkspaceSettingsRepository
from chem_vault.domain.workspace_config.workspace_settings import WorkspaceSettings, _SENTINEL
from chem_vault.application.shared.unit_of_work import UnitOfWork


@dataclass(frozen=True, kw_only=True)
class UpdateWorkspaceSettingsCommand(Command):
    workspace_id: uuid.UUID
    registration_rules: dict | object = _SENTINEL
    custom_field_definitions: dict | object = _SENTINEL
    default_molecule_type: str | None | object = _SENTINEL
    audit_reason_policy: dict | object = _SENTINEL
    signature_required_for: list[str] | object = _SENTINEL
    audit_retention_days: int | None | object = _SENTINEL
    formulation_number_scheme: dict | object = _SENTINEL


class UpdateWorkspaceSettings:
    def __init__(self, uow: UnitOfWork, repo: WorkspaceSettingsRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: UpdateWorkspaceSettingsCommand
    ) -> Result[WorkspaceSettings, DomainError]:
        async with self._uow:
            settings = await self._repo.find_by_id(input.workspace_id)
            if settings is None:
                settings = WorkspaceSettings.create_default(workspace_id=input.workspace_id)

            settings.update(
                registration_rules=input.registration_rules,
                custom_field_definitions=input.custom_field_definitions,
                default_molecule_type=input.default_molecule_type,
                audit_reason_policy=input.audit_reason_policy,
                signature_required_for=input.signature_required_for,
                audit_retention_days=input.audit_retention_days,
                formulation_number_scheme=input.formulation_number_scheme,
            )
            await self._repo.save(settings)
            await self._uow.commit()
            return Success(settings)
