"""ForceFailCddPlateImport command — force a stuck plate import to FAILED."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.inventory.repository import CddPlateImportRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class ForceFailCddPlateImportCommand(Command):
    workspace_id: uuid.UUID
    import_id: uuid.UUID


class ForceFailCddPlateImport:
    """Force a stuck CDD plate import to FAILED status.

    No-op if the import is already in a terminal state.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        repo: CddPlateImportRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: ForceFailCddPlateImportCommand,
        auth: AuthContext | None = None,
    ) -> Result[None, DomainError]:
        require_editor(auth)

        async with self._uow:
            imp = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.import_id
            )
            if imp is None:
                return Failure(NotFoundError("CddPlateImport", str(input.import_id)))

            if imp.status.value in ("completed", "completed_with_errors", "failed"):
                return Success(None)  # Already terminal — no-op

            imp.fail("Force-failed by admin")
            await self._repo.save(imp)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)

        return Success(None)
