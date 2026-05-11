"""RemoveCampaignChannel — drop a channel (and its measurements) from a draft Campaign.

The aggregate's ``remove_channel`` is silent when the id is unknown, so
the use case does an explicit existence check first and returns a
``NotFoundError`` if the channel is not on the campaign.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.research_organization.campaign import Campaign
from chem_vault.domain.research_organization.repository import CampaignRepository
from chem_vault.domain.shared.errors import (
    AuthorizationError,
    DomainError,
    NotFoundError,
)


@dataclass(frozen=True, kw_only=True)
class RemoveCampaignChannelCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    channel_id: uuid.UUID


class RemoveCampaignChannel:
    """Remove a channel and its measurements from a draft Campaign.

    Pipeline:
      1. ``require_editor`` auth guard.
      2. Load campaign (workspace-scoped).
      3. Explicit existence check — ``NotFoundError`` if channel is not present.
      4. ``campaign.remove_channel(channel_id)`` (aggregate enforces DRAFT guard
         and cascades measurement removal).
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
        input: RemoveCampaignChannelCommand,
        auth: AuthContext | None = None,
    ) -> Result[Campaign, DomainError]:
        try:
            require_editor(auth)
        except AuthorizationError as e:
            return Failure(e)

        async with self._uow:
            campaign = await self._campaign_repo.find_by_id_in_workspace(
                input.workspace_id, input.campaign_id
            )
            if campaign is None:
                return Failure(NotFoundError("Campaign", str(input.campaign_id)))

            if not any(c.id == input.channel_id for c in campaign.channels):
                return Failure(
                    NotFoundError("CampaignChannel", str(input.channel_id))
                )

            campaign.remove_channel(input.channel_id)

            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(campaign)
