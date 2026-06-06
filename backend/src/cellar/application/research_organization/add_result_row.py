"""AddResultRow — add a new compound result row to a DRAFT campaign.

Adds one CampaignResult for the given molecule_id, then resolves a measurement
for every existing CampaignChannel. The aggregate enforces DRAFT status and
unique molecule_id; duplicate inserts raise ValidationError.
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
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.enums import CampaignStatus
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.research_organization.source_ref import ManualRef
from cellar.domain.shared.errors import (
    DomainError,
    NotFoundError,
    ValidationError,
)


@dataclass(frozen=True, kw_only=True)
class AddResultRowCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    molecule_id: uuid.UUID


class AddResultRow:
    """Add a new compound row to a DRAFT campaign and resolve its measurements.

    Pipeline:
      1. ``require_editor`` auth guard.
      2. Load campaign (workspace-scoped); NotFoundError if missing.
      3. Inline DRAFT check — Failure(ValidationError) if not DRAFT.
      4. Build ``CampaignResult(campaign_id=campaign.id, molecule_id=cmd.molecule_id)``.
      5. ``campaign.add_result(result)`` — aggregate raises ValidationError on
         duplicate molecule_id; that propagates to Failure.
      6. For every existing channel, resolve a measurement and attach it to
         the result.
      7. Bump ``campaign.updated_at``. Save + commit; dispatch; return ``Success``.

    No molecule-existence check at this layer — the persistence FK will catch
    unknown molecule ids at commit time.
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
        input: AddResultRowCommand,
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
                    ValidationError(f"Cannot add result: campaign is {campaign.status.value}")
                )

            result = CampaignResult(
                campaign_id=campaign.id,
                molecule_id=input.molecule_id,
                added_from=ManualRef(),
            )
            try:
                campaign.add_result(result)
            except ValidationError as e:
                return Failure(e)

            for channel in campaign.channels:
                measurement = await self._resolver.resolve(
                    workspace_id=input.workspace_id,
                    channel=channel,
                    result_id=result.id,
                    molecule_id=result.molecule_id,
                )
                result.add_measurement(measurement)

            campaign.updated_at = datetime.now(UTC)
            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(campaign)
