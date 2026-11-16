"""Recompute every run with the current calculation engine, keeping chemists' curve edits.

Run it once per database after deploying a release that changes how runs are
calculated. Until a run is recomputed it keeps the numbers of the release that last
computed it: plate QC per readout x layer (``qc_metrics.plates``, which the Data summary
and the protocol averages read), outlier flags on computed rows, curves fitted from
sample wells only, dose-0 wells left out of fits, curve classes in dose order.

Per run, in one transaction:
  * normalization, plate QC (with control-compound potencies), replicate means and
    formulas are recomputed from the raw readout rows;
  * every dose-response curve is refitted in place (same id) with its own fit settings
    and its chemist-made exclusions carried to the same wells (``RefitCurvesKeepingEdits``);
    a series with fewer than four doses loses its curve, a newly fittable one gets one.

Locked and approved runs are skipped and listed: they change only through the app.
A run whose calculation fails is rolled back, listed, and the walk goes on.

Usage (from backend/):
    uv run python scripts/recompute_all_runs.py --dry-run
    uv run python scripts/recompute_all_runs.py --workspace-id <uuid>
    uv run python scripts/recompute_all_runs.py

Idempotent: a second pass recomputes the same values and finds nothing else to change.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

from returns.result import Failure
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cellar.application.screening.readout_calculation_engine import ReadoutCalculationEngine
from cellar.application.screening.refit_curves_keeping_edits import RefitCurvesKeepingEdits
from cellar.domain.screening_assay.plate_normalizer import PlateNormalizer
from cellar.domain.screening_assay.plate_quality import PlateQualityCalculator
from cellar.domain.screening_assay.replicate_aggregator import ReplicateAggregator
from cellar.domain.shared.errors import ConflictError
from cellar.infrastructure.computation.asteval_evaluator import AstevalFormulaEvaluator
from cellar.infrastructure.lmfit.curve_fitter import LmfitCurveFitter
from cellar.infrastructure.messaging.event_dispatcher import EventDispatcher
from cellar.infrastructure.persistence.settings import DatabaseSettings
from cellar.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (  # noqa: E501
    SQLAlchemyDoseResponseCurveRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.measured_curve_repository import (  # noqa: E501
    SQLAlchemyMeasuredCurveRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.melting_step_repository import (
    SQLAlchemyMeltingStepRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.readout_data_repository import (
    SQLAlchemyReadoutDataRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.run_repository import (
    SQLAlchemyRunRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


async def _runs(
    session_factory: async_sessionmaker, workspace_id: uuid.UUID | None
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """(workspace_id, run_id) of every run with readout rows, oldest first."""
    stmt = text(
        "SELECT r.workspace_id, r.id FROM runs r "
        "WHERE EXISTS (SELECT 1 FROM readout_data d WHERE d.run_id = r.id) "
        "AND (:every OR r.workspace_id = :ws) ORDER BY r.run_date, r.created_at"
    )
    params = {"every": workspace_id is None, "ws": workspace_id or uuid.UUID(int=0)}
    async with session_factory() as session:
        rows = (await session.execute(stmt, params)).all()
    return [(r.workspace_id, r.id) for r in rows]


async def _recompute(
    session_factory: async_sessionmaker, workspace_id: uuid.UUID, run_id: uuid.UUID
) -> str:
    """Recompute one run in its own transaction; a line for the progress log."""
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        run_repo = SQLAlchemyRunRepository(uow)
        readout_repo = SQLAlchemyReadoutDataRepository(uow)
        protocol_repo = SQLAlchemyProtocolRepository(uow)
        curve_repo = SQLAlchemyDoseResponseCurveRepository(uow)
        fitter = LmfitCurveFitter()
        engine = ReadoutCalculationEngine(
            uow=uow,
            formula_evaluator=AstevalFormulaEvaluator(),
            plate_normalizer=PlateNormalizer(),
            replicate_aggregator=ReplicateAggregator(),
            readout_data_repo=readout_repo,
            run_repo=run_repo,
            protocol_repo=protocol_repo,
            dispatcher=EventDispatcher(),
            plate_quality=PlateQualityCalculator(),
            melting_step_repo=SQLAlchemyMeltingStepRepository(uow),
            measured_curve_repo=SQLAlchemyMeasuredCurveRepository(uow),
            batch_repo=SQLAlchemyBatchRepository(uow),
            curve_fitter=fitter,
        )
        run = await run_repo.find_by_id_in_workspace(workspace_id, run_id)
        if run is None:
            return "skipped: gone"
        try:
            run.check_recalculation()
        except ConflictError as exc:
            return f"skipped: {exc.message}"
        protocol = await protocol_repo.find_by_id_in_workspace(workspace_id, run.protocol_id)
        if protocol is None:
            return "skipped: no protocol"
        before = await readout_repo.find_by_run(workspace_id, run_id)
        computed = await engine.compute_for_run(
            run_id, workspace_id=workspace_id, refit_curves=False
        )
        if isinstance(computed, Failure):
            return f"failed: {computed.failure().message}"  # left without a commit: rolled back
        after = await readout_repo.find_by_run(workspace_id, run_id)
        curves = await RefitCurvesKeepingEdits(curve_repo=curve_repo, curve_fitter=fitter).refit(
            run=run, protocol=protocol, before=before, after=after, only_changed=False
        )
        await uow.commit()
    note = curves.warning()
    return (
        f"ok: {curves.refitted} curves refitted, {curves.created} new, {curves.removed} removed"
        + (f"; {note}" if note else "")
    )


async def _main(args: argparse.Namespace) -> None:
    engine = create_async_engine(DatabaseSettings().database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        targets = await _runs(
            session_factory, uuid.UUID(args.workspace_id) if args.workspace_id else None
        )
        print(f"{len(targets)} run(s) with readout data.")
        if args.dry_run:
            for ws, rid in targets:
                print(f"  workspace={ws} run={rid}")
            return
        outcomes: dict[str, list[uuid.UUID]] = {"ok": [], "skipped": [], "failed": []}
        for i, (ws, rid) in enumerate(targets, 1):
            line = await _recompute(session_factory, ws, rid)
            outcomes[line.split(":", 1)[0]].append(rid)
            print(f"[{i}/{len(targets)}] run={rid} {line}")
        print(
            f"\nDone: {len(outcomes['ok'])} recomputed, {len(outcomes['skipped'])} skipped, "
            f"{len(outcomes['failed'])} failed."
        )
        for kind in ("skipped", "failed"):
            if outcomes[kind]:
                print(f"{kind.capitalize()}: {', '.join(map(str, outcomes[kind]))}")
    finally:
        await engine.dispose()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-id", help="Limit to one workspace. Defaults to all.")
    parser.add_argument(
        "--dry-run", action="store_true", help="List the runs it would recompute, write nothing."
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(_main(_parse_args()))
