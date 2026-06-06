"""CreateRun use case."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.enums import PlateFormat, ProtocolStatus, RunRelationshipType
from cellar.domain.screening_assay.repository import (
    PlateTemplateRepository,
    ProtocolRepository,
    RunRepository,
    TargetLinkResult,
)
from cellar.domain.screening_assay.run import Run
from cellar.domain.shared.errors import (
    AuthorizationError,
    ConflictError,
    DomainError,
    NotFoundError,
)


@dataclass(frozen=True, kw_only=True)
class CreateRunCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    run_date: date
    performed_at_org_id: uuid.UUID | None = None
    parent_run_id: uuid.UUID | None = None
    run_relationship_type: str | None = None
    plate_format: str | None = None
    plate_template_id: uuid.UUID | None = None
    conditions: dict[str, Any] | None = None
    notes: str | None = None
    target_ids: list[uuid.UUID] = field(default_factory=list)


class CreateRun:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: RunRepository,
        protocol_repo: ProtocolRepository,
        dispatcher: EventDispatcherProtocol,
        plate_template_repo: PlateTemplateRepository | None = None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._protocol_repo = protocol_repo
        self._dispatcher = dispatcher
        self._plate_template_repo = plate_template_repo

    async def __call__(
        self, input: CreateRunCommand, auth: AuthContext | None = None
    ) -> Result[Run, DomainError]:
        require_editor(auth)
        if auth is None:
            return Failure(AuthorizationError("Authentication required"))

        async with self._uow:
            # Guard: protocol must exist, belong to same workspace, and be ACTIVE
            protocol = await self._protocol_repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            if protocol.status != ProtocolStatus.ACTIVE:
                return Failure(
                    ConflictError(
                        f"Cannot create runs on a {protocol.status.value} protocol — "
                        "only active protocols"
                    )
                )

            # Verify plate template belongs to this workspace
            if input.plate_template_id is not None and self._plate_template_repo is not None:
                template = await self._plate_template_repo.find_by_id_in_workspace(
                    input.workspace_id, input.plate_template_id
                )
                if template is None:
                    return Failure(NotFoundError("PlateTemplate", str(input.plate_template_id)))

            run = Run.create(
                workspace_id=input.workspace_id,
                protocol_id=input.protocol_id,
                run_date=input.run_date,
                operator=auth.user_id,
                performed_at_org_id=input.performed_at_org_id,
                parent_run_id=input.parent_run_id,
                run_relationship_type=(
                    RunRelationshipType(input.run_relationship_type)
                    if input.run_relationship_type
                    else None
                ),
                plate_format=(PlateFormat(input.plate_format) if input.plate_format else None),
                plate_template_id=input.plate_template_id,
                conditions=input.conditions,
                notes=input.notes,
            )
            await self._repo.save(run)
            # Initial run targets — idempotent, workspace-checked in the repo.
            # An unknown/cross-workspace target aborts the create (404) instead
            # of being silently dropped from the new run.
            for target_id in dict.fromkeys(input.target_ids):
                link = await self._repo.add_target(input.workspace_id, run.id, target_id)
                if link is TargetLinkResult.TARGET_NOT_FOUND:
                    return Failure(NotFoundError("Target", str(target_id)))
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(run)
