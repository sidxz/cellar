"""Step 11 — Load inventory samples."""

from __future__ import annotations

import structlog

from ._context import WORKSPACE_ID, DemoContext
from ._result import try_create

logger = structlog.get_logger()


async def load(ctx: DemoContext) -> int:
    from chem_vault.application.inventory.create_sample import (
        CreateSample,
        CreateSampleCommand,
    )

    data = ctx.data("samples.json")
    create_uc = ctx.container[CreateSample]
    created = 0

    for key, rec in data.items():
        entity = await try_create(
            create_uc(
                CreateSampleCommand(
                    workspace_id=WORKSPACE_ID,
                    batch_id=ctx.registry.get(rec["batch_ref"]),
                    barcode=rec["barcode"],
                    container_type=rec["container_type"],
                    amount_value=rec["amount_value"],
                    amount_unit=rec["amount_unit"],
                    concentration_value=rec.get("concentration_value"),
                    concentration_unit=rec.get("concentration_unit"),
                    solvent=rec.get("solvent"),
                    location_id=ctx.registry.get_optional(rec.get("location_ref")),
                ),
                auth=ctx.auth,
            ),
            "Sample", key,
        )

        if entity is not None:
            ctx.registry.put(key, entity.id)
            created += 1
            logger.info("sample.created", key=key, id=str(entity.id))

    # Backfill registry for samples that already existed (by barcode)
    if created < len(data):
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import async_sessionmaker
        from chem_vault.infrastructure.persistence.sqlalchemy.inventory.models import SampleModel

        session_factory = ctx.container[async_sessionmaker]
        barcode_to_key = {rec["barcode"]: key for key, rec in data.items()}
        async with session_factory() as session:
            stmt = select(SampleModel).where(
                SampleModel.workspace_id == WORKSPACE_ID,
                SampleModel.barcode.in_(list(barcode_to_key.keys())),
            )
            result = await session.execute(stmt)
            for model in result.scalars().all():
                k = barcode_to_key.get(model.barcode)
                if k and not ctx.registry.has(k):
                    ctx.registry.put(k, model.id)

    return created
