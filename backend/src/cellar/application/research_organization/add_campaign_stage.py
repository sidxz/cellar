"""AddCampaignStage — add a hit-triage stage to a draft Campaign.

Stages are named AND-combinations of rules over the campaign's channels,
owned by ``Campaign`` (see ``domain/research_organization/campaign_stage.py``).
Unlike channels, stages have no dependent measurements to resolve — adding
one is a pure aggregate mutation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_stage import CampaignStage, StageCriterion
from cellar.domain.research_organization.enums import CampaignStatus, StageKind
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.shared.errors import (
    DataLockedError,
    DomainError,
    NotFoundError,
    ValidationError,
)


@dataclass(frozen=True, kw_only=True)
class AddCampaignStageCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    name: str
    parent_stage_id: uuid.UUID | None = None
    kind: StageKind = StageKind.CRITERIA
    criteria: list[StageCriterion] = field(default_factory=list)


class AddCampaignStage:
    """Add a stage to a draft Campaign.

    Pipeline:
      1. ``require_editor`` auth guard.
      2. Load campaign (workspace-scoped); ``Failure(NotFoundError)`` if missing.
      3. Status guard — ``Failure(DataLockedError)`` if not DRAFT (checked here,
         not left to the aggregate's internal draft guard, so a closed campaign
         reports 423 rather than 422 — matches ``UpdateCampaignMetadata``).
      4. Construct the ``CampaignStage`` at the next ``display_order`` and
         ``campaign.add_stage`` it — the aggregate validates name uniqueness,
         parent existence/cycles, and that criteria reference real channels.
      5. Save + commit inside the UoW; dispatch events outside; return
         ``Success(campaign)``.
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
        input: AddCampaignStageCommand,
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

            next_display_order = max((s.display_order for s in campaign.stages), default=-1) + 1
            try:
                stage = CampaignStage(
                    campaign_id=campaign.id,
                    name=input.name,
                    display_order=next_display_order,
                    parent_stage_id=input.parent_stage_id,
                    kind=input.kind,
                    criteria=input.criteria,
                )
                campaign.add_stage(stage)
            except ValidationError as e:
                return Failure(e)

            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(campaign)
