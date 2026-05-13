"""CreateDataSource command — link a new external data source."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_admin
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import ConflictError, DomainError
from cellar.domain.workspace_config.data_source import DataSource, DataSourceType
from cellar.domain.workspace_config.repository import DataSourceRepository


@dataclass(frozen=True, kw_only=True)
class CreateDataSourceCommand(Command):
    workspace_id: uuid.UUID
    name: str
    source_type: str
    config: dict[str, Any] = field(default_factory=dict)
    api_key_name: str | None = None


class CreateDataSource:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: DataSourceRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: CreateDataSourceCommand, auth: AuthContext | None = None
    ) -> Result[DataSource, DomainError]:
        require_admin(auth)

        async with self._uow:
            existing = await self._repo.find_by_name(input.workspace_id, input.name.strip())
            if existing is not None:
                return Failure(
                    ConflictError(f"Data source with name '{input.name.strip()}' already exists")
                )

            created_by = auth.user_id if auth else uuid.UUID(int=0)

            if input.source_type == DataSourceType.CDD_VAULT:
                ds = DataSource.create_cdd_vault(
                    workspace_id=input.workspace_id,
                    name=input.name,
                    vault_id=input.config.get("vault_id", ""),
                    api_key_name=input.api_key_name or "",
                    created_by=created_by,
                )
            elif input.source_type == DataSourceType.CHEMBL:
                ds = DataSource.create_chembl(
                    workspace_id=input.workspace_id,
                    name=input.name,
                    created_by=created_by,
                )
            else:
                ds = DataSource.create(
                    workspace_id=input.workspace_id,
                    name=input.name,
                    source_type=input.source_type,
                    config=input.config,
                    api_key_name=input.api_key_name,
                    created_by=created_by,
                )

            await self._repo.save(ds)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(ds)
