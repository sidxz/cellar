"""Set the workspace's home organisms: their targets are named without an organism prefix."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_admin, require_same_workspace
from cellar.application.screening.protocol_naming_service import ProtocolNameService
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.application.workspace_config.naming_changes import (
    apply_naming_change,
    compute_naming_change,
    plan_home_organism,
    refuse_collisions,
)
from cellar.domain.screening_assay.repository import ProtocolRepository
from cellar.domain.shared.errors import DomainError
from cellar.domain.workspace_config.repository import WorkspaceSettingsRepository
from cellar.domain.workspace_config.workspace_settings import WorkspaceSettings


@dataclass(frozen=True, kw_only=True)
class SetHomeOrganismCommand(Command):
    workspace_id: uuid.UUID
    terms: list[dict[str, Any]]  # [{term_id, label, ontology_source}]; empty clears them


class SetHomeOrganism:
    def __init__(
        self,
        uow: UnitOfWork,
        settings_repo: WorkspaceSettingsRepository,
        dispatcher: EventDispatcherProtocol,
        *,
        protocol_repo: ProtocolRepository,
        names: ProtocolNameService,
    ) -> None:
        self._uow = uow
        self._settings = settings_repo
        self._dispatcher = dispatcher
        self._protocols = protocol_repo
        self._names = names

    async def __call__(
        self, input: SetHomeOrganismCommand, auth: AuthContext | None = None
    ) -> Result[WorkspaceSettings, DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            settings = await self._settings.find_by_workspace_id(input.workspace_id)
            if settings is None:
                settings = WorkspaceSettings.create_default(workspace_id=input.workspace_id)
            settings.set_home_organisms(input.terms)
            plan = await plan_home_organism(
                workspace_id=input.workspace_id,
                protocol_repo=self._protocols,
                names=self._names,
                terms=settings.home_organisms,
            )
            preview = await compute_naming_change(
                workspace_id=input.workspace_id,
                protocol_repo=self._protocols,
                names=self._names,
                plan=plan,
            )
            refused = refuse_collisions(preview)
            if isinstance(refused, Failure):
                return refused
            await apply_naming_change(
                protocol_repo=self._protocols,
                names=self._names,
                plan=plan,
                preview=preview,
                reason="Home organism changed",
                user_id=auth.user_id if auth else None,
            )
            await self._settings.save(settings)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(settings)
