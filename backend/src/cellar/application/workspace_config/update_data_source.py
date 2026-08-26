"""UpdateDataSource command — update name, active status, or entity mappings."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_admin, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.sentinel import UNSET
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError
from cellar.domain.workspace_config.data_source import (
    DataSource,
    EntityMapping,
)
from cellar.domain.workspace_config.repository import DataSourceRepository


@dataclass(frozen=True, kw_only=True)
class UpdateDataSourceCommand(Command):
    workspace_id: uuid.UUID
    data_source_id: uuid.UUID
    name: str | object = UNSET
    is_active: bool | object = UNSET
    config: dict[str, Any] | object = UNSET
    api_key_name: str | object | None = UNSET
    entity_mappings: list[dict[str, Any]] | object = UNSET
    create_batch_on_duplicate: bool | object = UNSET


class UpdateDataSource:
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
        self, input: UpdateDataSourceCommand, auth: AuthContext | None = None
    ) -> Result[DataSource, DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            ds = await self._repo.find_by_id_in_workspace(input.workspace_id, input.data_source_id)
            if ds is None:
                return Failure(NotFoundError("DataSource", str(input.data_source_id)))

            update_kwargs: dict[str, Any] = {}
            if input.name is not UNSET:
                update_kwargs["name"] = input.name
            if input.is_active is not UNSET:
                update_kwargs["is_active"] = input.is_active
            if input.config is not UNSET:
                update_kwargs["config"] = input.config
            if input.api_key_name is not UNSET:
                update_kwargs["api_key_name"] = input.api_key_name
            if input.entity_mappings is not UNSET:
                update_kwargs["entity_mappings"] = _parse_entity_mappings(
                    input.entity_mappings  # type: ignore[arg-type]
                )
            if input.create_batch_on_duplicate is not UNSET:
                # Merge into config without replacing the full config dict.
                # Use the already-staged config (if config was also patched this
                # request) so that a combined PATCH preserves both changes.
                base_config = update_kwargs.get("config", ds.config)
                merged_config = dict(base_config)
                merged_config["create_batch_on_duplicate"] = bool(input.create_batch_on_duplicate)
                update_kwargs["config"] = merged_config

            if update_kwargs:
                ds.update(**update_kwargs)

            await self._repo.save(ds)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(ds)


def _parse_entity_mappings(raw: list[dict[str, Any]]) -> list[EntityMapping]:
    """Convert raw dicts (from API body) to domain value objects."""
    return [EntityMapping.from_dict(em) for em in raw]
