"""Read use cases for a campaign's library coverage and its gap.

"Of this library's compounds, how many were tested in this campaign" — covered
counts the members with a readout in any of the campaign's seed runs, the same
"screened" rule run coverage uses, unioned over the runs the campaign was
seeded from. ``total`` is today's membership, so a library that grew since the
screen shows the shortfall.

A campaign with no seed runs (one built from collections, another campaign, or
by hand) reports ``covered: 0`` — nothing was screened *in this campaign*.

Ownership is checked first, as in ``GetProtocolCollectionCoverage``: a foreign
or missing campaign 404s rather than reporting an empty list.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.screening_assay.collection_coverage import CollectionCoverage
from cellar.domain.screening_assay.repository import CollectionCoverageReader
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetCampaignCollectionCoverageQuery(Query):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID


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
    ) -> Result[list[CollectionCoverage], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
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
        return Success(coverage)


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
