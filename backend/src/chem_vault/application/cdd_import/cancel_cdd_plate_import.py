"""CancelCddPlateImport — signal a running CDD plate import to stop."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.cdd_import.cdd_plate_import_orchestrator import (
    CddPlateImportOrchestrator,
)
from chem_vault.application.shared.command import Command
from chem_vault.domain.shared.errors import DomainError, NotFoundError, ValidationError


@dataclass(frozen=True, kw_only=True)
class CancelCddPlateImportCommand(Command):
    workspace_id: uuid.UUID
    workflow_id: str


class CancelCddPlateImport:
    _PREFIX = "cdd-plate-import-"

    def __init__(self, orchestrator: CddPlateImportOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def __call__(
        self,
        input: CancelCddPlateImportCommand,
        auth: AuthContext | None = None,
    ) -> Result[None, DomainError]:
        require_editor(auth)

        if not _matches_workspace(input.workflow_id, input.workspace_id, self._PREFIX):
            return Failure(NotFoundError("Workflow", input.workflow_id))

        try:
            await self._orchestrator.cancel(input.workflow_id)
        except ValidationError as exc:
            return Failure(exc)
        return Success(None)


def _matches_workspace(workflow_id: str, workspace_id: uuid.UUID, prefix: str) -> bool:
    if not workflow_id.startswith(prefix):
        return False
    remainder = workflow_id[len(prefix):]
    return len(remainder) >= 37 and remainder[:36] == str(workspace_id)
