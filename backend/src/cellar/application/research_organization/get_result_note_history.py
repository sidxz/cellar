"""GetResultNoteHistory — every version of one campaign row's note, newest first.

Built from the audit operations ``SetResultNotes`` records (one per change):
each one's new value, who and when. ``versions[0]`` is the current note. A
note written before saves were tracked is the oldest version, with who and
when unknown (None) rather than invented. A row that never had a note has none.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.research_organization.set_result_notes import RESULT_NOTE_ENTITY_TYPE
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.audit_compliance.enums import OperationType
from cellar.domain.audit_compliance.models import AuditOperation
from cellar.domain.audit_compliance.repository import AuditRepository
from cellar.domain.research_organization.campaign_result import ResultNote
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetResultNoteHistoryQuery(Query):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    result_id: uuid.UUID


def _notes_entry_values(op: AuditOperation) -> tuple[str | None, str | None]:
    entry = next(e for e in op.entries if e.field_name == "notes")
    return entry.old_value, entry.new_value


class GetResultNoteHistory:
    """Return one row's note versions, newest first (viewer role)."""

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        audit_repository: AuditRepository,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._audit = audit_repository

    async def __call__(
        self,
        input: GetResultNoteHistoryQuery,
        auth: AuthContext | None = None,
    ) -> Result[list[ResultNote], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            current = await self._campaign_repo.find_result_note(
                input.workspace_id, input.campaign_id, input.result_id
            )
        if current is None:
            return Failure(NotFoundError("CampaignResult", str(input.result_id)))

        ops = await self._audit.find_by_entity(
            input.workspace_id, RESULT_NOTE_ENTITY_TYPE, input.result_id
        )
        edits = sorted(
            (op for op in ops if op.operation_type == OperationType.NOTE_EDIT),
            key=lambda op: op.started_at,
            reverse=True,
        )
        versions = [
            ResultNote(_notes_entry_values(op)[1], op.user_id, op.started_at) for op in edits
        ]
        legacy = _notes_entry_values(edits[-1])[0] if edits else current.notes
        if legacy is not None:
            versions.append(ResultNote(legacy, None, None))
        return Success(versions)
