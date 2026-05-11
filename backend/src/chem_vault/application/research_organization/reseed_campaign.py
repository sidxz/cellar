"""ReseedCampaign — replace the compound list of a DRAFT campaign and re-resolve.

Resolves a new ``compound_source`` (explicit list, Collection, or another
Campaign's results filtered by decision) to a list of molecule ids, rebuilds
the ``CampaignResult`` list via ``campaign.reseed_results``, then re-runs the
resolver for every existing channel on every new result.

NOTE: ``SavedSearchSource`` is currently not supported and returns a
``ValidationError``. A follow-up will pipe the existing SavedSearch
execution pipeline into the seeding step.
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
from chem_vault.domain.research_organization.campaign_result import CampaignResult
from chem_vault.domain.research_organization.compound_source import (
    CollectionSource,
    CompoundSource,
    DerivedFromCampaignSource,
    ExplicitListSource,
    SavedSearchSource,
)
from chem_vault.domain.research_organization.enums import (
    CampaignDecision,
    CampaignStatus,
)
from chem_vault.domain.research_organization.repository import (
    CampaignRepository,
    CollectionRepository,
)
from chem_vault.domain.shared.errors import (
    AuthorizationError,
    DomainError,
    NotFoundError,
    ValidationError,
)


@dataclass(frozen=True, kw_only=True)
class ReseedCampaignCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    new_source: CompoundSource


class ReseedCampaign:
    """Replace the compound list of a DRAFT campaign and re-resolve measurements.

    Pipeline:
      1. ``require_editor`` auth guard.
      2. Load the campaign (workspace-scoped); reject if missing.
      3. Inline DRAFT check — reject with ``ValidationError`` if not DRAFT.
      4. Resolve the new ``compound_source`` to a list of molecule ids:
         - ``ExplicitListSource``: dedupe while preserving input order.
         - ``CollectionSource``: load the collection (workspace-scoped) and
           fetch its molecule membership.
         - ``DerivedFromCampaignSource``: load the referenced campaign
           (workspace-scoped) and filter ``results`` by ``decision_filter``.
         - ``SavedSearchSource``: NOT YET SUPPORTED — returns
           ``ValidationError``. Follow-up will plug in the SavedSearch
           execution pipeline.
      5. Reject if the resolved compound list is empty.
      6. Build new ``CampaignResult`` objects and call
         ``campaign.reseed_results(new_results)``.
      7. For every existing channel, resolve a fresh measurement for every
         new result and attach it.
      8. ``campaign_repo.save`` and ``uow.commit`` inside the UoW.
      9. Dispatch collected events and return ``Success(campaign)``.
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
        input: ReseedCampaignCommand,
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
                        f"Cannot reseed: campaign is {campaign.status.value}"
                    )
                )

            try:
                molecule_ids = await self._resolve_source(input)
            except DomainError as e:
                return Failure(e)

            if not molecule_ids:
                return Failure(
                    ValidationError("compound_source resolved to zero compounds")
                )

            new_results = [
                CampaignResult(campaign_id=campaign.id, molecule_id=mid)
                for mid in molecule_ids
            ]
            campaign.reseed_results(new_results)

            for channel in campaign.channels:
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

    async def _resolve_source(
        self, input: ReseedCampaignCommand
    ) -> list[uuid.UUID]:
        src = input.new_source
        if isinstance(src, ExplicitListSource):
            # Dedupe while preserving input order
            seen: set[uuid.UUID] = set()
            out: list[uuid.UUID] = []
            for m in src.molecule_ids:
                if m not in seen:
                    seen.add(m)
                    out.append(m)
            return out
        if isinstance(src, CollectionSource):
            coll = await self._collection_repo.find_by_id_in_workspace(
                input.workspace_id, src.collection_id
            )
            if coll is None:
                raise NotFoundError("Collection", str(src.collection_id))
            return await self._collection_repo.get_molecule_ids(
                input.workspace_id,
                src.collection_id,
                offset=0,
                limit=100000,
            )
        if isinstance(src, DerivedFromCampaignSource):
            origin = await self._campaign_repo.find_by_id_in_workspace(
                input.workspace_id, src.campaign_id
            )
            if origin is None:
                raise NotFoundError("Campaign", str(src.campaign_id))
            decisions: set[CampaignDecision] = set(src.decision_filter)
            return [
                r.molecule_id for r in origin.results if r.decision in decisions
            ]
        if isinstance(src, SavedSearchSource):
            raise ValidationError(
                "saved_search compound_source is not yet supported"
            )
        raise ValidationError(f"Unknown CompoundSource: {src!r}")
