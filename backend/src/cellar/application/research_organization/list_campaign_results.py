"""ListCampaignResults — one page of a campaign's result rows.

``GET /campaigns/{id}`` returns every row with every measurement, which is the
right read for cellar's own grid (it holds the whole matrix client-side) and
the wrong one for a consumer showing 50 rows of one stage: on a primary screen
seeded at ``scope: "all"``, that is tens of thousands of rows — each carrying
its measurements and, for a dose-response cell, a frozen ``curve_snapshot``
JSONB — serialised to display a page.

This query filters, orders and pages server-side, so the wire carries the page
and nothing else.

Outcomes are still evaluated, not stored: ``evaluate_stages`` is the only thing
that knows what a stage verdict is, and a second implementation in SQL would
be free to disagree with it. Filtering by outcome therefore means evaluating
the campaign, which is why the load below is the whole aggregate.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.pagination import DEFAULT_PAGE_SIZE, PageResult
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.campaign_result_ordering import channel_sort_key
from cellar.domain.research_organization.enums import StageOutcome
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.research_organization.stage_evaluation import (
    StageResultOutcome,
    evaluate_stages,
)
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError


@dataclass(frozen=True, kw_only=True)
class ListCampaignResultsQuery(Query):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    #: Which stage's verdict to filter on. Required when ``outcome`` is set.
    stage_id: uuid.UUID | None = None
    #: The verdict at ``stage_id`` **after** any manual override — exactly what
    #: the row's ``stage_outcomes`` reports.
    outcome: StageOutcome | None = None
    #: Channel to order by. ``None`` keeps the campaign's own row order.
    order_by_channel_id: uuid.UUID | None = None
    descending: bool = False
    #: Id of the last row on the previous page.
    cursor_id: uuid.UUID | None = None
    limit: int = DEFAULT_PAGE_SIZE


@dataclass(frozen=True, kw_only=True)
class ListCampaignResultsOutput:
    page: PageResult[CampaignResult]
    #: Stage outcomes for the rows on this page only, result_id -> stage_id.
    outcomes: dict[uuid.UUID, dict[uuid.UUID, StageResultOutcome]]


class ListCampaignResults:
    def __init__(self, *, uow: UnitOfWork, campaign_repo: CampaignRepository) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo

    async def __call__(
        self, input: ListCampaignResultsQuery, auth: AuthContext | None = None
    ) -> Result[ListCampaignResultsOutput, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)

        if input.outcome is not None and input.stage_id is None:
            return Failure(ValidationError("outcome requires stage_id"))

        async with self._uow:
            # ponytail: loads and evaluates the whole campaign to return one
            # page. The ceiling is the aggregate hydration — `results` and
            # `measurements` are both lazy="selectin" (see
            # docs/backlog/campaign-list-hydrates-results.md), so a 16k-row
            # campaign pulls 16k rows plus measurements per request. The page
            # itself is cheap; what this change removes is serialising all of
            # them. Upgrade when a real campaign makes it hurt: project the
            # criteria channels' values + overrides in one flat SELECT, feed
            # that to evaluate_stages, then load only the page's rows.
            campaign = await self._campaign_repo.find_by_id_in_workspace(
                input.workspace_id, input.campaign_id
            )
            if campaign is None:
                return Failure(NotFoundError("Campaign", str(input.campaign_id)))

            if input.stage_id is not None and campaign.find_stage(input.stage_id) is None:
                return Failure(NotFoundError("CampaignStage", str(input.stage_id)))

            if input.order_by_channel_id is not None and not any(
                ch.id == input.order_by_channel_id for ch in campaign.channels
            ):
                return Failure(NotFoundError("CampaignChannel", str(input.order_by_channel_id)))

            outcomes = evaluate_stages(campaign)

            rows = list(campaign.results)
            if input.stage_id is not None and input.outcome is not None:
                stage_id = input.stage_id
                rows = [
                    r
                    for r in rows
                    if (o := outcomes.get(r.id, {}).get(stage_id)) is not None
                    and o.outcome == input.outcome
                ]
            total = len(rows)

            if input.order_by_channel_id is not None:
                channel_id = input.order_by_channel_id
                rows.sort(
                    key=lambda r: channel_sort_key(r, channel_id, descending=input.descending)
                )
            elif input.descending:
                # No channel named: the campaign's own row order, reversed.
                rows.reverse()

            start = _cursor_index(rows, input.cursor_id)
            page = rows[start : start + input.limit]
            next_cursor = str(page[-1].id) if page and start + input.limit < len(rows) else None

        return Success(
            ListCampaignResultsOutput(
                page=PageResult(items=page, next_cursor=next_cursor, total_count=total),
                outcomes={r.id: outcomes.get(r.id, {}) for r in page},
            )
        )


def _cursor_index(rows: list[CampaignResult], cursor_id: uuid.UUID | None) -> int:
    """Where the next page starts: just past ``cursor_id``.

    An unknown cursor degrades to the first page rather than erroring — the
    row it named can have been removed between two page reads, and the same
    convention already governs cellar's other cursors.
    """
    if cursor_id is None:
        return 0
    for i, row in enumerate(rows):
        if row.id == cursor_id:
            return i + 1
    return 0
