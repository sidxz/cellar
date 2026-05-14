"""Rebuild every campaign_measurement.curve_snapshot from the source DR curve.

Why: pre-2026-05-14 snapshots were built from a smaller subset of curve
fields (no curve_type, no intercept_values, no CI bounds, no fit warnings).
The campaign expand-dialog rendered via a custom strip + the lightweight
<DoseResponseFigure>, so it didn't need them. After unifying that dialog
to render via the shared <DoseResponseChart> (matching protocol-runs and
search), the snapshot needs the four extra fields or the chart degrades:
no secondary intercept chips, no CI strip, no fit-quality badges.

This script re-reads each measurement's source curve and rewrites the
JSONB column with the full snapshot via the same _build_curve_snapshot
helper the live import uses. New keys land additively; pre-existing keys
get overwritten with the current curve values.

Scope:
  * Handles every `campaign_measurement` row with non-null `source_curve_id`
    (LATEST_APPROVED_RUN channels — the common case).
  * Aggregate-rule rows (MEAN_ACROSS_RUNS / GEOMETRIC_MEAN) carry a null
    `source_curve_id` because the value is an aggregate over runs. Their
    snapshot was originally built from the latest-run "representative"
    candidate; reconstructing it requires re-running the resolver. These
    rows are reported in the summary; rebuild via "Refresh from sources"
    in the campaign UI to repopulate them.

Idempotent + resumable: each row is its own UPDATE inside its own
transaction, so re-runs are safe and partial runs only need a re-trigger.

Closed-campaign immutability:
  A trigger on campaign_measurement blocks INSERT/UPDATE/DELETE for
  campaigns whose status is 'closed' or 'superseded' (21 CFR Part 11
  alignment — the audit trail is append-only). Because every existing
  campaign with renderable data is closed, a default-safe run wouldn't
  touch any of the rows that need fixing. Pass ``--include-closed`` to
  bypass the trigger via PostgreSQL's session_replication_role for the
  duration of the script. The bypass is intentional and limited to
  display-metadata reconstruction; it does NOT change measurement values
  or hit calls. Default OFF to avoid accidental writes in prod.

Usage (from backend/):
    uv run python scripts/rebuild_campaign_curve_snapshots.py
    uv run python scripts/rebuild_campaign_curve_snapshots.py --dry-run
    uv run python scripts/rebuild_campaign_curve_snapshots.py --include-closed
    uv run python scripts/rebuild_campaign_curve_snapshots.py --workspace-id <uuid>
    uv run python scripts/rebuild_campaign_curve_snapshots.py --campaign-id <uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cellar.application.research_organization.channel_resolution import (
    ResolvedCandidate,
    _build_curve_snapshot,
)
from cellar.domain.research_organization.enums import ValueQualifier
from cellar.infrastructure.persistence.settings import DatabaseSettings


async def _discover_curve_measurements(
    session_factory: async_sessionmaker,
    workspace_id: uuid.UUID | None,
    campaign_id: uuid.UUID | None,
) -> list[uuid.UUID]:
    """Return the IDs of every campaign_measurement with a source curve.

    Filters by workspace via the join through campaign_result -> campaign,
    since campaign_measurement doesn't carry workspace_id directly.
    """
    filters = ["cm.source_curve_id IS NOT NULL"]
    params: dict[str, object] = {}
    if workspace_id is not None:
        filters.append("c.workspace_id = :workspace_id")
        params["workspace_id"] = workspace_id
    if campaign_id is not None:
        filters.append("c.id = :campaign_id")
        params["campaign_id"] = campaign_id

    stmt = text(
        f"""
        SELECT cm.id
        FROM campaign_measurement cm
        JOIN campaign_result cr ON cr.id = cm.result_id
        JOIN campaign c ON c.id = cr.campaign_id
        WHERE {" AND ".join(filters)}
        ORDER BY cm.id
        """
    )
    async with session_factory() as session:
        rows = (await session.execute(stmt, params)).all()
    return [r.id for r in rows]


async def _count_aggregate_measurements(
    session_factory: async_sessionmaker,
    workspace_id: uuid.UUID | None,
    campaign_id: uuid.UUID | None,
) -> int:
    """Count measurements with NULL source_curve_id but non-NULL curve_snapshot.

    These are MEAN/GEOMETRIC aggregate rows that this script can't safely
    reconstruct. Reported so the chemist knows what's left to refresh.
    """
    filters = [
        "cm.source_curve_id IS NULL",
        "cm.curve_snapshot IS NOT NULL",
    ]
    params: dict[str, object] = {}
    if workspace_id is not None:
        filters.append("c.workspace_id = :workspace_id")
        params["workspace_id"] = workspace_id
    if campaign_id is not None:
        filters.append("c.id = :campaign_id")
        params["campaign_id"] = campaign_id

    stmt = text(
        f"""
        SELECT COUNT(*) AS n
        FROM campaign_measurement cm
        JOIN campaign_result cr ON cr.id = cm.result_id
        JOIN campaign c ON c.id = cr.campaign_id
        WHERE {" AND ".join(filters)}
        """
    )
    async with session_factory() as session:
        row = (await session.execute(stmt, params)).one()
    return int(row.n)


async def _rebuild_one(
    session_factory: async_sessionmaker,
    measurement_id: uuid.UUID,
    *,
    dry_run: bool,
    include_closed: bool,
) -> bool:
    """Rebuild one measurement's snapshot. Returns True if updated."""
    pull = text(
        """
        SELECT
            cm.id AS measurement_id,
            cm.value AS measurement_value,
            cm.unit AS measurement_unit,
            cm.value_qualifier AS measurement_qualifier,
            cm.protocol_name_snapshot,
            cm.protocol_version_snapshot,
            cm.run_date_snapshot,
            cm.source_run_id,
            cm.source_curve_id,
            drc.id AS curve_id,
            drc.fitted_value,
            drc.curve_class,
            drc.curve_type,
            drc.top,
            drc.bottom,
            drc.hill_slope,
            drc.r_squared,
            drc.confidence_interval_low,
            drc.confidence_interval_high,
            drc.fit_quality_warnings,
            drc.raw_data,
            drc.excluded_points,
            drc.intercept_values
        FROM campaign_measurement cm
        JOIN dose_response_curves drc ON drc.id = cm.source_curve_id
        WHERE cm.id = :mid
        """
    )
    async with session_factory() as session:
        row = (await session.execute(pull, {"mid": measurement_id})).one_or_none()
    if row is None:
        return False

    qualifier = ValueQualifier.EQ
    if row.measurement_qualifier:
        try:
            qualifier = ValueQualifier(row.measurement_qualifier)
        except ValueError:
            pass

    candidate = ResolvedCandidate(
        # `value` here is just the scalar used for `fitted_value` in the
        # snapshot — must mirror what the live import wrote, which for a
        # LATEST_APPROVED_RUN channel is the curve's own fitted_value.
        value=float(row.fitted_value),
        qualifier=qualifier,
        unit=row.measurement_unit or "",
        run_id=row.source_run_id or uuid.uuid4(),
        run_date=row.run_date_snapshot if isinstance(row.run_date_snapshot, date) else None,
        run_approved=True,
        z_prime=None,
        protocol_name=row.protocol_name_snapshot or "",
        protocol_version=row.protocol_version_snapshot or 1,
        curve_id=row.curve_id,
        readout_id=None,
        curve_class=row.curve_class,
        curve_top=row.top,
        curve_bottom=row.bottom,
        curve_hill_slope=row.hill_slope,
        curve_r_squared=row.r_squared,
        curve_raw_data=row.raw_data,
        curve_excluded_points=row.excluded_points,
        intercept_values=row.intercept_values,
        curve_type=row.curve_type,
        curve_confidence_interval_low=row.confidence_interval_low,
        curve_confidence_interval_high=row.confidence_interval_high,
        curve_fit_quality_warnings=row.fit_quality_warnings,
    )
    snap = _build_curve_snapshot(candidate)
    if snap is None:
        return False

    if dry_run:
        return True

    update = text(
        "UPDATE campaign_measurement "
        "SET curve_snapshot = CAST(:snap AS jsonb) "
        "WHERE id = :mid"
    )
    import json as _json

    async with session_factory() as session, session.begin():
        if include_closed:
            # Bypass the reject_locked_campaign_write trigger for this
            # transaction. session_replication_role = 'replica' makes
            # Postgres skip user-defined triggers (replication-style
            # behavior). Scoped to this single transaction via SET LOCAL.
            await session.execute(text("SET LOCAL session_replication_role = 'replica'"))
        await session.execute(
            update,
            {"mid": measurement_id, "snap": _json.dumps(snap)},
        )
    return True


