"""Step 14 — Generate readout data for screening runs.

Dose-response runs (mode=dose_response): well-based readout data generated via
Hill equation, enabling the ReadoutCalculationEngine to auto-fit curves.

Single-point runs (mode=single_point or omitted): molecule-level readout data
generated from random ranges, as before.
"""

from __future__ import annotations

import random

import structlog
from returns.result import Failure

from ._context import WORKSPACE_ID, DemoContext
from ._result import unwrap

logger = structlog.get_logger()


async def load(ctx: DemoContext) -> int:
    from chem_vault.application.screening.bulk_create_readout_data import (
        BulkCreateReadoutData,
        BulkCreateReadoutDataCommand,
        ReadoutDataItem,
    )
    from chem_vault.application.screening.get_protocol import (
        GetProtocol,
        GetProtocolQuery,
    )
    from chem_vault.application.screening.get_run import GetRun, GetRunQuery
    from chem_vault.application.screening.readout_calculation_engine import (
        ReadoutCalculationEngine,
    )
    from chem_vault.domain.screening_assay.enums import RunStatus

    data = ctx.data("readout_config.json")
    bulk_uc = ctx.container[BulkCreateReadoutData]
    get_protocol_uc = ctx.container[GetProtocol]
    get_run_uc = ctx.container[GetRun]
    engine = ctx.container[ReadoutCalculationEngine]
    total_created = 0

    for run_key, config in data.items():
        if run_key.startswith("_"):
            continue

        run_id = ctx.registry.get(run_key)
        protocol_ref = config["protocol_ref"]
        seed = config["seed"]
        mode = config.get("mode", "single_point")

        # Idempotency: only load data for completed/approved runs that have no data yet
        run_result = await get_run_uc(
            GetRunQuery(workspace_id=WORKSPACE_ID, run_id=run_id), auth=None
        )
        if isinstance(run_result, Failure):
            logger.warning("readout.run_not_found", run_key=run_key)
            continue
        run = run_result.unwrap()
        if run.status not in (RunStatus.COMPLETED, RunStatus.APPROVED):
            logger.info(
                "readout.skipped_status",
                run_key=run_key,
                status=run.status.value,
            )
            continue

        # Get protocol to find readout definition IDs
        protocol_id = ctx.registry.get(protocol_ref)
        proto_result = await get_protocol_uc(
            GetProtocolQuery(workspace_id=WORKSPACE_ID, protocol_id=protocol_id),
            auth=None,
        )
        protocol = unwrap(proto_result, "Protocol", protocol_ref)

        # Build a name -> readout_definition map
        rd_by_name = {rd.name: rd for rd in protocol.readout_definitions}

        if mode == "dose_response":
            n_created = await _load_dose_response_run(
                ctx=ctx,
                run=run,
                run_key=run_key,
                config=config,
                rd_by_name=rd_by_name,
                bulk_uc=bulk_uc,
                engine=engine,
                seed=seed,
            )
            total_created += n_created
        else:
            n_created = await _load_single_point_run(
                ctx=ctx,
                run=run,
                run_key=run_key,
                config=config,
                rd_by_name=rd_by_name,
                bulk_uc=bulk_uc,
                seed=seed,
            )
            total_created += n_created

    return total_created


