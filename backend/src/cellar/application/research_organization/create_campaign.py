"""CreateCampaign — create a draft Campaign (empty, curated workspace).

Creates an empty Campaign aggregate. Compounds are added later via
AddResultsFromCollection, AddResultsFromCampaign, AddResultsFromRuns, or
AddResultRow. Each CampaignResult carries its own source attribution.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.shared.errors import (
    AuthorizationError,
    DomainError,
)


@dataclass(frozen=True, kw_only=True)
class CreateCampaignCommand(Command):
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    publishes_collection: bool
    created_by: uuid.UUID
    supersedes_campaign_id: uuid.UUID | None = None


class CreateCampaign:
    """Create a draft ``Campaign`` — empty, ready for compound curation.

    Pipeline:
      1. ``require_editor`` auth guard.
      2. ``Campaign.create(...)`` — no compound source required.
      3. ``campaign_repo.save`` and ``uow.commit`` inside the UoW.
      4. Dispatch collected events and return ``Success(campaign)``.
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
        input: CreateCampaignCommand,
        auth: AuthContext | None = None,
    ) -> Result[Campaign, DomainError]:
        try:
            require_editor(auth)
        except AuthorizationError as e:
            return Failure(e)

        async with self._uow:
            campaign = Campaign.create(
                workspace_id=input.workspace_id,
                project_id=input.project_id,
                name=input.name,
                description=input.description,
                publishes_collection=input.publishes_collection,
                created_by=input.created_by,
                supersedes_campaign_id=input.supersedes_campaign_id,
            )

            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(campaign)