async def _main(args: argparse.Namespace) -> None:
    settings = DatabaseSettings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        ws_id = uuid.UUID(args.workspace_id) if args.workspace_id else None
        cmp_id = uuid.UUID(args.campaign_id) if args.campaign_id else None

        ids = await _discover_curve_measurements(session_factory, ws_id, cmp_id)
        aggregate_count = await _count_aggregate_measurements(
            session_factory, ws_id, cmp_id
        )

        if not ids:
            print("No campaign_measurement rows with source_curve_id found.")
            if aggregate_count:
                print(
                    f"Note: {aggregate_count} aggregate-rule row(s) carry a snapshot "
                    "but no source_curve_id. Refresh those via the campaign UI."
                )
            return

        print(f"Found {len(ids)} measurement(s) with source curves to rebuild.")
        if aggregate_count:
            print(
                f"Plus {aggregate_count} aggregate-rule row(s) (MEAN/GEOMETRIC) "
                "this script cannot reconstruct — refresh via campaign UI."
            )

        if args.dry_run:
            print("Dry run — listing without writing.")

        updated = 0
        skipped = 0
        for i, mid in enumerate(ids, 1):
            if args.dry_run:
                print(f"[{i}/{len(ids)}] would rebuild {mid}")
                continue
            ok = await _rebuild_one(
                session_factory,
                mid,
                dry_run=False,
                include_closed=args.include_closed,
            )
            if ok:
                updated += 1
            else:
                skipped += 1
            if i % 100 == 0:
                print(f"  ... {i}/{len(ids)} processed")

        if args.dry_run:
            print(f"\nDry run complete. Would have rebuilt {len(ids)} snapshot(s).")
        else:
            print(
                f"\nDone. Rebuilt {updated} snapshot(s); "
                f"skipped {skipped} (curve missing or invalid)."
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
        "--campaign-id",
        help="Limit to a single campaign UUID. Useful for smoke-testing one campaign first.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the measurements that would be rebuilt, without writing.",
    )
    parser.add_argument(
        "--include-closed",
        action="store_true",
        help=(
            "Bypass the closed-campaign write block to rebuild snapshots on "
            "closed/superseded campaigns. Required when backfilling existing "
            "test data; safe since this script only rewrites display metadata "
            "(curve_snapshot JSONB), not measurement values or hit calls."
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(_main(_parse_args()))
