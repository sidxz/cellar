"""GetCampaign — load a campaign by id with scientist resolution."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.research_organization.campaign_scientist_reader import (
    CampaignScientistReader,
)
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetCampaignQuery(Query):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class GetCampaignResult:
    campaign: Campaign
    scientist_by_run_id: dict[uuid.UUID, str]


class GetCampaign:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        scientist_reader: CampaignScientistReader,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._scientist_reader = scientist_reader

    async def __call__(
        self, input: GetCampaignQuery, auth: AuthContext | None = None
    ) -> Result[GetCampaignResult, DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            campaign = await self._campaign_repo.find_by_id_in_workspace(
                input.workspace_id, input.campaign_id
            )
            if campaign is None:
                return Failure(NotFoundError("Campaign", str(input.campaign_id)))

            run_ids = {
                m.source_run_id
                for r in campaign.results
                for m in r.measurements
                if m.source_run_id is not None
            }
            scientist_by_run_id = await self._scientist_reader.find_scientist_by_run_ids(
                input.workspace_id, run_ids
            )

        return Success(
            GetCampaignResult(campaign=campaign, scientist_by_run_id=scientist_by_run_id)
        )
