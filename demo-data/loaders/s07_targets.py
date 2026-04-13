"""Step 07 — Load screening targets."""

from __future__ import annotations

import structlog

from ._context import WORKSPACE_ID, DemoContext
from ._result import unwrap_or_skip

logger = structlog.get_logger()


async def load(ctx: DemoContext) -> int:
    from chem_vault.application.screening.create_target import (
        CreateTarget,
        CreateTargetCommand,
    )
    from chem_vault.application.screening.get_target import (
        ListTargets,
        ListTargetsQuery,
    )

    data = ctx.data("targets.json")
    create_uc = ctx.container[CreateTarget]
    list_uc = ctx.container[ListTargets]
    created = 0

    for key, rec in data.items():
        result = await create_uc(
            CreateTargetCommand(
                workspace_id=WORKSPACE_ID,
                name=rec["name"],
                target_type=rec["target_type"],
                organism=rec.get("organism"),
                gene_name=rec.get("gene_name"),
                uniprot_id=rec.get("uniprot_id"),
                ncbi_gene_id=rec.get("ncbi_gene_id"),
                description=rec.get("description"),
                target_class=rec.get("target_class"),
            ),
            auth=ctx.auth,
        )
        entity = unwrap_or_skip(result, "Target", key)

        if entity is not None:
            ctx.registry.put(key, entity.id)
            created += 1
            logger.info("target.created", key=key, id=str(entity.id))
        else:
            # Conflict — look up by name to register the existing id
            list_result = await list_uc(
                ListTargetsQuery(workspace_id=WORKSPACE_ID), auth=ctx.auth
            )
            targets = list_result.unwrap()
            match = next((t for t in targets if t.name == rec["name"]), None)
            if match is not None:
                ctx.registry.put(key, match.id)
                logger.info("target.exists", key=key, id=str(match.id))
            else:
                logger.warning("target.conflict_but_not_found", key=key)

    return created