async def _load_dose_response_run(
    *,
    ctx: DemoContext,
    run,
    run_key: str,
    config: dict,
    rd_by_name: dict,
    bulk_uc,
    engine,
    seed: int,
) -> int:
    """Generate well-based readout data for a dose-response run.

    For each well on the run: look up molecule via batch registry, compute
    % Inhibition from Hill equation, create ReadoutDataItem with well_id set.
    Then trigger the ReadoutCalculationEngine to normalize + auto-fit curves.
    """
    from chem_vault.application.screening.bulk_create_readout_data import (
        BulkCreateReadoutDataCommand,
        ReadoutDataItem,
    )

    ic50_map = config.get("ic50_nM", {})
    top = config.get("top", 100.0)
    bottom = config.get("bottom", 0.0)
    hill_slope = config.get("hill_slope", 1.0)
    noise_pct = config.get("noise_pct", 3.0)
    mol_keys = config.get("molecules", [])

    # Build batch_id -> mol_key reverse map from registry
    batch_to_mol_key: dict = {}
    for mol_key in mol_keys:
        mol_name = mol_key.removeprefix("mol_")
        batch_key = f"batch_{mol_name}_01"
        batch_id = ctx.registry.get_optional(batch_key)
        if batch_id is not None:
            batch_to_mol_key[batch_id] = mol_key

    # The % Inhibition readout definition
    pct_inh_rd = rd_by_name.get("% Inhibition")
    if pct_inh_rd is None:
        logger.warning("readout.no_pct_inhibition", run_key=run_key)
        return 0

    if not run.wells:
        logger.warning("readout.no_wells", run_key=run_key, msg="Plate setup may not have run")
        return 0

    rng = random.Random(seed)
    items = []

    for well in run.wells:
        if well.batch_id is None or well.concentration is None:
            continue

        mol_key = batch_to_mol_key.get(well.batch_id)
        if mol_key is None:
            continue

        mol_id = ctx.registry.get_optional(mol_key)
        if mol_id is None:
            continue

        ic50 = ic50_map.get(mol_key)
        if ic50 is None:
            continue

        mol_name = mol_key.removeprefix("mol_")
        batch_key = f"batch_{mol_name}_01"
        batch_id = ctx.registry.get_optional(batch_key)
        if batch_id is None:
            continue

        conc = well.concentration.value  # in nM

        # Hill equation: % Inhibition = bottom + (top - bottom) / (1 + (IC50/conc)^hill_slope)
        # At conc >> IC50: response -> top (high inhibition)
        # At conc << IC50: response -> bottom (low inhibition)
        inhibition = bottom + (top - bottom) / (1.0 + (ic50 / conc) ** hill_slope)
        noise = rng.gauss(0, (top - bottom) * noise_pct / 100.0)
        inhibition = max(bottom - 5.0, min(top + 5.0, inhibition + noise))

        items.append(
            ReadoutDataItem(
                run_id=run.id,
                well_id=well.id,
                molecule_id=mol_id,
                batch_id=batch_id,
                readout_definition_id=pct_inh_rd.id,
                value_numeric=round(inhibition, 2),
                value_qualifier="=",
            )
        )

    if not items:
        logger.info("readout.no_well_items", run_key=run_key)
        return 0

    result = await bulk_uc(
        BulkCreateReadoutDataCommand(workspace_id=WORKSPACE_ID, items=items),
        auth=None,
    )
    if isinstance(result, Failure):
        logger.warning(
            "readout.bulk_failed",
            run_key=run_key,
            error=str(result.failure()),
        )
        return 0

    bulk_result = result.unwrap()
    logger.info(
        "readout.well_based_loaded",
        run_key=run_key,
        success=bulk_result.success_count,
        errors=bulk_result.error_count,
    )

    # Trigger ReadoutCalculationEngine — normalizes + auto-fits dose-response curves
    engine_result = await engine.compute_for_run(run.id, workspace_id=WORKSPACE_ID)
    if isinstance(engine_result, Failure):
        logger.warning(
            "readout.engine_failed",
            run_key=run_key,
            error=str(engine_result.failure()),
        )
    else:
        computed = engine_result.unwrap()
        logger.info(
            "readout.engine_done",
            run_key=run_key,
            computed_count=len(computed),
        )

    # Also load extra single-point readouts (e.g. Selectivity Index for COX-2)
    extra = config.get("extra_readouts")
    if extra:
        extra_items = await _build_extra_readout_items(
            ctx=ctx,
            run=run,
            mol_keys=mol_keys,
            rd_by_name=rd_by_name,
            extra_readouts=extra,
            seed=seed + 1000,
        )
        if extra_items:
            extra_result = await bulk_uc(
                BulkCreateReadoutDataCommand(workspace_id=WORKSPACE_ID, items=extra_items),
                auth=None,
            )
            if isinstance(extra_result, Failure):
                logger.warning("readout.extra_failed", run_key=run_key, error=str(extra_result.failure()))
            else:
                er = extra_result.unwrap()
                logger.info("readout.extra_loaded", run_key=run_key, success=er.success_count)

    return bulk_result.success_count


