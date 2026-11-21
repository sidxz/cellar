"""SetResultNotes — save the free-text note on one campaign result.

A note can be saved on any campaign status: scientists come back to a closed
campaign months later to write down what they remember. Each change records
who saved it and when on the row, and one audit operation (old → new) in the
same transaction; ``GetResultNoteHistory`` reads those back as the versions.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from returns.result import Failure, Result, Success

from cellar.application.audit.audit_recording_service import AuditRecordingService
from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.audit_compliance.enums import AuditAction, OperationType
from cellar.domain.audit_compliance.models import AuditEntry
from cellar.domain.research_organization.campaign_result import ResultNote, StaleNoteError
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.shared.errors import DomainError, NotFoundError

#: The audit entity type note edits are recorded against; the history query reads it.
RESULT_NOTE_ENTITY_TYPE = "CampaignResult"


@dataclass(frozen=True, kw_only=True)
class SetResultNotesCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    result_id: uuid.UUID
    #: ``None`` (or blank) clears the note.
    notes: str | None
    #: The note as the editor opened it; a save from an out-of-date copy is refused.
    expected_notes: str | None


def _audit_action(before: str | None, after: str | None) -> AuditAction:
    if before is None:
        return AuditAction.CREATE
    if after is None:
        return AuditAction.DELETE
    return AuditAction.UPDATE


class SetResultNotes:
    """Save (or clear) the note on one CampaignResult row.

    Pipeline:
      1. ``require_editor`` auth guard, then ``require_same_workspace``.
      2. Load campaign (workspace-scoped); NotFoundError if missing.
      3. Find the result by id on ``campaign.results``; NotFoundError if missing.
      4. ``result.set_notes`` — StaleNoteError when ``expected_notes`` is out of
         date; the same text as now changes nothing and saves nothing.
      5. Bump ``campaign.updated_at``, save, and record the audit operation in
         the UoW's transaction, so the note and its history commit together.
      6. Commit; dispatch events; return ``Success(result.note)``.
    """

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        audit: AuditRecordingService,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._audit = audit
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: SetResultNotesCommand,
        auth: AuthContext | None = None,
    ) -> Result[ResultNote, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        assert auth is not None  # require_editor raised otherwise

        async with self._uow:
            campaign = await self._campaign_repo.find_by_id_in_workspace(
                input.workspace_id, input.campaign_id
            )
            if campaign is None:
                return Failure(NotFoundError("Campaign", str(input.campaign_id)))

            result = next((r for r in campaign.results if r.id == input.result_id), None)
            if result is None:
                return Failure(NotFoundError("CampaignResult", str(input.result_id)))

            before = result.notes
            now = datetime.now(UTC)
            try:
                changed = result.set_notes(
                    input.notes, expected_notes=input.expected_notes, by=auth.user_id, at=now
                )
            except StaleNoteError as exc:
                return Failure(exc)
            if not changed:
                return Success(result.note)

            campaign.updated_at = now
            await self._campaign_repo.save(campaign)
            await self._audit.record(
                workspace_id=input.workspace_id,
                operation_type=OperationType.NOTE_EDIT,
                entity_type=RESULT_NOTE_ENTITY_TYPE,
                entity_id=result.id,
                user_id=auth.user_id,
                entries=[
                    AuditEntry(
                        entity_type=RESULT_NOTE_ENTITY_TYPE,
                        entity_id=result.id,
                        field_name="notes",
                        action=_audit_action(before, result.notes),
                        old_value=before,
                        new_value=result.notes,
                    )
                ],
                session=self._uow.session,
            )
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(result.note)
