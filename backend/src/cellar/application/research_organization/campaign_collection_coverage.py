"""Read use cases for a campaign's library coverage, its stage counts, and its gap.

"Of this library's compounds, how many were tested in this campaign" — covered
counts the members with a readout in any of the campaign's seed runs, the same
"screened" rule run coverage uses, unioned over the runs the campaign was
seeded from. ``total`` is today's membership, so a library that grew since the
screen shows the shortfall.

A campaign with no seed runs (one built from collections, another campaign, or
by hand) reports ``covered: 0`` — nothing was screened *in this campaign*.

Ownership is checked first, as in ``GetProtocolCollectionCoverage``: a foreign
or missing campaign 404s rather than reporting an empty list.

With ``include_stages`` the same read also answers "which library did the hits
come from": the campaign's funnel is evaluated ONCE and tallied per library
over the rows whose molecule that library contains. One evaluation, however
many libraries — the alternative (a per-library results read) re-evaluates the
whole campaign for every cell of a libraries x stages table. It costs a full
aggregate load, which is why it is opt-in.

Two consequences of counting "campaign rows whose molecule is in this library":
a row in no linked library is counted in none of them, so per-library
populations need not sum to the campaign's; a molecule in two libraries counts
in both.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.research_organization.stage_evaluation import (
    evaluate_stages,
    tally_stage_counts,
)
from cellar.domain.screening_assay.collection_coverage import CollectionCoverage
from cellar.domain.screening_assay.repository import CollectionCoverageReader
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True)
class LibraryCoverage:
    """One linked library: its coverage, and optionally its per-stage funnel.

    ``stage_counts`` is None when stages were not asked for — distinct from
    ``{}``, which is a campaign that genuinely has no stages.
    """

    coverage: CollectionCoverage
    stage_counts: dict[uuid.UUID, dict[str, int]] | None = None


@dataclass(frozen=True, kw_only=True)
class GetCampaignCollectionCoverageQuery(Query):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    #: Also tally each library's rows through the campaign's stages. Costs a
    #: full aggregate load, so callers that only want coverage leave it off.
    include_stages: bool = False


class GetCampaignCollectionCoverage:
    """Coverage of each library linked to a campaign, over its seed runs."""

    def __init__(
        self,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        reader: CollectionCoverageReader,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._reader = reader

    async def __call__(
        self, input: GetCampaignCollectionCoverageQuery, auth: AuthContext | None = None
    ) -> Result[list[LibraryCoverage], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            campaign = None
            if input.include_stages:
                campaign = await self._campaign_repo.find_by_id_in_workspace(
                    input.workspace_id, input.campaign_id
                )
                run_ids = [s.run_id for s in campaign.seed_runs] if campaign is not None else None
            else:
                run_ids = await self._campaign_repo.find_seed_run_ids(
                    input.workspace_id, input.campaign_id
                )
            if run_ids is None:
                return Failure(NotFoundError("Campaign", str(input.campaign_id)))
            collection_ids = await self._campaign_repo.list_collection_ids(
                input.workspace_id, input.campaign_id
            )
            coverage = await self._reader.runs_coverage(
                input.workspace_id, collection_ids, run_ids
            )
            if campaign is None:
                return Success([LibraryCoverage(coverage=c) for c in coverage])

            members = await self._campaign_repo.collection_members_among(
                input.workspace_id,
                collection_ids,
                [r.molecule_id for r in campaign.results],
            )

        # One evaluation for the whole campaign; the tally is re-run per
        # library over that library's rows.
        outcomes = evaluate_stages(campaign)
        results_by_molecule: dict[uuid.UUID, list[uuid.UUID]] = {}
        for r in campaign.results:
            results_by_molecule.setdefault(r.molecule_id, []).append(r.id)
        return Success(
            [
                LibraryCoverage(
                    coverage=c,
                    stage_counts=tally_stage_counts(
                        campaign,
                        outcomes,
                        result_ids={
                            result_id
                            for molecule_id in members.get(c.ref.id, ())
                            for result_id in results_by_molecule.get(molecule_id, ())
                        },
                    ),
                )
                for c in coverage
            ]
        )


@dataclass(frozen=True, kw_only=True)
class GetCampaignCollectionGapQuery(Query):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    collection_id: uuid.UUID
    offset: int = 0
    limit: int = 100


class GetCampaignCollectionGap:
    """Library members no seed run of the campaign read (paged)."""

    def __init__(
        self,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        reader: CollectionCoverageReader,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._reader = reader

    async def __call__(
        self, input: GetCampaignCollectionGapQuery, auth: AuthContext | None = None
    ) -> Result[list[uuid.UUID], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            run_ids = await self._campaign_repo.find_seed_run_ids(
                input.workspace_id, input.campaign_id
            )
            if run_ids is None:
                return Failure(NotFoundError("Campaign", str(input.campaign_id)))
            ids = await self._reader.runs_gap(
                input.workspace_id,
                input.collection_id,
                run_ids,
                offset=input.offset,
                limit=input.limit,
            )
        return Success(ids)
