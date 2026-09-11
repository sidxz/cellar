"""ReopenCampaign — move a CLOSED campaign back to DRAFT.

No signature, no collection to unwind — this is the mirror of ``CloseCampaign``
minus everything soft-close removed. ``campaign.reopen`` enforces the CLOSED
guard (superseded campaigns cannot be reopened) and clears close metadata.

Pipeline:
  1. ``require_editor`` auth guard.
  2. Load campaign (workspace-scoped); ``Failure(NotFoundError)`` if missing.
  3. ``campaign.reopen(reopened_by=..., reason=...)`` — catch ``ValidationError``
     and return ``Failure`` (not CLOSED, or an empty reason).
  4. Save + commit; dispatch events; return ``Success(campaign)``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.shared.errors import (
    DomainError,
    NotFoundError,
    ValidationError,
)


@dataclass(frozen=True, kw_only=True)
class ReopenCampaignCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    user_id: uuid.UUID
    reason: str


class ReopenCampaign:
    """Move a CLOSED campaign back to DRAFT, clearing its close metadata.

    Pipeline:
      1. ``require_editor`` auth guard.
      2. Load campaign (workspace-scoped).
      3. ``campaign.reopen(...)`` — aggregate enforces CLOSED-only + non-empty
         reason; ``ValidationError`` is caught here and returned as ``Failure``.
      4. Save + commit; dispatch events; return ``Success(campaign)``.
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
        input: ReopenCampaignCommand,
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

            try:
                campaign.reopen(reopened_by=input.user_id, reason=input.reason)
            except ValidationError as e:
                return Failure(e)

            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(campaign)
