"""ResumeCddMoleculeImport command — start a failed import again from where it stopped."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.cdd_import.cdd_molecule_import_orchestrator import (
    CddMoleculeImportOrchestrator,
    ResumeCddMoleculeImportRequest,
)
from cellar.application.cdd_import.start_cdd_molecule_import import (
    StartCddMoleculeImportResult,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.cdd_molecule_import import (
    TERMINAL_STATUSES,
    CddMoleculeImport,
)
from cellar.domain.chemical_registration.enums import CddMoleculeImportStatus
from cellar.domain.chemical_registration.repository import CddMoleculeImportRepository
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError


@dataclass(frozen=True, kw_only=True)
class ResumeCddMoleculeImportCommand(Command):
    workspace_id: uuid.UUID
    import_id: uuid.UUID
    resumed_by: uuid.UUID


class ResumeCddMoleculeImport:
    """Pick a failed import up at its last saved offset, on the export already on disk.

    The run restarts with the settings it started with, not the data source's current
    ones. The workflow starts before the record changes, so a resume that cannot start
    leaves the import failed; a record that then cannot be saved cancels that run.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        repo: CddMoleculeImportRepository,
        orchestrator: CddMoleculeImportOrchestrator,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._orchestrator = orchestrator
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: ResumeCddMoleculeImportCommand,
        auth: AuthContext | None = None,
    ) -> Result[StartCddMoleculeImportResult, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            imp = await self._repo.find_by_id_in_workspace(input.workspace_id, input.import_id)
            if imp is None:
                return Failure(NotFoundError("CddMoleculeImport", str(input.import_id)))
            others = await self._repo.find_by_workspace(input.workspace_id)
        refusal = _refusal(imp, others)
        if refusal is not None:
            return Failure(ValidationError(refusal))

        # A failed record's workflow can still be running: Force Stop only marks the
        # record. Left alone it would carry on beside the resume once the record reopens.
        if imp.workflow_id:
            await self._orchestrator.terminate(imp.workflow_id, "Superseded by a resume")
        try:
            workflow_id = await self._orchestrator.resume(
                _request(imp, input.resumed_by, auth.org_id if auth else None)
            )
        except DomainError as exc:
            return Failure(exc)

        try:
            async with self._uow:
                again = await self._repo.find_by_id_in_workspace(
                    input.workspace_id, input.import_id
                )
                if again is None:
                    raise NotFoundError("CddMoleculeImport", str(input.import_id))
                again.resume(workflow_id, input.resumed_by)
                await self._repo.save(again)
                events = await self._uow.commit()
        except Exception:
            # The run has started but the import does not say so: stop it rather than
            # let it register rows under a record that is still failed. Terminated, not
            # cancelled: a cancelled run would try to fail the failed record, retry that
            # forever, and keep this resume's workflow id taken.
            await self._orchestrator.terminate(workflow_id, "The import could not be reopened")
            raise

        await self._dispatcher.dispatch_all(events)
        return Success(StartCddMoleculeImportResult(workflow_id=workflow_id))


def _refusal(imp: CddMoleculeImport, imports: list[CddMoleculeImport]) -> str | None:
    if any(o.id != imp.id and o.status.value not in TERMINAL_STATUSES for o in imports):
        return "Another import is running; resume this one when it ends"
    if imp.status != CddMoleculeImportStatus.FAILED:
        return "Only a failed import can be resumed"
    if not imp.resumable:
        return (
            "This import can't be resumed: it stopped before its export was saved. "
            "Start a new import."
        )
    return None


def _request(
    imp: CddMoleculeImport, resumed_by: uuid.UUID, resumed_by_org_id: uuid.UUID | None
) -> ResumeCddMoleculeImportRequest:
    assert imp.cdd_export_id is not None and imp.run_settings is not None  # resumable
    return ResumeCddMoleculeImportRequest(
        workspace_id=imp.workspace_id,
        import_id=imp.id,
        cdd_vault_id=imp.cdd_vault_id,
        import_mode=imp.import_mode.value,
        submitted_by=resumed_by,
        originating_org_id=imp.originating_org_id,
        filter_criteria=imp.filter_criteria,
        run_settings=imp.run_settings,
        cdd_export_id=imp.cdd_export_id,
        resume_offset=imp.last_processed_offset,
        total_count=imp.total_count,
        registered_count=imp.registered_count,
        duplicate_count=imp.duplicate_count,
        error_count=imp.error_count,
        skipped_count=imp.skipped_count,
        submitted_by_org_id=resumed_by_org_id,
        disclosed_by=imp.disclosed_by,
        disclosed_by_org_id=imp.disclosed_by_org_id,
    )
