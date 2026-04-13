"""Step 13 — Create screening runs, apply state transitions, and set up dose-response plates."""

from __future__ import annotations

from datetime import date

import structlog
from returns.result import Failure

from ._context import WORKSPACE_ID, DemoContext
from ._result import unwrap_or_skip

logger = structlog.get_logger()


async def load(ctx: DemoContext) -> int:
    from chem_vault.application.screening.create_run import (
        CreateRun,
        CreateRunCommand,
    )
    from chem_vault.application.screening.get_run import GetRun, GetRunQuery
    from chem_vault.application.screening.manage_run import (
        ApproveRun,
        ApproveRunCommand,
        CompleteRun,
        CompleteRunCommand,
        RejectRun,
        RejectRunCommand,
        StartRun,
        StartRunCommand,
    )
    from chem_vault.application.screening.plate_setup import (
        CompoundAssignment,
        SetUpRunPlate,
        SetUpRunPlateCommand,
    )

    data = ctx.data("runs.json")
    create_uc = ctx.container[CreateRun]
    get_uc = ctx.container[GetRun]
    start_uc = ctx.container[StartRun]
    complete_uc = ctx.container[CompleteRun]
    approve_uc = ctx.container[ApproveRun]
    reject_uc = ctx.container[RejectRun]
    setup_uc = ctx.container[SetUpRunPlate]
    created = 0

    for key, run_data in data.items():
        det_id = ctx.registry.deterministic(key)

        # Idempotency: check if a run with this deterministic ID already exists
        existing = await get_uc(
            GetRunQuery(workspace_id=WORKSPACE_ID, run_id=det_id), auth=None
        )
        if not isinstance(existing, Failure):
            ctx.registry.put(key, det_id)
            logger.info("run.skipped", key=key, reason="already_exists")
            continue

        cmd = CreateRunCommand(
            workspace_id=WORKSPACE_ID,
            protocol_id=ctx.registry.get(run_data["protocol_ref"]),
            run_date=date.fromisoformat(run_data["run_date"]),
            performed_at_org_id=ctx.registry.get_optional(run_data.get("org_ref")),
            plate_format=run_data.get("plate_format"),
            conditions=run_data.get("conditions"),
            notes=run_data.get("notes"),
        )

        result = await create_uc(cmd, auth=ctx.auth)
        entity = unwrap_or_skip(result, "Run", key)

        if entity is None:
            logger.info("run.skipped", key=key, reason="conflict")
            continue

        run_id = entity.id
        ctx.registry.put(key, run_id)
        created += 1
        logger.info("run.created", key=key, run_id=str(run_id))

        # Apply state transitions
        for transition in run_data.get("transitions", []):
            if transition == "start":
                t_result = await start_uc(
                    StartRunCommand(workspace_id=WORKSPACE_ID, run_id=run_id),
                    auth=ctx.auth,
                )
            elif transition == "complete":
                t_result = await complete_uc(
                    CompleteRunCommand(workspace_id=WORKSPACE_ID, run_id=run_id),
                    auth=ctx.auth,
                )
            elif transition == "approve":
                t_result = await approve_uc(
                    ApproveRunCommand(workspace_id=WORKSPACE_ID, run_id=run_id),
                    auth=ctx.auth,
                )
            elif transition == "reject":
                t_result = await reject_uc(
                    RejectRunCommand(
                        workspace_id=WORKSPACE_ID,
                        run_id=run_id,
                        reason=run_data.get("reject_reason", "QC failure"),
                    ),
                    auth=ctx.auth,
                )
            else:
                logger.warning("run.unknown_transition", key=key, transition=transition)
                continue

            if isinstance(t_result, Failure):
                logger.warning(
                    "run.transition_failed",
                    key=key,
                    transition=transition,
                    error=str(t_result.failure()),
                )
            else:
                logger.info("run.transition", key=key, transition=transition)

        # Set up plate for dose-response runs
        plate_setup = run_data.get("plate_setup")
        if plate_setup:
            molecules = plate_setup["molecules"]
            concentrations = plate_setup["concentrations_nM"]
            rows = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

            compound_assignments = []
            for i, mol_name in enumerate(molecules):
                row = rows[i]
                # One row of wells, one per concentration step
                well_positions = [f"{row}{col}" for col in range(1, len(concentrations) + 1)]
                compound_assignments.append(
                    CompoundAssignment(
                        molecule_ref=mol_name,
                        well_positions=well_positions,
                    )
                )

            setup_result = await setup_uc(
                SetUpRunPlateCommand(
                    workspace_id=WORKSPACE_ID,
                    run_id=run_id,
                    compound_assignments=compound_assignments,
                    concentration_series=concentrations,
                    concentration_unit="nM",
                ),
                auth=ctx.auth,
            )
            if isinstance(setup_result, Failure):
                logger.warning(
                    "run.plate_setup_failed",
                    key=key,
                    error=str(setup_result.failure()),
                )
            else:
                info = setup_result.unwrap()
                logger.info(
                    "run.plate_setup_done",
                    key=key,
                    wells_created=info["wells_created"],
                    compounds_assigned=info["compounds_assigned"],
                    unresolved=info.get("unresolved", []),
                )

                # Add control wells directly via SQL for normalization + Z-prime
                from sqlalchemy.ext.asyncio import async_sessionmaker
                from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models import (
                    PlateModel, WellModel,
                )
                from sqlalchemy import select
                import uuid as _uuid

                sf = ctx.container[async_sessionmaker]
                async with sf() as session:
                    # Find the plate we just created
                    stmt = select(PlateModel).where(PlateModel.run_id == run_id)
                    plate_result = await session.execute(stmt)
                    plate_model = plate_result.scalars().first()
                    if plate_model:
                        # Add 4 positive + 4 negative control wells in last 2 columns
                        last_col = len(concentrations) + 1
                        control_rows = ["A", "B", "C", "D"]
                        for r in control_rows:
                            session.add(WellModel(
                                id=_uuid.uuid4(), plate_id=plate_model.id,
                                row=r, column=last_col,
                                well_type="positive_control",
                            ))
                            session.add(WellModel(
                                id=_uuid.uuid4(), plate_id=plate_model.id,
                                row=r, column=last_col + 1,
                                well_type="negative_control",
                            ))
                        await session.commit()
                        logger.info("run.controls_added", key=key, pos=4, neg=4)

    return created
