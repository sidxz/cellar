"""CreateCampaign — create a draft Campaign and seed its results.

Resolves the ``compound_source`` (explicit list, Collection, or another
Campaign's results filtered by decision) to a list of molecule ids and
seeds one ``CampaignResult`` row per molecule on the new aggregate.

NOTE: ``SavedSearchSource`` is currently not supported and returns a
``ValidationError``. A follow-up will pipe the existing SavedSearch
execution pipeline into the seeding step.
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
from chem_vault.domain.research_organization.campaign_result import CampaignResult
from chem_vault.domain.research_organization.compound_source import (
    CollectionSource,
    CompoundSource,
    DerivedFromCampaignSource,
    ExplicitListSource,
    SavedSearchSource,
)
from chem_vault.domain.research_organization.enums import CampaignDecision
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
class CreateCampaignCommand(Command):
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    compound_source: CompoundSource
    publishes_collection: bool
    created_by: uuid.UUID
    supersedes_campaign_id: uuid.UUID | None = None


class CreateCampaign:
    """Create a draft ``Campaign`` and seed its results from ``compound_source``.

    Pipeline:
      1. ``require_editor`` auth guard.
      2. Resolve the compound source to a list of molecule ids.
         - ``ExplicitListSource``: dedupe while preserving input order.
         - ``CollectionSource``: load the collection (workspace-scoped) and
           fetch its molecule membership.
         - ``DerivedFromCampaignSource``: load the referenced campaign
           (workspace-scoped) and filter ``results`` by ``decision_filter``.
         - ``SavedSearchSource``: NOT YET SUPPORTED — returns
           ``ValidationError``. Follow-up will plug in the SavedSearch
           execution pipeline.
      3. Reject if the resolved compound list is empty.
      4. ``Campaign.create(...)`` then ``add_result`` per molecule.
      5. ``campaign_repo.save`` and ``uow.commit`` inside the UoW.
      6. Dispatch collected events and return ``Success(campaign)``.
    """

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        collection_repo: CollectionRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._collection_repo = collection_repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: CreateCampaignCommand,
        auth: AuthContext | None = None,
    ) -> Result[Campaign, DomainError]:
        try:
            require_editor(auth)
        except AuthorizationError as e:
            return Failure(e)

        async with self._uow:
            try:
                molecule_ids = await self._resolve_source(input)
            except DomainError as e:
                return Failure(e)

            if not molecule_ids:
                return Failure(
                    ValidationError("compound_source resolved to zero compounds")
                )

            campaign = Campaign.create(
                workspace_id=input.workspace_id,
                project_id=input.project_id,
                name=input.name,
                description=input.description,
                compound_source=input.compound_source,
                publishes_collection=input.publishes_collection,
                created_by=input.created_by,
                supersedes_campaign_id=input.supersedes_campaign_id,
            )
            for mid in molecule_ids:
                campaign.add_result(
                    CampaignResult(campaign_id=campaign.id, molecule_id=mid)
                )

            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(campaign)

    async def _resolve_source(
        self, input: CreateCampaignCommand
    ) -> list[uuid.UUID]:
        src = input.compound_source
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
