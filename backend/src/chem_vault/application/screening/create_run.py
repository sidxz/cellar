"""CreateRun use case."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from returns.result import Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.enums import PlateFormat, ProtocolStatus, RunRelationshipType
from chem_vault.domain.screening_assay.repository import ProtocolRepository, RunRepository
from chem_vault.domain.screening_assay.run import Run
from chem_vault.domain.shared.errors import ConflictError, DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class CreateRunCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    run_date: date
    performed_at_org_id: uuid.UUID | None = None
    parent_run_id: uuid.UUID | None = None
    run_relationship_type: str | None = None
    plate_format: str | None = None
    conditions: dict[str, Any] | None = None
    notes: str | None = None


class CreateRun:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: RunRepository,
        protocol_repo: ProtocolRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._protocol_repo = protocol_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: CreateRunCommand, auth: AuthContext | None = None
    ) -> Result[Run, DomainError]:
        require_editor(auth)

        async with self._uow:
            # Guard: protocol must exist and be ACTIVE
            protocol = await self._protocol_repo.find_by_id(input.protocol_id)
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))
            if protocol.status != ProtocolStatus.ACTIVE:
                return Failure(
                    ConflictError(
                        f"Cannot create runs on a {protocol.status.value} protocol — only active protocols"
                    )
                )

            run = Run.create(
                workspace_id=input.workspace_id,
                protocol_id=input.protocol_id,
                run_date=input.run_date,
                operator=auth.user_id if auth else uuid.uuid4(),
                performed_at_org_id=input.performed_at_org_id,
                parent_run_id=input.parent_run_id,
                run_relationship_type=(
                    RunRelationshipType(input.run_relationship_type)
                    if input.run_relationship_type
                    else None
                ),
                plate_format=(
                    PlateFormat(input.plate_format) if input.plate_format else None
                ),
                conditions=input.conditions,
                notes=input.notes,
            )
            await self._repo.save(run)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(run)
