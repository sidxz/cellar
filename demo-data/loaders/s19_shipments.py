"""Step 19 — Load shipments and advance through lifecycle transitions."""

from __future__ import annotations

from datetime import date

import structlog

from ._context import USER_ID, WORKSPACE_ID, DemoContext
from ._result import unwrap_or_skip

logger = structlog.get_logger()


async def load(ctx: DemoContext) -> int:
    from cellar.application.inventory.shipments import (
        CreateShipment,
        CreateShipmentCommand,
        DeliverShipment,
        DeliverShipmentCommand,
        MarkInTransitCommand,
        MarkShipmentInTransit,
        ShipmentItemInput,
        ShipShipment,
        ShipShipmentCommand,
    )
    from cellar.domain.inventory.enums import ShipmentItemType

    data: dict = ctx.data("shipments.json")
    create_uc = ctx.container[CreateShipment]
    ship_uc = ctx.container[ShipShipment]
    in_transit_uc = ctx.container[MarkShipmentInTransit]
    deliver_uc = ctx.container[DeliverShipment]
    created = 0

    for key, rec in data.items():
        items = [
            ShipmentItemInput(
                item_type=ShipmentItemType.SAMPLE,
                item_id=ctx.registry.get(sample_ref),
                amount_value=5.0,
                amount_unit="mg",
            )
            for sample_ref in rec.get("sample_refs", [])
        ]

        expected_date = None
        if rec.get("expected_arrival_date"):
            expected_date = date.fromisoformat(rec["expected_arrival_date"])

        cmd = CreateShipmentCommand(
            workspace_id=WORKSPACE_ID,
            sender_id=USER_ID,
            destination_org_id=ctx.registry.get(rec["destination_ref"]),
            carrier=rec.get("carrier"),
            expected_arrival_date=expected_date,
            shipping_conditions=rec.get("shipping_conditions"),
            notes=rec.get("notes"),
            items=items,
        )
        result = await create_uc(cmd, auth=ctx.auth)
        entity = unwrap_or_skip(result, "Shipment", key)
        if entity is None:
            logger.debug("shipment.exists", key=key)
            continue

        shipment_id = entity.id
        ctx.registry.put(key, shipment_id)
        created += 1
        logger.info("shipment.created", key=key, destination=rec["destination_ref"])

        transitions = rec.get("transitions", [])

        for transition in transitions:
            try:
                if transition == "ship":
                    await ship_uc(
                        ShipShipmentCommand(
                            workspace_id=WORKSPACE_ID,
                            shipment_id=shipment_id,
                            tracking_number=rec.get("tracking_number", "DEMO-TRACK-000"),
                        ),
                        auth=ctx.auth,
                    )
                elif transition == "in_transit":
                    await in_transit_uc(
                        MarkInTransitCommand(
                            workspace_id=WORKSPACE_ID,
                            shipment_id=shipment_id,
                        ),
                        auth=ctx.auth,
                    )
                elif transition == "deliver":
                    await deliver_uc(
                        DeliverShipmentCommand(
                            workspace_id=WORKSPACE_ID,
                            shipment_id=shipment_id,
                        ),
                        auth=ctx.auth,
                    )
                logger.debug("shipment.transition", key=key, transition=transition)
            except Exception:
                logger.warning(
                    "shipment.transition_failed",
                    key=key,
                    transition=transition,
                    exc_info=True,
                )

    return created
