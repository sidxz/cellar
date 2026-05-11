"""AddCampaignChannel — add a new channel to a draft Campaign.

Binds a protocol readout to a selection rule, qualifier handling, and
optional QC filter/hit-threshold.  When ``hit_threshold`` is ``None`` the
use case attempts to carry it forward from the protocol's
``recommended_hit_criteria``.  After the channel is appended, one
``CampaignMeasurement`` is resolved for every existing ``CampaignResult``
via ``ChannelResolver``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.research_organization.channel_resolution import (
    ChannelResolver,
)
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.research_organization.campaign import Campaign
from chem_vault.domain.research_organization.campaign_channel import CampaignChannel
from chem_vault.domain.research_organization.enums import (
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
)
from chem_vault.domain.research_organization.repository import CampaignRepository
from chem_vault.domain.screening_assay.hit_criterion import HitCriterion
from chem_vault.domain.screening_assay.repository import ProtocolRepository
from chem_vault.domain.shared.errors import (
    AuthorizationError,
    DomainError,
    NotFoundError,
    ValidationError,
)


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
    hit_threshold: HitCriterion | None  # None → attempt carry-forward from protocol
    display_order: int


class AddCampaignChannel:
    """Add a channel to a draft Campaign and seed measurements for existing results.

    Pipeline:
      1. ``require_editor`` auth guard.
      2. Load campaign (workspace-scoped).
      3. If ``hit_threshold`` is ``None``, load the protocol and attempt to
         carry-forward the matching ``HitCriterion`` from
         ``recommended_hit_criteria``.
      4. Construct the ``CampaignChannel``.
      5. ``campaign.add_channel(channel)`` (aggregate enforces DRAFT guard).
      6. For every existing result call ``resolver.resolve`` and append the
         returned measurement to the result.
      7. Save + commit inside the UoW; dispatch events outside.
    """

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        protocol_repo: ProtocolRepository,
        resolver: ChannelResolver,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._protocol_repo = protocol_repo
        self._resolver = resolver
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: AddCampaignChannelCommand,
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

            # Carry-forward hit_threshold from protocol if not supplied
            effective_threshold = input.hit_threshold
            if effective_threshold is None:
                protocol = await self._protocol_repo.find_by_id_in_workspace(
                    input.workspace_id, input.protocol_id
                )
                if protocol is None:
                    return Failure(NotFoundError("Protocol", str(input.protocol_id)))
                readout_def = next(
                    (
                        rd
                        for rd in protocol.readout_definitions
                        if rd.id == input.readout_definition_id
                    ),
                    None,
                )
                if readout_def is None:
                    return Failure(
                        ValidationError(
                            f"ReadoutDefinition {input.readout_definition_id} "
                            f"not found on protocol {input.protocol_id}"
                        )
                    )
                if protocol.recommended_hit_criteria:
                    matched = next(
                        (
                            c
                            for c in protocol.recommended_hit_criteria
                            if c.readout_name == readout_def.name
                        ),
                        None,
                    )
                    effective_threshold = matched  # None if no match — that is fine

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
                    hit_threshold=effective_threshold,
                    display_order=input.display_order,
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
