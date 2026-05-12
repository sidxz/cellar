"""CancelCddMoleculeImport — signal a running CDD molecule import to stop."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.cdd_import.cdd_molecule_import_orchestrator import (
    CddMoleculeImportOrchestrator,
)
from cellar.application.shared.command import Command
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError


@dataclass(frozen=True, kw_only=True)
class CancelCddMoleculeImportCommand(Command):
    workspace_id: uuid.UUID
    workflow_id: str


class CancelCddMoleculeImport:
    """Editor sends a cancel signal to a running CDD molecule import workflow.

    The orchestrator silently no-ops if the workflow is already terminal.
    Workflow ID ownership is verified by prefix before the signal is sent.
    """

    _PREFIX = "cdd-mol-import-"

    def __init__(self, orchestrator: CddMoleculeImportOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def __call__(
        self,
        input: CancelCddMoleculeImportCommand,
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
    """Workflow IDs are ``{prefix}{workspace_uuid}-{random_uuid}``."""
    if not workflow_id.startswith(prefix):
        return False
    remainder = workflow_id[len(prefix) :]
    return len(remainder) >= 37 and remainder[:36] == str(workspace_id)
