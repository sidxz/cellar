"""UpdateRun command — update mutable run fields (qc_metrics, notes)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.sentinel import UNSET
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.repository import RunRepository
from cellar.domain.screening_assay.run import Run
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class UpdateRunCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    qc_metrics: dict[str, Any] | None | object = UNSET
    notes: str | None | object = UNSET
    conditions: dict[str, Any] | None | object = UNSET


class UpdateRun:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: RunRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: UpdateRunCommand, auth: AuthContext | None = None
    ) -> Result[Run, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            run = await self._repo.find_by_id_in_workspace(input.workspace_id, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))

            fields: dict[str, Any] = {}
            if input.qc_metrics is not UNSET:
                fields["qc_metrics"] = input.qc_metrics
            if input.notes is not UNSET:
                fields["notes"] = input.notes
            if input.conditions is not UNSET:
                fields["conditions"] = input.conditions

            if fields:
                run.update(**fields)

            await self._repo.save(run)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(run)
