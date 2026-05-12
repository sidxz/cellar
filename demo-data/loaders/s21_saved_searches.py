"""Step 21 — Load saved searches."""

from __future__ import annotations

import structlog

from ._context import USER_ID, WORKSPACE_ID, DemoContext
from ._result import unwrap_or_skip

logger = structlog.get_logger()


async def load(ctx: DemoContext) -> int:
    from cellar.application.research_organization.create_saved_search import (
        CreateSavedSearch,
        CreateSavedSearchCommand,
    )

    data: dict = ctx.data("saved_searches.json")
    create_uc = ctx.container[CreateSavedSearch]
    created = 0

    for key, rec in data.items():
        cmd = CreateSavedSearchCommand(
            workspace_id=WORKSPACE_ID,
            name=rec["name"],
            query=rec["query"],
            columns=rec.get("columns"),
            visibility=rec.get("visibility", "private"),
            project_id=ctx.registry.get_optional(rec.get("project_ref")),
            created_by=USER_ID,
        )
        result = await create_uc(cmd, auth=ctx.auth)
        entity = unwrap_or_skip(result, "SavedSearch", key)
        if entity is not None:
            ctx.registry.put(key, entity.id)
            created += 1
            logger.info("saved_search.created", key=key, name=rec["name"])
        else:
            logger.debug("saved_search.exists", key=key, name=rec["name"])

    return created
