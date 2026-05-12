"""Step 16 — Create synthesis routes with reaction steps."""

from __future__ import annotations

import structlog
from returns.result import Failure

from ._context import WORKSPACE_ID, DemoContext
from ._result import unwrap_or_skip

logger = structlog.get_logger()


async def load(ctx: DemoContext) -> int:
    from cellar.application.chemical_registration.synthesis_routes import (
        AddReactionStep,
        AddReactionStepCommand,
        CreateSynthesisRoute,
        CreateSynthesisRouteCommand,
    )

    data = ctx.data("synthesis_routes.json")
    create_uc = ctx.container[CreateSynthesisRoute]
    add_step_uc = ctx.container[AddReactionStep]
    created = 0

    for key, route_data in data.items():
        cmd = CreateSynthesisRouteCommand(
            workspace_id=WORKSPACE_ID,
            target_molecule_id=ctx.registry.get(route_data["molecule_ref"]),
            name=route_data["name"],
            description=route_data.get("description"),
            route_type=route_data.get("route_type", "linear"),
            scale=route_data.get("scale"),
            source=route_data.get("source", "manual"),
            source_reference=route_data.get("source_reference"),
        )

        result = await create_uc(cmd, auth=ctx.auth)
        entity = unwrap_or_skip(result, "SynthesisRoute", key)

        if entity is None:
            logger.info("synthesis_route.skipped", key=key)
            continue

        route_id = entity.id
        ctx.registry.put(key, route_id)
        created += 1
        logger.info("synthesis_route.created", key=key, name=route_data["name"])

        # Add reaction steps
        for step in route_data.get("steps", []):
            step_cmd = AddReactionStepCommand(
                workspace_id=WORKSPACE_ID,
                route_id=route_id,
                step_number=step["step_number"],
                name=step.get("name"),
                named_reaction=step.get("named_reaction"),
                product_description=step.get("product_description"),
                conditions=step.get("conditions"),
                reagents=step.get("reagents", []),
                notes=step.get("notes"),
            )

            step_result = await add_step_uc(step_cmd, auth=ctx.auth)
            if isinstance(step_result, Failure):
                logger.warning(
                    "synthesis_route.step_failed",
                    key=key,
                    step_number=step["step_number"],
                    error=str(step_result.failure()),
                )
            else:
                logger.info(
                    "synthesis_route.step_added",
                    key=key,
                    step_number=step["step_number"],
                    name=step.get("name"),
                )

    return created
