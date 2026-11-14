"""Recent-search endpoints — the current user's own search history."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from starlette.responses import Response

from cellar.application.personalization.clear_recent_searches import ClearRecentSearchesCommand
from cellar.application.personalization.list_recent_searches import ListRecentSearchesQuery
from cellar.application.personalization.record_recent_search import RecordRecentSearchCommand
from cellar.domain.personalization.recent_search import MAX_RECENT_SEARCHES, RecentSearch
from cellar.interface.dependencies import (
    AuthDep,
    ClearRecentSearchesDep,
    ListRecentSearchesDep,
    RecordRecentSearchDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/recent-searches", tags=["recent-searches"])


class RecentSearchResponse(BaseModel):
    id: uuid.UUID
    query: dict[str, Any]
    columns: dict[str, Any] | None
    result_count: int | None
    ran_at: datetime

    @classmethod
    def from_domain(cls, search: RecentSearch) -> RecentSearchResponse:
        return cls(
            id=search.id,
            query=search.query,
            columns=search.columns,
            result_count=search.result_count,
            ran_at=search.ran_at,
        )


class RecordRecentSearchBody(BaseModel):
    """The search as just run — the same ``query`` / ``columns`` a saved search
    stores. Not re-validated here: it is only ever replayed through
    ``/search/execute``, which validates it."""

    query: dict[str, Any]
    columns: dict[str, Any] | None = None
    result_count: int | None = Field(default=None, ge=0)


@router.get("", response_model=list[RecentSearchResponse])
async def list_recent_searches(
    auth: AuthDep,
    use_case: ListRecentSearchesDep,
    limit: int = Query(10, ge=1, le=MAX_RECENT_SEARCHES),
) -> list[RecentSearchResponse]:
    query = ListRecentSearchesQuery(
        workspace_id=auth.workspace_id, user_id=auth.user_id, limit=limit
    )
    searches = result_to_response(await use_case(query, auth=auth))
    return [RecentSearchResponse.from_domain(s) for s in searches]


@router.post("", response_model=RecentSearchResponse, status_code=201)
async def record_recent_search(
    auth: AuthDep,
    use_case: RecordRecentSearchDep,
    body: RecordRecentSearchBody,
) -> RecentSearchResponse:
    command = RecordRecentSearchCommand(
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
        query=body.query,
        columns=body.columns,
        result_count=body.result_count,
    )
    search = result_to_response(await use_case(command, auth=auth))
    return RecentSearchResponse.from_domain(search)


@router.delete("", status_code=204)
async def clear_recent_searches(auth: AuthDep, use_case: ClearRecentSearchesDep) -> Response:
    command = ClearRecentSearchesCommand(workspace_id=auth.workspace_id, user_id=auth.user_id)
    result_to_response(await use_case(command, auth=auth))
    return Response(status_code=204)
