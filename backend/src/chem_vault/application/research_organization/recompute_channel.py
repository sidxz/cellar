"""RecomputeChannel — re-resolve all non-override measurements for a single channel.

Identical logic to ``RefreshFromSources`` but scoped to one ``CampaignChannel``.
Cells on other channels are left entirely untouched.

Pipeline:
  1. ``require_editor`` auth guard.
  2. Load campaign (workspace-scoped); Failure(NotFoundError) if missing.
  3. Inline DRAFT check — Failure(ValidationError) if not DRAFT.
  4. Locate the target channel; Failure(NotFoundError) if missing.
  5. For each result: skip overrides for this channel; re-resolve the rest.
  6. Bump ``campaign.updated_at``. Save + commit; dispatch; return ``Success(campaign)``.
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
from chem_vault.domain.research_organization.enums import CampaignStatus
from chem_vault.domain.research_organization.repository import CampaignRepository
from chem_vault.domain.shared.errors import (
    AuthorizationError,
    DomainError,
    NotFoundError,
    ValidationError,
)


@dataclass(frozen=True, kw_only=True)
class RecomputeChannelCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    channel_id: uuid.UUID


class RecomputeChannel:
    """Re-resolve non-override measurements for a single channel in a DRAFT campaign.

    Pipeline:
      1. ``require_editor`` auth guard.
      2. Load campaign (workspace-scoped); reject if missing.
      3. Inline DRAFT check — reject with ``ValidationError`` if not DRAFT.
      4. Locate the channel by id; reject with ``NotFoundError`` if missing.
      5. For each result: if the measurement for this channel is a manual
         override, skip it; otherwise re-resolve and replace it. If the cell
         is entirely missing, resolve and add it.
      6. Bump ``campaign.updated_at``. Save + commit; dispatch events; return
         ``Success(campaign)``.
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
        input: RecomputeChannelCommand,
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
                        f"Cannot recompute channel: campaign is {campaign.status.value}"
                    )
                )

            channel = next(
                (c for c in campaign.channels if c.id == input.channel_id), None
            )
            if channel is None:
                return Failure(NotFoundError("CampaignChannel", str(input.channel_id)))

            # Snapshot results list to avoid mutation-during-iteration issues
            results = list(campaign.results)

            for result in results:
                measurement = result.find_measurement(channel.id)
                if measurement is not None and measurement.is_manual_override:
                    continue
                new_measurement = await self._resolver.resolve(
                    workspace_id=input.workspace_id,
                    channel=channel,
                    result_id=result.id,
                    molecule_id=result.molecule_id,
                )
                if measurement is not None:
                    result.remove_measurement_for_channel(channel.id)
                result.add_measurement(new_measurement)

            campaign.updated_at = datetime.now(UTC)
            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(campaign)
