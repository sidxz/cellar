"""Step 06 — Load research projects."""

from __future__ import annotations

import structlog

from ._context import USER_ID, WORKSPACE_ID, DemoContext
from ._result import unwrap_or_skip

logger = structlog.get_logger()


async def load(ctx: DemoContext) -> int:
    from cellar.application.research_organization.create_project import (
        CreateProject,
        CreateProjectCommand,
    )
    from cellar.application.research_organization.get_project import (
        ListProjects,
        ListProjectsQuery,
    )

    data: dict = ctx.data("projects.json")
    create_uc = ctx.container[CreateProject]
    created = 0

    for key, rec in data.items():
        cmd = CreateProjectCommand(
            workspace_id=WORKSPACE_ID,
            name=rec["name"],
            description=rec.get("description"),
            created_by=USER_ID,
        )
        result = await create_uc(cmd, auth=ctx.auth)
        project = unwrap_or_skip(result, "Project", key)
        if project is not None:
            ctx.registry.put(key, project.id)
            created += 1
            logger.info("project.created", key=key, name=rec["name"])
        else:
            logger.debug("project.exists", key=key, name=rec["name"])

    # Back-fill registry for any that already existed (conflict path)
    if created < len(data):
        list_uc = ctx.container[ListProjects]
        query = ListProjectsQuery(workspace_id=WORKSPACE_ID)
        all_projects_result = await list_uc(query)
        all_projects = all_projects_result.unwrap().items
        name_to_id = {p.name: p.id for p in all_projects}
        for key, rec in data.items():
            if not ctx.registry.has(key):
                proj_id = name_to_id.get(rec["name"])
                if proj_id is not None:
                    ctx.registry.put(key, proj_id)

    return created
