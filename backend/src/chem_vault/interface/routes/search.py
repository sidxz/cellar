"""Search execution endpoint."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from chem_vault.application.research_organization.execute_search import ExecuteSearchQuery
from chem_vault.interface.dependencies import AuthDep, ExecuteSearchDep
from chem_vault.interface.error_handlers import result_to_response
from chem_vault.interface.pagination import PaginatedResponse, clamp_limit, parse_cursor
from chem_vault.interface.routes.molecules import MoleculeResponse

router = APIRouter(prefix="/api/v1/search", tags=["search"])


class ExecuteSearchBody(BaseModel):
    query: dict[str, Any] | None = None
    saved_search_id: uuid.UUID | None = None
    protocol_columns: list[str] | None = None


@router.post("/execute")
async def execute_search(
    body: ExecuteSearchBody,
    auth: AuthDep,
    use_case: ExecuteSearchDep,
    cursor: str | None = None,
    limit: int | None = None,
) -> dict:
    """Execute a compound search -- inline query or saved search reference."""
    q = ExecuteSearchQuery(
        workspace_id=auth.workspace_id,
        saved_search_id=body.saved_search_id,
        query=body.query,
        protocol_columns=body.protocol_columns,
        cursor_id=parse_cursor(cursor),
        limit=clamp_limit(limit),
    )
    page = result_to_response(await use_case(q))
    response: dict = {
        "items": [MoleculeResponse.from_domain(m) for m in page.items],
        "next_cursor": page.next_cursor,
    }
    if page.activity_data:
        response["activity_data"] = page.activity_data
    return response
