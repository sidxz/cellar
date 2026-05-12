"""AddResultsFromCollection — pull molecules from a Collection into a Campaign.

Idempotent: re-adding molecules already in the campaign is silently skipped.
Each new CampaignResult is attributed to the source Collection via CollectionRef.
For every new result, one measurement is resolved per existing channel.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.research_organization.channel_resolution import (
    ChannelResolver,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.repository import (
    CampaignRepository,
    CollectionRepository,
)
from cellar.domain.research_organization.source_ref import CollectionRef
from cellar.domain.shared.errors import (
    AuthorizationError,
    DomainError,
    NotFoundError,
    ValidationError,
)


@dataclass(frozen=True, kw_only=True)
class AddResultsFromCollectionCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    collection_id: uuid.UUID
    description: str | None = None


@dataclass
class AddResultsOutcome:
    campaign: Campaign
    added: int
    skipped: int


class AddResultsFromCollection:
    """Add results from a Collection's membership to a DRAFT Campaign.

    Pipeline:
      1. require_editor auth guard.
      2. Load campaign (workspace-scoped); NotFoundError if missing.
      3. Load collection (workspace-scoped); NotFoundError if missing.
      4. Fetch molecule ids from collection membership.
      5. Build CampaignResult rows attributed to CollectionRef.
      6. campaign.add_results() — idempotent, returns (added, skipped).
      7. For each new result, resolve measurements for all existing channels.
      8. Save + commit + dispatch events.
    """

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        collection_repo: CollectionRepository,
        resolver: ChannelResolver,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._collection_repo = collection_repo
        self._resolver = resolver
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: AddResultsFromCollectionCommand,
        auth: AuthContext | None = None,
    ) -> Result[AddResultsOutcome, DomainError]:
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

            collection = await self._collection_repo.find_by_id_in_workspace(
                input.workspace_id, input.collection_id
            )
            if collection is None:
                return Failure(NotFoundError("Collection", str(input.collection_id)))

            molecule_ids = await self._collection_repo.get_molecule_ids(
                input.workspace_id,
                input.collection_id,
                offset=0,
                limit=100_000,
            )

            source_ref = CollectionRef(
                collection_id=input.collection_id,
                description=input.description,
            )
            new_results = [
                CampaignResult(
                    campaign_id=campaign.id,
                    molecule_id=mid,
                    added_from=source_ref,
                )
                for mid in molecule_ids
            ]

            try:
                added, skipped = campaign.add_results(new_results)
            except ValidationError as e:
                return Failure(e)

            # Resolve measurements for the newly added results only.
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
