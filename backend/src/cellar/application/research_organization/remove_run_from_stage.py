"""RemoveRunFromStage — take a run off a stage; the stage's columns recompute (spec §9).

The run stays in the campaign (with no stages left it is a campaign run), and so do
the compound rows: their cells at that stage recompute over the runs the stage has
left, untested when none remain. Idempotent: a run that is not on the stage, or not
in the campaign at all, is a no-op. An unknown stage is ``NotFoundError``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.research_organization.column_resolution import ColumnCandidateQuery
from cellar.application.research_organization.recompute_columns import recompute_columns
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.enums import CampaignStatus
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.shared.errors import DataLockedError, DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class RemoveRunFromStageCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    stage_id: uuid.UUID
    run_id: uuid.UUID


class RemoveRunFromStage:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        query: ColumnCandidateQuery,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._query = query
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: RemoveRunFromStageCommand,
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
                # 423, like every other stage write.
                return Failure(DataLockedError(f"Campaign is {campaign.status.value}"))
            if campaign.find_stage(input.stage_id) is None:
                return Failure(NotFoundError("CampaignStage", str(input.stage_id)))
            if not any(
                s.run_id == input.run_id and input.stage_id in s.stage_ids
                for s in campaign.seed_runs
            ):
                return Success(campaign)

            campaign.remove_run_from_stage(input.stage_id, input.run_id)
            await recompute_columns(
                query=self._query,
                campaign=campaign,
                channels=campaign.channels_of_stage(input.stage_id),
            )
            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(campaign)
