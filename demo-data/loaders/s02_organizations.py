"""Step 02 — Load organizations."""

from __future__ import annotations

import structlog

from ._context import WORKSPACE_ID, DemoContext
from ._result import unwrap_or_skip

logger = structlog.get_logger()


async def load(ctx: DemoContext) -> int:
    from cellar.application.workspace_config.create_organization import (
        CreateOrganization,
        CreateOrganizationCommand,
    )
    from cellar.application.workspace_config.list_organizations import (
        ListOrganizations,
        ListOrganizationsQuery,
    )
    from cellar.domain.workspace_config.enums import OrganizationType

    data: dict = ctx.data("organizations.json")
    create_uc = ctx.container[CreateOrganization]
    created = 0

    for key, rec in data.items():
        cmd = CreateOrganizationCommand(
            workspace_id=WORKSPACE_ID,
            name=rec["name"],
            org_type=OrganizationType(rec["org_type"].lower()),
            contact_name=rec.get("contact_name"),
            contact_email=rec.get("contact_email"),
            notes=rec.get("notes"),
        )
        result = await create_uc(cmd, auth=None)
        org = unwrap_or_skip(result, "Organization", key)
        if org is not None:
            ctx.registry.put(key, org.id)
            created += 1
            logger.info("organization.created", key=key, name=rec["name"])
        else:
            logger.debug("organization.exists", key=key, name=rec["name"])

    # Back-fill registry for any that already existed (conflict path)
    if created < len(data):
        list_uc = ctx.container[ListOrganizations]
        query = ListOrganizationsQuery(workspace_id=WORKSPACE_ID)
        all_orgs_result = await list_uc(query)
        all_orgs = all_orgs_result.unwrap()
        name_to_id = {o.name: o.id for o in all_orgs}
        for key, rec in data.items():
            if not ctx.registry.has(key):
                org_id = name_to_id.get(rec["name"])
                if org_id is not None:
                    ctx.registry.put(key, org_id)

    return created
