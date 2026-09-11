"""SetResultNotes — edit the free-text notes on one result of a DRAFT campaign.

Notes are the only per-result free-text field; triage lives in the stage
funnel. ``notes=None`` clears them. The campaign must be in DRAFT status;
closed and superseded campaigns are immutable.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.enums import CampaignStatus
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.shared.errors import (
    DomainError,
    NotFoundError,
    ValidationError,
)


@dataclass(frozen=True, kw_only=True)
class SetResultNotesCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    result_id: uuid.UUID
    #: ``None`` clears the notes.
    notes: str | None


class SetResultNotes:
    """Set (or clear) the notes on one CampaignResult row.

    Pipeline:
      1. ``require_editor`` auth guard.
      2. Load campaign (workspace-scoped); NotFoundError if missing.
      3. Inline DRAFT check — Failure(ValidationError) if not DRAFT.
      4. Find the result by id on ``campaign.results``; NotFoundError if missing.
      5. Assign ``result.notes``.
      6. Bump ``campaign.updated_at``.
      7. Save + commit inside UoW; dispatch events; return ``Success(campaign)``.
    """

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: SetResultNotesCommand,
        auth: AuthContext | None = None,
    ) -> Result[Campaign, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            campaign = await self._campaign_repo.find_by_id_in_workspace(
                input.workspace_id, input.campaign_id
            )
            if campaign is None:
                return Failure(NotFoundError("Campaign", str(input.campaign_id)))

            if campaign.status != CampaignStatus.DRAFT:
                return Failure(
                    ValidationError(f"Cannot edit notes: campaign is {campaign.status.value}")
                )

            result = next((r for r in campaign.results if r.id == input.result_id), None)
            if result is None:
                return Failure(NotFoundError("CampaignResult", str(input.result_id)))

            result.notes = input.notes
            campaign.updated_at = datetime.now(UTC)

            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(campaign)
