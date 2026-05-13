"""Step 03 — Load salt catalog entries."""

from __future__ import annotations

import structlog

from ._context import WORKSPACE_ID, DemoContext
from ._result import unwrap_or_skip

logger = structlog.get_logger()


async def load(ctx: DemoContext) -> int:
    from cellar.application.workspace_config.create_salt_entry import (
        CreateSaltEntry,
        CreateSaltEntryCommand,
    )
    from cellar.application.workspace_config.list_salt_entries import (
        ListSaltEntries,
        ListSaltEntriesQuery,
    )

    data: dict = ctx.data("salts.json")
    create_uc = ctx.container[CreateSaltEntry]
    created = 0

    for key, rec in data.items():
        cmd = CreateSaltEntryCommand(
            workspace_id=WORKSPACE_ID,
            code=rec["code"],
            name=rec["name"],
            smiles=rec["smiles"],
            molecular_weight=rec["molecular_weight"],
            is_default=rec.get("is_default", False),
        )
        result = await create_uc(cmd, auth=None)
        entry = unwrap_or_skip(result, "SaltEntry", key)
        if entry is not None:
            ctx.registry.put(key, entry.id)
            created += 1
            logger.info("salt.created", key=key, code=rec["code"])
        else:
            logger.debug("salt.exists", key=key, code=rec["code"])

    # Back-fill registry for any that already existed (conflict path)
    if created < len(data):
        list_uc = ctx.container[ListSaltEntries]
        query = ListSaltEntriesQuery(workspace_id=WORKSPACE_ID)
        all_salts_result = await list_uc(query)
        all_salts = all_salts_result.unwrap()
        code_to_id = {s.code: s.id for s in all_salts}
        for key, rec in data.items():
            if not ctx.registry.has(key):
                salt_id = code_to_id.get(rec["code"])
                if salt_id is not None:
                    ctx.registry.put(key, salt_id)

    return created
