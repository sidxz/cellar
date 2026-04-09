"""Step 09 — Load plate templates."""

from __future__ import annotations

import structlog

from ._context import USER_ID, WORKSPACE_ID, DemoContext
from ._result import unwrap_or_skip

logger = structlog.get_logger()


async def load(ctx: DemoContext) -> int:
    from chem_vault.application.screening.plate_templates import (
        CreatePlateTemplate,
        CreatePlateTemplateCommand,
        ListPlateTemplates,
        ListPlateTemplatesQuery,
    )
    from chem_vault.domain.screening_assay.enums import PlateFormat

    data = ctx.data("plate_templates.json")
    create_uc = ctx.container[CreatePlateTemplate]
    list_uc = ctx.container[ListPlateTemplates]
    created = 0

    for key, rec in data.items():
        result = await create_uc(
            CreatePlateTemplateCommand(
                workspace_id=WORKSPACE_ID,
                name=rec["name"],
                format=PlateFormat[rec["format"]],
                template_map=rec["template_map"],
                description=rec.get("description"),
                created_by=USER_ID,
            ),
            auth=ctx.auth,
        )
        entity = unwrap_or_skip(result, "PlateTemplate", key)

        if entity is not None:
            ctx.registry.put(key, entity.id)
            created += 1
            logger.info("plate_template.created", key=key, id=str(entity.id))
        else:
            # Conflict — look up by name
            list_result = await list_uc(
                ListPlateTemplatesQuery(workspace_id=WORKSPACE_ID)
            )
            templates = list_result.unwrap()
            match = next((t for t in templates if t.name == rec["name"]), None)
            if match is not None:
                ctx.registry.put(key, match.id)
                logger.info("plate_template.exists", key=key, id=str(match.id))
            else:
                logger.warning("plate_template.conflict_but_not_found", key=key)

    return created
