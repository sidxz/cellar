"""The managing app marks a campaign as its own (e.g. DAIKON, for a round it already made)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_editor,
    require_same_workspace,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_management import CampaignManagement
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.shared.errors import (
    AuthorizationError,
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)


@dataclass(frozen=True, kw_only=True)
class SetCampaignManagementCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    managed_url: str
    managed_label: str
    # The realm app making the call (verified X-Service-Token); only it can mark a campaign.
    acting_service: str | None = None
    user_id: uuid.UUID | None = None


class SetCampaignManagement:
    """Hand a campaign to the app making the call; that app again updates where it lives."""

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
        self, input: SetCampaignManagementCommand, auth: AuthContext | None = None
    ) -> Result[Campaign, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        if input.acting_service is None:
            raise AuthorizationError(
                "Only the app that manages a campaign can mark it; send X-Service-Token"
            )

        async with self._uow:
            campaign = await self._campaign_repo.find_by_id_in_workspace(
                input.workspace_id, input.campaign_id
            )
            if campaign is None:
                return Failure(NotFoundError("Campaign", str(input.campaign_id)))
            try:
                management = CampaignManagement(
                    managed_by=input.acting_service,
                    url=input.managed_url,
                    label=input.managed_label,
                )
                campaign.set_management(management, user_id=input.user_id)
            except (ValidationError, ConflictError) as e:
                return Failure(e)
            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(campaign)
