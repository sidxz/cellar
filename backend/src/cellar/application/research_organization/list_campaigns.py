"""ListCampaigns query — workspace- (and optionally project-) scoped read."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.shared.pagination import PageResult
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListCampaignsQuery(Query):
    workspace_id: uuid.UUID
    project_id: uuid.UUID | None = None
    cursor_id: uuid.UUID | None = None
    limit: int | None = None
    tags: list[uuid.UUID] | None = None
    tag_logic: str = "any"


class ListCampaigns:
    def __init__(self, *, uow: UnitOfWork, campaign_repo: CampaignRepository) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo

    async def __call__(
        self, input: ListCampaignsQuery, auth: AuthContext | None = None
    ) -> Result[PageResult[Campaign], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            effective_limit = input.limit
            fetch_limit = effective_limit + 1 if effective_limit is not None else None

            if input.project_id is not None:
                campaigns = await self._campaign_repo.find_by_project(
                    input.workspace_id,
                    input.project_id,
                    cursor_id=input.cursor_id,
                    limit=fetch_limit,
                    tags=input.tags,
                    tag_logic=input.tag_logic,
                )
            else:
                campaigns = await self._campaign_repo.find_by_workspace(
                    input.workspace_id,
                    cursor_id=input.cursor_id,
                    limit=fetch_limit,
                    tags=input.tags,
                    tag_logic=input.tag_logic,
                )

            next_cursor: str | None = None
            if effective_limit is not None and len(campaigns) > effective_limit:
                campaigns = campaigns[:effective_limit]
                next_cursor = str(campaigns[-1].id)

            return Success(PageResult(items=campaigns, next_cursor=next_cursor))
