"""GetWorkspaceSettings query — retrieve settings or return defaults (no hidden write)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError
from cellar.domain.workspace_config.repository import WorkspaceSettingsRepository
from cellar.domain.workspace_config.workspace_settings import WorkspaceSettings


@dataclass(frozen=True, kw_only=True)
class GetWorkspaceSettingsQuery(Query):
    workspace_id: uuid.UUID


class GetWorkspaceSettings:
    def __init__(self, uow: UnitOfWork, repo: WorkspaceSettingsRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: GetWorkspaceSettingsQuery, auth: AuthContext | None = None
    ) -> Result[WorkspaceSettings, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            settings = await self._repo.find_by_workspace_id(input.workspace_id)
            if settings is None:
                # Return in-memory defaults — no hidden write.
                # Settings are persisted on first explicit PATCH.
                settings = WorkspaceSettings.create_default(workspace_id=input.workspace_id)
            return Success(settings)
