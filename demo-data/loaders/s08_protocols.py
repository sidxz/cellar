"""Step 08 — Load screening protocols."""

from __future__ import annotations

import structlog

from ._context import WORKSPACE_ID, DemoContext
from ._result import unwrap_or_skip

logger = structlog.get_logger()


async def load(ctx: DemoContext) -> int:
    from cellar.application.screening.create_protocol import (
        CreateProtocol,
        CreateProtocolCommand,
    )
    from cellar.application.screening.get_protocol import (
        ListProtocols,
        ListProtocolsQuery,
    )
    from cellar.application.screening.manage_protocol import (
        PublishProtocol,
        PublishProtocolCommand,
    )

    data = ctx.data("protocols.json")
    create_uc = ctx.container[CreateProtocol]
    list_uc = ctx.container[ListProtocols]
    publish_uc = ctx.container[PublishProtocol]
    created = 0

    for key, rec in data.items():
        target_id = ctx.registry.get_optional(rec.get("target_ref"))

        result = await create_uc(
            CreateProtocolCommand(
                workspace_id=WORKSPACE_ID,
                name=rec["name"],
                description=rec.get("description"),
                protocol_type=rec["protocol_type"],
                target_id=target_id,
                category=rec.get("category"),
                readout_definitions=rec.get("readout_definitions", []),
                condition_definitions=rec.get("condition_definitions", []),
            ),
            auth=ctx.auth,
        )
        entity = unwrap_or_skip(result, "Protocol", key)

        if entity is not None:
            ctx.registry.put(key, entity.id)
            _register_readout_defs(ctx, key, entity)
            created += 1
            logger.info("protocol.created", key=key, id=str(entity.id))

            # Publish if requested
            if rec.get("publish"):
                pub_result = await publish_uc(
                    PublishProtocolCommand(
                        workspace_id=WORKSPACE_ID,
                        protocol_id=entity.id,
                    ),
                    auth=ctx.auth,
                )
                pub_result.unwrap()
                logger.info("protocol.published", key=key)

            # Set recommended hit criteria if defined
            hit_criteria = rec.get("recommended_hit_criteria")
            if hit_criteria:
                from cellar.application.screening.manage_protocol import (
                    UpdateProtocol,
                    UpdateProtocolCommand,
                )
                update_uc = ctx.container[UpdateProtocol]
                cr = await update_uc(
                    UpdateProtocolCommand(
                        workspace_id=WORKSPACE_ID,
                        protocol_id=entity.id,
                        recommended_hit_criteria=hit_criteria,
                    ),
                    auth=ctx.auth,
                )
                cr.unwrap()
                logger.info("protocol.hit_criteria_set", key=key, count=len(hit_criteria))
        else:
            # Conflict — look up existing protocol by name
            list_result = await list_uc(
                ListProtocolsQuery(workspace_id=WORKSPACE_ID), auth=ctx.auth
            )
            protocols = list_result.unwrap()
            match = next((p for p in protocols if p.name == rec["name"]), None)
            if match is not None:
                ctx.registry.put(key, match.id)
                _register_readout_defs(ctx, key, match)
                logger.info("protocol.exists", key=key, id=str(match.id))
            else:
                logger.warning("protocol.conflict_but_not_found", key=key)

    return created


def _register_readout_defs(ctx: DemoContext, proto_key: str, protocol: object) -> None:
    """Register each readout definition id with key ``{proto_key}__rd__{name}``."""
    for rd in protocol.readout_definitions:
        rd_key = f"{proto_key}__rd__{rd.name}"
        ctx.registry.put(rd_key, rd.id)
