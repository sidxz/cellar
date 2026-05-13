"""Step 04 — Load storage locations (parent-before-child order)."""

from __future__ import annotations

import structlog

from ._context import WORKSPACE_ID, DemoContext
from ._result import unwrap_or_skip

logger = structlog.get_logger()


async def load(ctx: DemoContext) -> int:
    from cellar.application.inventory.manage_storage import (
        CreateStorageLocation,
        CreateStorageLocationCommand,
        ListStorageLocations,
        ListStorageLocationsQuery,
    )

    data: dict = ctx.data("storage_locations.json")
    create_uc = ctx.container[CreateStorageLocation]

    # Guard: if locations exist, backfill registry and skip
    list_uc = ctx.container[ListStorageLocations]
    existing = (await list_uc(ListStorageLocationsQuery(workspace_id=WORKSPACE_ID))).unwrap().items
    if existing:
        name_to_id = {loc.name: loc.id for loc in existing}
        for key, rec in data.items():
            loc_id = name_to_id.get(rec["name"])
            if loc_id:
                ctx.registry.put(key, loc_id)
        return 0

    created = 0

    # JSON is ordered parent-before-child, so iterate in insertion order
    for key, rec in data.items():
        parent_id = ctx.registry.get_optional(rec.get("parent_ref"))

        cmd = CreateStorageLocationCommand(
            workspace_id=WORKSPACE_ID,
            name=rec["name"],
            type=rec["type"],
            parent_id=parent_id,
            barcode=rec.get("barcode"),
            temperature=rec.get("temperature"),
            rows=rec.get("rows"),
            columns=rec.get("columns"),
            capacity=rec.get("capacity"),
        )
        result = await create_uc(cmd, auth=None)
        loc = unwrap_or_skip(result, "StorageLocation", key)
        if loc is not None:
            ctx.registry.put(key, loc.id)
            created += 1
            logger.info("storage_location.created", key=key, name=rec["name"])
        else:
            logger.debug("storage_location.exists", key=key, name=rec["name"])

    # Back-fill registry for any that already existed (conflict path)
    if created < len(data):
        list_uc = ctx.container[ListStorageLocations]
        query = ListStorageLocationsQuery(workspace_id=WORKSPACE_ID)
        all_locs_result = await list_uc(query)
        all_locs = all_locs_result.unwrap().items
        name_to_id = {loc.name: loc.id for loc in all_locs}
        for key, rec in data.items():
            if not ctx.registry.has(key):
                loc_id = name_to_id.get(rec["name"])
                if loc_id is not None:
                    ctx.registry.put(key, loc_id)

    return created
