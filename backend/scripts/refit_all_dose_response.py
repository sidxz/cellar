"""Re-fit every dose-response curve in the database.

Migration 033 truncated `dose_response_curves` (the old schema had no
identity link to a specific readout-def, so two DR readouts sharing a
curve_type were indistinguishable — no safe backfill exists). This
script reconstructs every curve from the preserved inputs:

    runs + wells + readout_data + protocols + readout_definitions

It walks every (workspace, protocol_id) pair whose protocol declares at
least one dose-response readout, loads each run for that protocol, and
calls the existing fitter. The fitter is wipe-then-rewrite per run, so
re-running the script is idempotent.

Side effects:
  * Populates `dose_response_curves` with `readout_definition_id` and
    `dose_response_config_snapshot` set on every row.
  * Does NOT touch `campaign_measurement` — open draft campaigns must be
    refreshed in the UI to re-link `source_curve_id` / `curve_snapshot`
    (closed campaigns keep their nulls until they're reopened).

Usage (from backend/):
    uv run python scripts/refit_all_dose_response.py
    uv run python scripts/refit_all_dose_response.py --dry-run
    uv run python scripts/refit_all_dose_response.py --workspace-id <uuid>
    uv run python scripts/refit_all_dose_response.py --protocol-id <uuid>

Idempotent: the fitter deletes its own previous output per run before
re-fitting, so partial runs and retries are safe.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

from returns.result import Failure
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cellar.application.screening.fit_dose_response import FitDoseResponseCurves
from cellar.infrastructure.persistence.settings import DatabaseSettings
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (
    SQLAlchemyDoseResponseCurveRepository,
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
from cellar.infrastructure.lmfit.curve_fitter import LmfitCurveFitter
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


async def _discover_dr_runs(
    session_factory: async_sessionmaker,
    workspace_id: uuid.UUID | None,
    protocol_id: uuid.UUID | None,
) -> list[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]:
    """Return (workspace_id, protocol_id, run_id) for every run on a
    protocol that declares at least one dose-response readout."""
    # Build the WHERE clause dynamically — asyncpg can't infer parameter
    # types from `:p IS NULL OR col = :p` patterns where the same param is
    # bound to NULL.
    filters = [
        "EXISTS ("
        " SELECT 1 FROM readout_definitions rd"
        " WHERE rd.protocol_id = p.id"
        " AND rd.data_type = 'dose_response'"
        " AND rd.dose_response_config IS NOT NULL"
        ")"
    ]
    params: dict[str, object] = {}
    if workspace_id is not None:
        filters.append("r.workspace_id = :workspace_id")
        params["workspace_id"] = workspace_id
    if protocol_id is not None:
        filters.append("r.protocol_id = :protocol_id")
        params["protocol_id"] = protocol_id

    stmt = text(
        f"""
        SELECT DISTINCT r.workspace_id, r.protocol_id, r.id AS run_id
        FROM runs r
        JOIN protocols p ON p.id = r.protocol_id
        WHERE {" AND ".join(filters)}
        ORDER BY r.workspace_id, r.protocol_id, r.id
        """
    )
    async with session_factory() as session:
        rows = (await session.execute(stmt, params)).all()
    return [(r.workspace_id, r.protocol_id, r.run_id) for r in rows]


async def _refit_one(
    *,
    session_factory: async_sessionmaker,
    workspace_id: uuid.UUID,
    protocol_id: uuid.UUID,
    run_id: uuid.UUID,
    dry_run: bool,
) -> tuple[int, int]:
    """Refit a single run. Returns (curves_written, warnings)."""
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        run_repo = SQLAlchemyRunRepository(uow)
        protocol_repo = SQLAlchemyProtocolRepository(uow)
        readout_repo = SQLAlchemyReadoutDataRepository(uow)
        curve_repo = SQLAlchemyDoseResponseCurveRepository(uow)
        fitter = FitDoseResponseCurves(
            uow=uow,
            curve_repo=curve_repo,
            curve_fitter=LmfitCurveFitter(),
        )

        run = await run_repo.find_by_id_in_workspace(workspace_id, run_id)
        if run is None:
            return (0, 0)
        protocol = await protocol_repo.find_by_id_in_workspace(workspace_id, protocol_id)
        if protocol is None:
            return (0, 0)
        readouts = await readout_repo.find_by_run(workspace_id, run_id)

        if dry_run:
            return (-1, 0)  # sentinel meaning "would have fit"

        result = await fitter.fit_for_run(
            run=run,
            protocol=protocol,
            readout_data=readouts,
            workspace_id=workspace_id,
        )
        if isinstance(result, Failure):
            print(f"  ! run {run_id}: fit failed — {result.failure()}")
            return (0, 0)
        unwrapped = result.unwrap()
        await uow.commit()
        return (len(unwrapped.curves), len(unwrapped.warnings))


async def _main(args: argparse.Namespace) -> None:
    settings = DatabaseSettings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        targets = await _discover_dr_runs(
            session_factory,
            workspace_id=uuid.UUID(args.workspace_id) if args.workspace_id else None,
            protocol_id=uuid.UUID(args.protocol_id) if args.protocol_id else None,
        )

        if not targets:
            print("No DR-protocol runs found. Nothing to refit.")
            return

        print(f"Found {len(targets)} run(s) with DR protocols.")
        if args.dry_run:
            print("Dry run — listing without fitting:")
            for ws, pid, rid in targets:
                print(f"  workspace={ws} protocol={pid} run={rid}")
            return

        total_curves = 0
        total_warnings = 0
        for i, (ws, pid, rid) in enumerate(targets, 1):
            print(f"[{i}/{len(targets)}] workspace={ws} protocol={pid} run={rid}")
            curves, warnings = await _refit_one(
                session_factory=session_factory,
                workspace_id=ws,
                protocol_id=pid,
                run_id=rid,
                dry_run=False,
            )
            total_curves += curves
            total_warnings += warnings
            if curves:
                print(f"  -> {curves} curve(s), {warnings} warning(s)")
            else:
                print("  -> no curves produced (no qualifying data?)")
        print(
            f"\nDone. Wrote {total_curves} curve(s) total across "
            f"{len(targets)} run(s); {total_warnings} warning(s)."
        )
    finally:
        await engine.dispose()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace-id",
        help="Limit to a single workspace UUID. Defaults to all workspaces.",
    )
    parser.add_argument(
        "--protocol-id",
        help="Limit to a single protocol UUID. Useful for smoke-testing one protocol first.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the runs that would be refit, without writing anything.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(_main(_parse_args()))
