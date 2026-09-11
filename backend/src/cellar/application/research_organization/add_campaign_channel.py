"""AddCampaignChannel — add a new channel to a draft Campaign.

Binds a protocol readout to a selection rule, qualifier handling, and an
optional QC filter. After the channel is appended, one ``CampaignMeasurement``
is resolved for every existing ``CampaignResult`` via ``ChannelResolver``.
Hit/miss criteria live on ``CampaignStage``, not the channel.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.research_organization.channel_resolution import (
    ChannelResolver,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
)
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.shared.errors import (
    DomainError,
    NotFoundError,
    ValidationError,
)
from cellar.domain.shared.hit_criterion import InterceptKey


@dataclass(frozen=True, kw_only=True)
class AddCampaignChannelCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    label: str
    protocol_id: uuid.UUID
    readout_definition_id: uuid.UUID
    source_kind: ChannelSourceKind
    selection_rule: SelectionRule
    qualifier_handling: QualifierHandling
    qc_filter: dict | None
    display_order: int
    #: Optional normalization layer to read for readout_data channels (e.g.
    #: "percent_inhibition"). ``None`` selects the raw layer. Ignored for
    #: dose-response curve channels.
    normalization_applied: str | None = None
    #: Identifies which intercept of a DR curve this channel surfaces.
    #: ``None`` = primary intercept (legacy single-intercept channels).
    intercept_key: InterceptKey | None = None


class AddCampaignChannel:
    """Add a channel to a draft Campaign and seed measurements for existing results.

    Pipeline:
      1. ``require_editor`` auth guard.
      2. Load campaign (workspace-scoped).
      3. Construct the ``CampaignChannel``.
      4. ``campaign.add_channel(channel)`` (aggregate enforces DRAFT guard).
      5. For every existing result call ``resolver.resolve`` and append the
         returned measurement to the result.
      6. Save + commit inside the UoW; dispatch events outside.
    """

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        resolver: ChannelResolver,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._resolver = resolver
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: AddCampaignChannelCommand,
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
                channel = CampaignChannel(
                    campaign_id=campaign.id,
                    label=input.label,
                    protocol_id=input.protocol_id,
                    readout_definition_id=input.readout_definition_id,
                    source_kind=input.source_kind,
                    selection_rule=input.selection_rule,
                    qualifier_handling=input.qualifier_handling,
                    qc_filter=input.qc_filter,
                    display_order=input.display_order,
                    normalization_applied=(
                        input.normalization_applied
                        if input.source_kind == ChannelSourceKind.READOUT_DATA
                        else None
                    ),
                    intercept_key=input.intercept_key,
                )
                campaign.add_channel(channel)
            except ValidationError as e:
                return Failure(e)

            for result in campaign.results:
                measurement = await self._resolver.resolve(
                    workspace_id=input.workspace_id,
                    channel=channel,
                    result_id=result.id,
                    molecule_id=result.molecule_id,
                )
                result.add_measurement(measurement)

            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(campaign)
