"""Step 12 — Register physical plates."""

from __future__ import annotations

import structlog

from ._context import USER_ID, WORKSPACE_ID, DemoContext
from ._result import try_create

logger = structlog.get_logger()


async def load(ctx: DemoContext) -> int:
    from chem_vault.application.inventory.registered_plates import (
        RegisterPlate,
        RegisterPlateCommand,
    )

    data = ctx.data("plates.json")
    uc = ctx.container[RegisterPlate]
    created = 0

    for key, plate in data.items():
        cmd = RegisterPlateCommand(
            workspace_id=WORKSPACE_ID,
            barcode=plate["barcode"],
            plate_label=plate["plate_label"],
            format=plate["format"],
            plate_type=plate["plate_type"],
            registered_by=USER_ID,
            storage_location_id=ctx.registry.get_optional(plate.get("location_ref")),
            project_id=ctx.registry.get_optional(plate.get("project_ref")),
            template_id=ctx.registry.get_optional(plate.get("template_ref")),
            notes=plate.get("notes"),
        )

        entity = await try_create(uc(cmd, auth=None), "Plate", key)

        if entity is not None:
            ctx.registry.put(key, entity.id)
            created += 1
            logger.info("plate.created", key=key, barcode=plate["barcode"])
        else:
            logger.info("plate.skipped", key=key, barcode=plate["barcode"])

    return created
