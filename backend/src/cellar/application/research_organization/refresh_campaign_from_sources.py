"""RefreshFromSources — re-resolve every non-override measurement in a DRAFT campaign.

Iterates all (result, channel) pairs. Cells with ``is_manual_override == True``
are skipped. All other cells are re-resolved via ``ChannelResolver`` and
replaced in-place. Missing cells (defensive case) are resolved and added.

Pipeline:
  1. ``require_editor`` auth guard.
  2. Load campaign (workspace-scoped); Failure(NotFoundError) if missing.
  3. Inline DRAFT check — Failure(ValidationError) if not DRAFT.
  4. For each result × channel: skip overrides, re-resolve the rest.
  5. Bump ``campaign.updated_at``. Save + commit; dispatch; return ``Success(campaign)``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.research_organization.channel_resolution import (
    ChannelResolver,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.enums import CampaignStatus
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.shared.errors import (
    DomainError,
    NotFoundError,
    ValidationError,
)


@dataclass(frozen=True, kw_only=True)
class RefreshFromSourcesCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID


class RefreshFromSources:
    """Re-resolve all non-override measurements across all channels in a DRAFT campaign.

    Pipeline:
      1. ``require_editor`` auth guard.
      2. Load campaign (workspace-scoped); reject if missing.
      3. Inline DRAFT check — reject with ``ValidationError`` if not DRAFT.
      4. For each result, for each channel: if the measurement is a manual
         override, skip it; otherwise re-resolve and replace it. If the cell
         is entirely missing, resolve and add it.
      5. Bump ``campaign.updated_at``. Save + commit; dispatch events; return
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
        input: RefreshFromSourcesCommand,
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
                return Failure(
                    ValidationError(f"Cannot refresh: campaign is {campaign.status.value}")
                )

            # Snapshot both lists to avoid mutation-during-iteration issues
            channels = list(campaign.channels)
            results = list(campaign.results)

            for result in results:
                for channel in channels:
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
                        new_measurement.id = (
                            measurement.id
                        )  # preserve id → UPDATE not DELETE+INSERT
                        result.remove_measurement_for_channel(channel.id)
                    result.add_measurement(new_measurement)

            campaign.updated_at = datetime.now(UTC)
            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(campaign)
