"""UpdateCampaignChannel — mutate label, selection rule, qc_filter, or hit_threshold.

Uses the UNSET sentinel to distinguish "don't touch this field" from
``None`` (which is a meaningful value for ``hit_threshold`` and
``qc_filter`` — it clears them).

When a gating field (selection_rule, qc_filter, hit_threshold) actually
changes value, every non-manual-override measurement for this channel
across all results is re-resolved via ``ChannelResolver``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.research_organization.channel_resolution import (
    ChannelResolver,
)
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.research_organization.campaign import Campaign
from chem_vault.domain.research_organization.enums import (
    CampaignStatus,
    SelectionRule,
)
from chem_vault.domain.research_organization.repository import CampaignRepository
from chem_vault.domain.screening_assay.hit_criterion import HitCriterion
from chem_vault.domain.shared.errors import (
    AuthorizationError,
    DomainError,
    NotFoundError,
    ValidationError,
)


class _Unset:
    """Singleton sentinel meaning "caller did not supply this field"."""

    _instance: _Unset | None = None

    def __new__(cls) -> _Unset:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNSET"


UNSET = _Unset()


@dataclass(frozen=True, kw_only=True)
class UpdateCampaignChannelCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    channel_id: uuid.UUID
    # UNSET means "don't touch"; None means "clear the value"
    label: str | object = UNSET
    selection_rule: SelectionRule | object = UNSET
    qc_filter: dict | None | object = UNSET
    hit_threshold: HitCriterion | None | object = UNSET


class UpdateCampaignChannel:
    """Update mutable fields on a CampaignChannel and optionally re-resolve measurements.

    Pipeline:
      1. ``require_editor`` auth guard.
      2. Load campaign; check status is DRAFT.
      3. Locate the channel by id.
      4. Detect which fields are changing (sentinel-aware).
      5. Mutate label in-place when supplied.
      6. If any gating field (selection_rule, qc_filter, hit_threshold) changed,
         re-resolve every non-manual-override measurement for this channel.
      7. Bump ``campaign.updated_at``.
      8. Save + commit; dispatch events; return ``Success(campaign)``.
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
        input: UpdateCampaignChannelCommand,
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

            if campaign.status != CampaignStatus.DRAFT:
                return Failure(
                    ValidationError(
                        f"Cannot update channel: campaign is {campaign.status.value}"
                    )
                )

            channel = next(
                (c for c in campaign.channels if c.id == input.channel_id), None
            )
            if channel is None:
                return Failure(NotFoundError("CampaignChannel", str(input.channel_id)))

            # Determine which gating fields actually changed value
            gating_changed = False

            if not isinstance(input.selection_rule, _Unset):
                if input.selection_rule != channel.selection_rule:
                    gating_changed = True
                channel.selection_rule = input.selection_rule  # type: ignore[assignment]

            if not isinstance(input.qc_filter, _Unset):
                if input.qc_filter != channel.qc_filter:
                    gating_changed = True
                channel.qc_filter = input.qc_filter  # type: ignore[assignment]

            if not isinstance(input.hit_threshold, _Unset):
                if input.hit_threshold != channel.hit_threshold:
                    gating_changed = True
                channel.hit_threshold = input.hit_threshold  # type: ignore[assignment]

            if not isinstance(input.label, _Unset):
                label = input.label
                if not isinstance(label, str) or not label.strip():
                    return Failure(
                        ValidationError("CampaignChannel.label must not be empty")
                    )
                channel.label = label.strip()

            # Re-resolve non-override measurements when gating fields changed
            if gating_changed:
                for result in campaign.results:
                    measurement = result.find_measurement(channel.id)
                    if measurement is None:
                        continue
                    if measurement.is_manual_override:
                        continue
                    new_measurement = await self._resolver.resolve(
                        workspace_id=input.workspace_id,
                        channel=channel,
                        result_id=result.id,
                        molecule_id=result.molecule_id,
                    )
                    new_measurement.id = measurement.id  # preserve id → UPDATE not DELETE+INSERT
                    result.remove_measurement_for_channel(channel.id)
                    result.add_measurement(new_measurement)

            campaign.updated_at = datetime.now(UTC)
            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(campaign)
