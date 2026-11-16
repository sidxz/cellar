"""Seed (or delete) a large benchmark protocol for the visualization workbench.

Dev database only. Creates ONE protocol named ``BENCH_NAME`` in the workspace
that owns the most runs: 3 runs of 384-well plates (column 1 negative controls,
column 2 positive controls, columns 3-24 samples) holding about ``--rows`` wells
in total, each well with two readout layers of one "Signal" readout (raw RLU +
percent_inhibition). Sample wells cycle through the workspace's existing
batches, so no molecules or batches are created. ``--delete`` removes the
protocol with its readout definitions, runs, plates, wells and readout data.

Usage (from backend/):
    uv run --env-file ../.env python scripts/seed_visualization_benchmark.py --rows 50000
    uv run --env-file ../.env python scripts/seed_visualization_benchmark.py --delete
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import uuid
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from cellar.infrastructure.persistence.settings import DatabaseSettings

BENCH_NAME = "ZZ Benchmark — visualization workbench"
N_RUNS = 3
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def is_dev_database(database_url: str, app_env: str | None) -> bool:
    """APP_ENV=development, or no APP_ENV and a database on this machine."""
    if app_env is not None:
        return app_env == "development"
    return make_url(database_url).host in _LOCAL_HOSTS


async def _workspace(conn: AsyncConnection) -> tuple[uuid.UUID, uuid.UUID]:
    """(workspace, operator) of the dev data: the workspace with the most runs."""
    row = (
        await conn.execute(
            text(
                "SELECT workspace_id, mode() WITHIN GROUP (ORDER BY operator) AS operator "
                "FROM runs GROUP BY workspace_id ORDER BY count(*) DESC LIMIT 1"
            )
        )
    ).one_or_none()
    if row is None:
        sys.exit("No runs in this database; nothing to attach the benchmark to.")
    return row.workspace_id, row.operator


async def _protocol_id(conn: AsyncConnection, ws: uuid.UUID) -> uuid.UUID | None:
    return await conn.scalar(
        text("SELECT id FROM protocols WHERE workspace_id = :ws AND name = :name"),
        {"ws": ws, "name": BENCH_NAME},
    )


async def seed(conn: AsyncConnection, rows: int) -> None:
    ws, operator = await _workspace(conn)
    if await _protocol_id(conn, ws) is not None:
        sys.exit(f"'{BENCH_NAME}' already exists; run --delete first.")

    pid, rd = uuid.uuid4(), uuid.uuid4()
    await conn.execute(
        text(
            "INSERT INTO protocols (id, workspace_id, name, name_base, protocol_type, status, "
            "is_locked, dose_unit, pos_control_signal, version, protocol_version, created_by) "
            "VALUES (:id, :ws, :name, :name, 'biochemical', 'active', false, 'uM', 'low', 1, 1, "
            ":user)"
        ),
        {"id": pid, "ws": ws, "name": BENCH_NAME, "user": operator},
    )
    await conn.execute(
        text(
            "INSERT INTO readout_definitions (id, protocol_id, name, data_type, unit, "
            "aggregation, display_order, is_calculated, normalizations) "
            "VALUES (:id, :p, 'Signal', 'numeric', 'RLU', 'none', 0, false, cast(:n as jsonb))"
        ),
        {"id": rd, "p": pid, "n": json.dumps(["percent_inhibition"])},
    )

    run_ids = [uuid.uuid4() for _ in range(N_RUNS)]
    n_plates = math.ceil(rows / 384)
    for i, run_id in enumerate(run_ids):
        await conn.execute(
            text(
                "INSERT INTO runs (id, workspace_id, protocol_id, run_date, operator, status, "
                "plate_format, is_locked, version) "
                "VALUES (:id, :ws, :p, :d, :user, 'completed', '384', false, 1)"
            ),
            {
                "id": run_id,
                "ws": ws,
                "p": pid,
                "d": date.today() - timedelta(days=N_RUNS - i),
                "user": operator,
            },
        )
        # Plates round-robin over the runs, numbered from 1 within each run.
        await conn.execute(
            text(
                "INSERT INTO plates (id, run_id, plate_number, format) "
                "SELECT gen_random_uuid(), :run, n, '384' FROM generate_series(1, :n) n"
            ),
            {"run": run_id, "n": len(range(i, n_plates, N_RUNS))},
        )
    params = {"ws": ws, "runs": run_ids, "rd": rd}
    await conn.execute(
        text(
            'INSERT INTO wells (id, plate_id, "row", "column", well_type) '
            "SELECT gen_random_uuid(), p.id, chr(65 + r), c, "
            "CASE c WHEN 1 THEN 'negative_control' WHEN 2 THEN 'positive_control' "
            "ELSE 'sample' END "
            "FROM plates p, generate_series(0, 15) r, generate_series(1, 24) c "
            "WHERE p.run_id = ANY(:runs)"
        ),
        params,
    )
    # Raw signal ~1000 for neutral samples / negative controls, ~100 for positive
    # controls, a tail of actives; percent inhibition computed from those means.
    await conn.execute(
        text(
            "WITH b AS ("
            "  SELECT b.id, b.molecule_id, row_number() OVER (ORDER BY b.id) - 1 AS k "
            "  FROM batches b JOIN molecules m ON m.id = b.molecule_id "
            "  WHERE b.workspace_id = :ws AND m.workspace_id = :ws AND m.smiles IS NOT NULL"
            "), nb AS (SELECT greatest(count(*), 1) AS n FROM b), "
            "w AS ("
            "  SELECT w.id, w.well_type, p.run_id, "
            "    row_number() OVER (ORDER BY p.run_id, p.plate_number, w.row, w.column) - 1 AS k, "
            "    CASE w.well_type "
            "      WHEN 'negative_control' THEN 1000 + (random() + random() + random() - 1.5)*80 "
            "      WHEN 'positive_control' THEN 100 + (random() + random() + random() - 1.5)*30 "
            "      ELSE 1000 - 900 * power(random(), 8) "
            "        + (random() + random() + random() - 1.5) * 120 END AS raw "
            "  FROM wells w JOIN plates p ON p.id = w.plate_id WHERE p.run_id = ANY(:runs)"
            ") "
            "INSERT INTO readout_data (id, workspace_id, run_id, well_id, molecule_id, batch_id, "
            "  readout_definition_id, value_numeric, is_outlier, is_computed, "
            "  normalization_applied) "
            "SELECT gen_random_uuid(), :ws, w.run_id, w.id, b.molecule_id, b.id, :rd, "
            "  x.value, false, x.computed, x.norm "
            "FROM w CROSS JOIN nb "
            "LEFT JOIN b ON w.well_type = 'sample' AND b.k = w.k % nb.n "
            "CROSS JOIN LATERAL (VALUES "
            "  (round(w.raw::numeric, 1)::float8, false, NULL), "
            "  (100 * (1000 - w.raw) / 900, true, 'percent_inhibition')"
            ") AS x(value, computed, norm)"
        ),
        params,
    )
    await conn.execute(text("ANALYZE plates, wells, readout_data"))
    wells = await conn.scalar(
        text(
            "SELECT count(*) FROM wells w JOIN plates p ON p.id = w.plate_id "
            "WHERE p.run_id = ANY(:runs)"
        ),
        params,
    )
    print(
        f"Seeded '{BENCH_NAME}' ({pid}) in workspace {ws}: {N_RUNS} runs, {n_plates} plates, "
        f"{wells:,} wells x 2 layers."
    )


async def delete(conn: AsyncConnection) -> None:
    ws, _ = await _workspace(conn)
    pid = await _protocol_id(conn, ws)
    if pid is None:
        print(f"No '{BENCH_NAME}' protocol; nothing to delete.")
        return
    await conn.execute(
        text(
            "DELETE FROM readout_data WHERE run_id IN (SELECT id FROM runs WHERE protocol_id = :p)"
        ),
        {"p": pid},
    )
    await conn.execute(
        text("DELETE FROM runs WHERE protocol_id = :p"), {"p": pid}
    )  # plates, wells
    await conn.execute(text("DELETE FROM protocols WHERE id = :p"), {"p": pid})  # readout defs
    print(f"Deleted '{BENCH_NAME}' ({pid}) and everything under it.")


async def _main(args: argparse.Namespace) -> None:
    url = DatabaseSettings().database_url  # type: ignore[call-arg]
    if not is_dev_database(url, os.environ.get("APP_ENV")):
        sys.exit(
            "Refusing: not a development database (set APP_ENV=development or use localhost)."
        )
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await (delete(conn) if args.delete else seed(conn, args.rows))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--rows", type=int, help="total wells to seed (e.g. 50000, 100000, 200000)")
    mode.add_argument("--delete", action="store_true", help="remove the benchmark protocol")
    asyncio.run(_main(parser.parse_args()))
