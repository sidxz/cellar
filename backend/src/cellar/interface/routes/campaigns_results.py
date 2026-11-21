"""Campaign result-row endpoints.

Covers the paged row read, per-row CRUD (add / remove), bulk row removal,
per-row notes edits, per-cell manual overrides, and QC verdicts on many cells.

Every write here answers 204. They used to return the whole
``CampaignResponse``, so editing one cell on a 16,900-row campaign serialised
the entire result matrix back to say so. No caller wanted it — cellar's own
grid invalidates and refetches, and daikon's client ignores the body — and a
write that reports "here is everything" hides which thing it actually changed.
Read the new state with ``GET /campaigns/{id}`` or the paged read above.
The QC write is the exception: it answers with its counts, which only it knows.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from cellar.application.research_organization.add_result_row import (
    AddResultRowCommand,
)
from cellar.application.research_organization.campaign_row_selection import RowSelection
from cellar.application.research_organization.get_result_note_history import (
    GetResultNoteHistoryQuery,
)
from cellar.application.research_organization.list_campaign_results import (
    ListCampaignResultsQuery,
)
from cellar.application.research_organization.override_result_cell import (
    OverrideResultCellCommand,
)
from cellar.application.research_organization.remove_result_row import (
    RemoveResultRowCommand,
)
from cellar.application.research_organization.set_cell_qc_verdicts import (
    QcTarget,
    SetCellQcVerdictsCommand,
)
from cellar.application.research_organization.set_result_notes import (
    SetResultNotesCommand,
)
from cellar.domain.research_organization.campaign_result_filters import CampaignResultFilters
from cellar.domain.research_organization.campaign_stage import UNSET
from cellar.domain.research_organization.enums import QcVerdict, StageOutcome, ValueQualifier
from cellar.interface.dependencies import (
    ActingServiceDep,
    AddResultRowDep,
    AuthDep,
    GetResultNoteHistoryDep,
    ListCampaignResultsDep,
    OverrideResultCellDep,
    RemoveResultRowDep,
    SetCellQcVerdictsDep,
    SetResultNotesDep,
)
from cellar.interface.error_handlers import result_to_response
from cellar.interface.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PaginatedResponse,
    clamp_limit,
    parse_cursor,
)
from cellar.interface.routes._campaign_dtos import (
    AddResultRowRequest,
    BulkRemoveResultsRequest,
    CampaignResultResponse,
    OverrideCellRequest,
    QcVerdictCountsResponse,
    ResultNoteHistoryResponse,
    ResultNoteResponse,
    SetQcVerdictsRequest,
    SetResultNotesRequest,
)

router = APIRouter(prefix="/api/v1/campaigns", tags=["campaigns"])


class SearchCampaignResultsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_id: uuid.UUID | None = None
    outcome: list[StageOutcome] = Field(default_factory=list)
    order_by: uuid.UUID | None = None
    direction: Literal["asc", "desc"] = "asc"
    cursor: str | None = Field(default=None, max_length=64)
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    filters: CampaignResultFilters = Field(default_factory=CampaignResultFilters)


@router.post(
    "/{campaign_id}/results/search", response_model=PaginatedResponse[CampaignResultResponse]
)
async def search_campaign_results(
    campaign_id: uuid.UUID,
    body: SearchCampaignResultsRequest,
    auth: AuthDep,
    uc: ListCampaignResultsDep,
) -> PaginatedResponse[CampaignResultResponse]:
    """Search the complete stage before ordering and pagination, without changing hit calls.

    Identity search is literal, case-insensitive substring matching on registration number or
    name. All measurement filters are ANDed. Bounds are inclusive, use the exact stored unit,
    and match only unqualified numeric values. QC ``not_tested`` means a cell holding a value (or a
    tested ND) with no verdict yet. ``overridden`` refers to the selected stage's outcome override.
    """
    out = result_to_response(
        await uc(
            ListCampaignResultsQuery(
                workspace_id=auth.workspace_id,
                campaign_id=campaign_id,
                stage_id=body.stage_id,
                outcome=tuple(body.outcome),
                order_by_channel_id=body.order_by,
                descending=body.direction == "desc",
                cursor_id=parse_cursor(body.cursor),
                limit=body.limit,
                filters=body.filters,
            ),
            auth=auth,
        )
    )
    return PaginatedResponse(
        items=[
            CampaignResultResponse.from_domain(r, out.outcomes.get(r.id)) for r in out.page.items
        ],
        next_cursor=out.page.next_cursor,
        total_count=out.page.total_count,
    )


@router.get("/{campaign_id}/results", response_model=PaginatedResponse[CampaignResultResponse])
async def list_campaign_results(
    campaign_id: uuid.UUID,
    auth: AuthDep,
    uc: ListCampaignResultsDep,
    stage_id: uuid.UUID | None = None,
    outcome: Annotated[
        list[StageOutcome] | None,
        Query(description="Verdict at stage_id to keep; may repeat to keep any of them"),
    ] = None,
    order_by: Annotated[
        uuid.UUID | None, Query(description="Channel id to sort by; omit for row order")
    ] = None,
    direction: Literal["asc", "desc"] = "asc",
    cursor: str | None = None,
    limit: Annotated[int, Query(le=MAX_PAGE_SIZE, ge=1)] = DEFAULT_PAGE_SIZE,
) -> PaginatedResponse[CampaignResultResponse]:
    """One page of a campaign's result rows, filtered and ordered server-side.

    ``outcome`` filters on the verdict at ``stage_id`` **after** overrides —
    the same value the row's ``stage_outcomes`` reports — and needs
    ``stage_id``. It may repeat (``&outcome=hit&outcome=miss``) to keep a row
    whose verdict is any of them; all four of ``hit``/``miss``/``untested``/
    ``pending`` is exactly the stage's ``population`` in the summary read.
    ``order_by`` names a channel: plain values sort first, then censored ones,
    with ND and excluded cells last in either direction.
    ``total_count`` is the filtered count, so a page can say "50 of 214".

    The full ``GET /campaigns/{id}`` read is unchanged; use this when you want
    a page rather than the matrix.
    """
    query = ListCampaignResultsQuery(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        stage_id=stage_id,
        outcome=tuple(outcome or ()),
        order_by_channel_id=order_by,
        descending=direction == "desc",
        cursor_id=parse_cursor(cursor),
        limit=clamp_limit(limit),
    )
    out = result_to_response(await uc(query, auth=auth))
    return PaginatedResponse(
        items=[
            CampaignResultResponse.from_domain(r, out.outcomes.get(r.id)) for r in out.page.items
        ],
        next_cursor=out.page.next_cursor,
        total_count=out.page.total_count,
    )


@router.patch("/{campaign_id}/results/{result_id}", response_model=ResultNoteResponse)
async def set_result_notes(
    campaign_id: uuid.UUID,
    result_id: uuid.UUID,
    body: SetResultNotesRequest,
    auth: AuthDep,
    uc: SetResultNotesDep,
) -> ResultNoteResponse:
    """Save (or, with ``null``, clear) the note on one result row, on any campaign status.

    Answers with the row's note and who saved it when. A save whose
    ``expected_notes`` is no longer the current note is a 409 ``StaleEditError``
    whose ``current`` is the note as it now stands.
    """
    cmd = SetResultNotesCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        result_id=result_id,
        notes=body.notes,
        expected_notes=body.expected_notes,
    )
    return ResultNoteResponse.from_domain(result_to_response(await uc(cmd, auth=auth)))


@router.get(
    "/{campaign_id}/results/{result_id}/notes/history",
    response_model=ResultNoteHistoryResponse,
)
async def get_result_note_history(
    campaign_id: uuid.UUID,
    result_id: uuid.UUID,
    auth: AuthDep,
    uc: GetResultNoteHistoryDep,
) -> ResultNoteHistoryResponse:
    """Every version of one row's note, newest first; ``versions[0]`` is the current note.

    A removed note is a version with ``notes: null``. A note written before saves
    were tracked is the oldest version, with ``edited_by`` and ``edited_at`` null.
    """
    query = GetResultNoteHistoryQuery(
        workspace_id=auth.workspace_id, campaign_id=campaign_id, result_id=result_id
    )
    return ResultNoteHistoryResponse.from_domain(result_to_response(await uc(query, auth=auth)))


@router.patch(
    "/{campaign_id}/results/{result_id}/cells/{channel_id}",
    status_code=204,
)
async def override_result_cell(
    campaign_id: uuid.UUID,
    result_id: uuid.UUID,
    channel_id: uuid.UUID,
    body: OverrideCellRequest,
    auth: AuthDep,
    uc: OverrideResultCellDep,
) -> Response:
    """Manually override a single (result, channel) measurement cell."""
    cmd = OverrideResultCellCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        result_id=result_id,
        channel_id=channel_id,
        value=body.value,
        value_qualifier=ValueQualifier(body.value_qualifier),
        unit=body.unit,
        reason=body.reason,
    )
    result_to_response(await uc(cmd, auth=auth))
    return Response(status_code=204)


@router.put("/{campaign_id}/qc-verdicts", response_model=QcVerdictCountsResponse)
async def set_qc_verdicts(
    campaign_id: uuid.UUID,
    body: SetQcVerdictsRequest,
    auth: AuthDep,
    uc: SetCellQcVerdictsDep,
) -> QcVerdictCountsResponse:
    """Put a person's QC verdict on many cells of a DRAFT campaign in one save.

    Each target is its ``channel_ids`` times its rows, named exactly one way: the
    ``result_ids`` key (``null`` = every row) or ``where``, the rows ``POST /results/search``
    returns for that stage, outcome and filters. A cell named twice counts once.
    ``not_tested`` clears a verdict whatever ``overwrite`` says; Verified/Failed over the
    other verdict needs ``overwrite`` (else ``kept``). A note goes with Verified/Failed
    only. A cell already holding the verdict is re-stamped only with ``overwrite`` and a
    ``note`` key whose note differs (``null`` = no note); omit ``note`` to leave it alone.

    404 on the first unknown result, column, stage or filter column, with nothing
    applied. 423 when the campaign is not a draft. Open to the managing app and to
    ChemCellar alike.
    """
    cmd = SetCellQcVerdictsCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        user_id=auth.user_id,
        verdict=None if body.verdict == "not_tested" else QcVerdict(body.verdict),
        targets=tuple(
            QcTarget(
                channel_ids=tuple(t.channel_ids),
                result_ids=None if t.result_ids is None else tuple(t.result_ids),
                where=None
                if t.where is None
                else RowSelection(
                    stage_id=t.where.stage_id,
                    outcome=tuple(t.where.outcome),
                    filters=t.where.filters,
                ),
            )
            for t in body.targets
        ),
        overwrite=body.overwrite,
        note=body.note if "note" in body.model_fields_set else UNSET,
    )
    return QcVerdictCountsResponse.from_domain(result_to_response(await uc(cmd, auth=auth)))


@router.post("/{campaign_id}/results", status_code=204)
async def add_result_row(
    campaign_id: uuid.UUID,
    body: AddResultRowRequest,
    auth: AuthDep,
    uc: AddResultRowDep,
    acting: ActingServiceDep,
) -> Response:
    """Add a new compound result row (manual attribution) to a DRAFT campaign."""
    cmd = AddResultRowCommand(
        acting_service=acting,
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        molecule_id=body.molecule_id,
    )
    result_to_response(await uc(cmd, auth=auth))
    return Response(status_code=204)


@router.delete("/{campaign_id}/results/{result_id}", status_code=204)
async def remove_result_row(
    campaign_id: uuid.UUID,
    result_id: uuid.UUID,
    auth: AuthDep,
    uc: RemoveResultRowDep,
    acting: ActingServiceDep,
) -> Response:
    """Remove a compound result row and its measurements from a DRAFT campaign."""
    cmd = RemoveResultRowCommand(
        acting_service=acting,
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        result_ids=[result_id],
    )
    result_to_response(await uc(cmd, auth=auth))
    return Response(status_code=204)


@router.post("/{campaign_id}/results/bulk-remove", status_code=204)
async def bulk_remove_result_rows(
    campaign_id: uuid.UUID,
    body: BulkRemoveResultsRequest,
    auth: AuthDep,
    uc: RemoveResultRowDep,
    acting: ActingServiceDep,
) -> Response:
    """Remove N compound result rows from a DRAFT campaign in one save.

    POST rather than DELETE because some proxies drop DELETE bodies. 404 on
    the first unknown result id, with nothing removed.
    """
    cmd = RemoveResultRowCommand(
        acting_service=acting,
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        result_ids=body.result_ids,
    )
    result_to_response(await uc(cmd, auth=auth))
    return Response(status_code=204)
