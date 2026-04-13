"""Step 10 — Load inventory batches."""

from __future__ import annotations

import datetime

import structlog

from ._context import USER_ID, WORKSPACE_ID, DemoContext
from ._result import try_create

logger = structlog.get_logger()


async def load(ctx: DemoContext) -> int:
    from chem_vault.application.inventory.create_batch import (
        CreateBatch,
        CreateBatchCommand,
    )
    from chem_vault.application.inventory.get_batch import (
        ListBatchesByMolecule,
        ListBatchesByMoleculeQuery,
    )

    data = ctx.data("batches.json")
    items = {k: v for k, v in data.items() if not k.startswith("_")}
    create_uc = ctx.container[CreateBatch]
    list_uc = ctx.container[ListBatchesByMolecule]

    # Guard: if batches already exist for first molecule, backfill registry and skip
    first_rec = next(iter(items.values()))
    first_mol_id = ctx.registry.get(first_rec["molecule_ref"])
    check = await list_uc(
        ListBatchesByMoleculeQuery(workspace_id=WORKSPACE_ID, molecule_id=first_mol_id),
        auth=ctx.auth,
    )
    existing_batches = check.unwrap()
    if existing_batches:
        # Backfill all batch IDs into registry
        mol_batches: dict[str, list] = {}
        for key, rec in items.items():
            mol_ref = rec["molecule_ref"]
            mol_batches.setdefault(mol_ref, []).append(key)
        for mol_ref, keys in mol_batches.items():
            mol_id = ctx.registry.get(mol_ref)
            res = await list_uc(
                ListBatchesByMoleculeQuery(workspace_id=WORKSPACE_ID, molecule_id=mol_id),
                auth=ctx.auth,
            )
            batches = res.unwrap()
            for i, key in enumerate(keys):
                if i < len(batches):
                    ctx.registry.put(key, batches[i].id)
        return 0

    created = 0
    mol_batch_counts: dict[str, int] = {}

    for key, rec in data.items():
        if key.startswith("_"):
            continue

        molecule_ref = rec["molecule_ref"]
        molecule_id = ctx.registry.get(molecule_ref)

        # Count how many batches we expect per molecule (for idempotency)
        mol_batch_counts[molecule_ref] = mol_batch_counts.get(molecule_ref, 0) + 1

        synthesis_date = None
        if rec.get("synthesis_date"):
            synthesis_date = datetime.date.fromisoformat(rec["synthesis_date"])

        entity = await try_create(
            create_uc(
                CreateBatchCommand(
                    workspace_id=WORKSPACE_ID,
                    molecule_id=molecule_id,
                    source=rec["source"],
                    chemist=USER_ID,
                    amount_value=rec["amount_value"],
                    amount_unit=rec["amount_unit"],
                    purity=rec.get("purity"),
                    supplier_org_id=ctx.registry.get_optional(rec.get("supplier_ref")),
                    vendor_catalog_number=rec.get("vendor_catalog"),
                    vendor_lot_number=rec.get("vendor_lot"),
                    synthesis_date=synthesis_date,
                    notebook_reference=rec.get("notebook_reference"),
                    appearance=rec.get("appearance"),
                ),
                auth=ctx.auth,
            ),
            "Batch", key,
        )

        if entity is not None:
            ctx.registry.put(key, entity.id)
            created += 1
            logger.info("batch.created", key=key, id=str(entity.id))
        else:
            # Conflict — look up existing batches for this molecule
            list_result = await list_uc(
                ListBatchesByMoleculeQuery(
                    workspace_id=WORKSPACE_ID,
                    molecule_id=molecule_id,
                ),
                auth=ctx.auth,
            )
            batches = list_result.unwrap()
            # Use the expected index to pick the right batch
            expected_idx = mol_batch_counts[molecule_ref] - 1
            if expected_idx < len(batches):
                existing = batches[expected_idx]
                ctx.registry.put(key, existing.id)
                logger.info("batch.exists", key=key, id=str(existing.id))
            elif batches:
                # Fallback: register the last batch
                ctx.registry.put(key, batches[-1].id)
                logger.info("batch.exists_fallback", key=key, id=str(batches[-1].id))
            else:
                logger.warning("batch.conflict_but_not_found", key=key)

    return created
