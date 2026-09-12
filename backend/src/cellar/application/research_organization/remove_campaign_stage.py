"""RemoveCampaignStage — drop a stage from a draft Campaign.

Unlike ``remove_channel`` (silent on an unknown id), ``Campaign.remove_stage``
raises ``NotFoundError`` itself when the stage id is unknown, and
``ConflictError`` when child stages still reference it — so no separate
existence check is needed here, just a catch around the aggregate call.
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
from cellar.domain.research_organization.enums import CampaignStatus
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.shared.errors import (
    ConflictError,
    DataLockedError,
    DomainError,
    NotFoundError,
)


@dataclass(frozen=True, kw_only=True)
class RemoveCampaignStageCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    stage_id: uuid.UUID


class RemoveCampaignStage:
    """Remove a stage from a draft Campaign.

    Pipeline:
      1. ``require_editor`` auth guard.
      2. Load campaign (workspace-scoped); ``Failure(NotFoundError)`` if missing.
      3. Status guard — ``Failure(DataLockedError)`` if not DRAFT.
      4. ``campaign.remove_stage(stage_id)`` — ``NotFoundError`` if the stage
         is unknown, ``ConflictError`` if child stages still reference it.
      5. Save + commit; dispatch events; return ``Success(campaign)``.
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
        input: RemoveCampaignStageCommand,
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
                return Failure(DataLockedError(f"Campaign is {campaign.status.value}"))

            try:
                campaign.remove_stage(input.stage_id)
            except (NotFoundError, ConflictError) as e:
                return Failure(e)

            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(campaign)
