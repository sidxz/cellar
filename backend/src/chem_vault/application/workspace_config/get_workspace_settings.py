"""GetWorkspaceSettings query — retrieve settings or return defaults (no hidden write)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.errors import DomainError
from chem_vault.domain.workspace_config.repository import WorkspaceSettingsRepository
from chem_vault.domain.workspace_config.workspace_settings import WorkspaceSettings


@dataclass(frozen=True, kw_only=True)
class GetWorkspaceSettingsQuery(Query):
    workspace_id: uuid.UUID


class GetWorkspaceSettings:
    def __init__(self, uow: UnitOfWork, repo: WorkspaceSettingsRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetWorkspaceSettingsQuery
    ) -> Result[WorkspaceSettings, DomainError]:
        async with self._uow:
            settings = await self._repo.find_by_workspace_id(input.workspace_id)
            if settings is None:
                # Return in-memory defaults — no hidden write.
                # Settings are persisted on first explicit PATCH.
                settings = WorkspaceSettings.create_default(workspace_id=input.workspace_id)
            return Success(settings)
