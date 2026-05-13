"""AddResultsFromCampaign — pull molecules from another Campaign into this Campaign.

Accepts ANY source campaign status (draft / closed / superseded). The curator
decides what is valid. Results are filtered by the specified decision_filter.
Idempotent: re-adding molecules already in the campaign is silently skipped.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.research_organization.add_results_from_collection import (
    AddResultsOutcome,
)
from cellar.application.research_organization.channel_resolution import (
    ChannelResolver,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.enums import CampaignDecision
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.research_organization.source_ref import CampaignRef
from cellar.domain.shared.errors import (
    DomainError,
    NotFoundError,
    ValidationError,
)


@dataclass(frozen=True, kw_only=True)
class AddResultsFromCampaignCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    source_campaign_id: uuid.UUID
    decision_filter: list[CampaignDecision]
    description: str | None = None


class AddResultsFromCampaign:
    """Add results from another Campaign's filtered result set into this Campaign.

    Source campaign status is intentionally not checked — the curator may pull
    from draft, closed, or superseded campaigns as appropriate.

    Pipeline:
      1. require_editor auth guard.
      2. Load target campaign; NotFoundError if missing.
      3. Load source campaign; NotFoundError if missing.
      4. Filter source results by decision_filter.
      5. Build CampaignResult rows attributed to CampaignRef.
      6. campaign.add_results() — idempotent.
      7. Resolve measurements for newly added results.
      8. Save + commit + dispatch.
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
        input: AddResultsFromCampaignCommand,
        auth: AuthContext | None = None,
    ) -> Result[AddResultsOutcome, DomainError]:
        require_editor(auth)

        async with self._uow:
            campaign = await self._campaign_repo.find_by_id_in_workspace(
                input.workspace_id, input.campaign_id
            )
            if campaign is None:
                return Failure(NotFoundError("Campaign", str(input.campaign_id)))

            source = await self._campaign_repo.find_by_id_in_workspace(
                input.workspace_id, input.source_campaign_id
            )
            if source is None:
                return Failure(NotFoundError("Campaign", str(input.source_campaign_id)))

            allowed_decisions: set[CampaignDecision] = set(input.decision_filter)
            source_ref = CampaignRef(
                campaign_id=input.source_campaign_id,
                decision_filter=list(input.decision_filter),
                description=input.description,
            )
            new_results = [
                CampaignResult(
                    campaign_id=campaign.id,
                    molecule_id=r.molecule_id,
                    added_from=source_ref,
                )
                for r in source.results
                if r.decision in allowed_decisions
            ]

            try:
                added, skipped = campaign.add_results(new_results)
            except ValidationError as e:
                return Failure(e)

            if added > 0:
                added_molecule_ids = {r.molecule_id for r in new_results}
                for result in campaign.results:
                    if result.molecule_id not in added_molecule_ids:
                        continue
                    for channel in campaign.channels:
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
        return Success(AddResultsOutcome(campaign=campaign, added=added, skipped=skipped))