async def _build_extra_readout_items(
    *,
    ctx: DemoContext,
    run,
    mol_keys: list,
    rd_by_name: dict,
    extra_readouts: dict,
    seed: int,
) -> list:
    """Build single-point readout items for non-Hill readouts (e.g. Selectivity Index)."""
    from chem_vault.application.screening.bulk_create_readout_data import ReadoutDataItem

    items = []
    rng = random.Random(seed)

    for mol_key in mol_keys:
        mol_id = ctx.registry.get_optional(mol_key)
        if mol_id is None:
            continue
        mol_name = mol_key.removeprefix("mol_")
        batch_key = f"batch_{mol_name}_01"
        batch_id = ctx.registry.get_optional(batch_key)
        if batch_id is None:
            continue

        for readout_name, value_range in extra_readouts.items():
            rd = rd_by_name.get(readout_name)
            if rd is None:
                continue
            value = rng.uniform(value_range["min"], value_range["max"])
            items.append(
                ReadoutDataItem(
                    run_id=run.id,
                    molecule_id=mol_id,
                    batch_id=batch_id,
                    readout_definition_id=rd.id,
                    value_numeric=round(value, 3),
                    value_qualifier="=",
                )
            )
    return items


async def _load_single_point_run(
    *,
    ctx: DemoContext,
    run,
    run_key: str,
    config: dict,
    rd_by_name: dict,
    bulk_uc,
    seed: int,
) -> int:
    """Generate molecule-level single-point readout data (original approach)."""
    from chem_vault.application.screening.bulk_create_readout_data import (
        BulkCreateReadoutDataCommand,
        ReadoutDataItem,
    )

    readout_ranges = config.get("readouts", {})
    mol_keys = config.get("molecules", [])

    items = []
    for mol_key in mol_keys:
        mol_id = ctx.registry.get_optional(mol_key)
        if mol_id is None:
            logger.warning("readout.mol_not_found", mol_key=mol_key)
            continue

        mol_name = mol_key.removeprefix("mol_")
        batch_key = f"batch_{mol_name}_01"
        batch_id = ctx.registry.get_optional(batch_key)
        if batch_id is None:
            logger.warning("readout.batch_not_found", mol_key=mol_key, batch_key=batch_key)
            continue

        for readout_name, value_range in readout_ranges.items():
            rd = rd_by_name.get(readout_name)
            if rd is None:
                logger.warning(
                    "readout.definition_not_found",
                    run_key=run_key,
                    readout_name=readout_name,
                )
                continue

            # Deterministic random value per molecule + readout combination
            rng = random.Random(seed + hash(mol_key + readout_name))
            value = rng.uniform(value_range["min"], value_range["max"])

            items.append(
                ReadoutDataItem(
                    run_id=run.id,
                    molecule_id=mol_id,
                    batch_id=batch_id,
                    readout_definition_id=rd.id,
                    value_numeric=round(value, 3),
                    value_qualifier="=",
                )
            )

    if not items:
        logger.info("readout.no_items", run_key=run_key)
        return 0

    result = await bulk_uc(
        BulkCreateReadoutDataCommand(workspace_id=WORKSPACE_ID, items=items),
        auth=None,
    )
    if isinstance(result, Failure):
        logger.warning(
            "readout.bulk_failed",
            run_key=run_key,
            error=str(result.failure()),
        )
        return 0

    bulk_result = result.unwrap()
    logger.info(
        "readout.loaded",
        run_key=run_key,
        success=bulk_result.success_count,
        errors=bulk_result.error_count,
    )
    return bulk_result.success_count
