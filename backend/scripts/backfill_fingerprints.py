"""Backfill Morgan + FCFP fingerprints for molecules registered before migration 025.

Migration 025 changed the `morgan_bfp` trigger: it no longer derives from
`smiles`, it lifts bytes from `fp_morgan` (bytea) via `bfp_from_binary_text`.
Existing rows have `fp_morgan = NULL` and therefore `morgan_bfp = NULL`,
which makes similarity search return zero hits.

This script:
  1. Computes stereo-aware Morgan bytes in Python (same path the registration
     pipeline uses) for every molecule that has `smiles` set and `fp_morgan`
     missing.
  2. Writes `fp_morgan`; the `sync_morgan_bfp` trigger fires and fills
     `morgan_bfp` from those bytes.
  3. Forces the `compute_fcfp_bfp` trigger to fire for any row where
     `fcfp_bfp` is still NULL (the trigger fires BEFORE UPDATE OF smiles,
     so `SET smiles = smiles` is enough).

Usage (from backend/):
    uv run python scripts/backfill_fingerprints.py
    uv run python scripts/backfill_fingerprints.py --dry-run
    uv run python scripts/backfill_fingerprints.py --workspace-id <uuid>
    uv run python scripts/backfill_fingerprints.py --batch-size 500

Idempotent: skips rows that already have `fp_morgan` set.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

from rdkit import Chem
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from cellar.infrastructure.persistence.settings import DatabaseSettings
from cellar.infrastructure.rdkit.fingerprints.morgan import MorganAlgorithm

_morgan = MorganAlgorithm()


async def _backfill_morgan(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID | None,
    batch_size: int,
    dry_run: bool,
) -> tuple[int, int, int]:
    """Returns (scanned, written, parse_failures)."""
    where_ws = "AND workspace_id = :ws" if workspace_id else ""
    select_sql = (
        f"SELECT id, smiles FROM molecules "
        f"WHERE smiles IS NOT NULL AND fp_morgan IS NULL {where_ws} "
        f"ORDER BY id"
    )
    params: dict[str, object] = {}
    if workspace_id:
        params["ws"] = workspace_id

    result = await session.execute(text(select_sql), params)
    rows = result.all()
    scanned = len(rows)
    written = 0
    parse_failures = 0

    print(f"  found {scanned} molecules needing Morgan backfill")

    if scanned == 0:
        return scanned, 0, 0

    update_stmt = text(
        "UPDATE molecules SET fp_morgan = :fp WHERE id = :id"
    ).bindparams(
        bindparam("fp", type_=__import__("sqlalchemy").LargeBinary),
    )

    pending: list[dict[str, object]] = []
    for i, (mol_id, smiles) in enumerate(rows, start=1):
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            parse_failures += 1
            print(f"  [{i}/{scanned}] WARN unparseable SMILES on {mol_id}: {smiles!r}")
            continue
        fp_bytes = _morgan.compute_bytes(mol)
        pending.append({"id": mol_id, "fp": fp_bytes})

        if len(pending) >= batch_size:
            if not dry_run:
                await session.execute(update_stmt, pending)
                await session.commit()
            written += len(pending)
            print(f"  [{i}/{scanned}] flushed {len(pending)} (total written: {written})")
            pending.clear()

    if pending:
        if not dry_run:
            await session.execute(update_stmt, pending)
            await session.commit()
        written += len(pending)
        print(f"  [{scanned}/{scanned}] flushed final {len(pending)} (total written: {written})")

    return scanned, written, parse_failures


async def _backfill_fcfp(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID | None,
    dry_run: bool,
) -> int:
    """Force the compute_fcfp_bfp trigger for rows where fcfp_bfp is NULL.

    The trigger fires BEFORE UPDATE OF smiles, so a no-op UPDATE on smiles
    is enough. Returns count of affected rows.
    """
    where_ws = "AND workspace_id = :ws" if workspace_id else ""
    sql = (
        f"UPDATE molecules SET smiles = smiles "
        f"WHERE smiles IS NOT NULL AND fcfp_bfp IS NULL {where_ws}"
    )
    params: dict[str, object] = {}
    if workspace_id:
        params["ws"] = workspace_id

    if dry_run:
        count_sql = (
            f"SELECT count(*) FROM molecules "
            f"WHERE smiles IS NOT NULL AND fcfp_bfp IS NULL {where_ws}"
        )
        result = await session.execute(text(count_sql), params)
        return int(result.scalar_one())

    result = await session.execute(text(sql), params)
    await session.commit()
    return result.rowcount or 0


async def _run(args: argparse.Namespace) -> int:
    settings = DatabaseSettings()  # type: ignore[call-arg]
    engine = create_async_engine(settings.database_url, echo=False)
    workspace_id = uuid.UUID(args.workspace_id) if args.workspace_id else None

    print(f"Backfill target: {settings.database_url}")
    print(f"Workspace filter: {workspace_id or '<all workspaces>'}")
    print(f"Dry run: {args.dry_run}")
    print()

    async with AsyncSession(engine) as session:
        print("Step 1/2: Morgan (Python-computed bytes)")
        scanned, written, parse_failures = await _backfill_morgan(
            session,
            workspace_id=workspace_id,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )
        print()
        print("Step 2/2: FCFP (trigger via no-op UPDATE OF smiles)")
        fcfp_affected = await _backfill_fcfp(
            session,
            workspace_id=workspace_id,
            dry_run=args.dry_run,
        )

    await engine.dispose()

    print()
    print("Summary:")
    print(f"  Morgan scanned:     {scanned}")
    print(f"  Morgan written:     {written}")
    print(f"  Morgan parse fails: {parse_failures}")
    print(f"  FCFP triggered:     {fcfp_affected}")
    if args.dry_run:
        print()
        print("(dry run — no changes committed)")
    return 0 if parse_failures == 0 else 1


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--workspace-id", default=None, help="UUID; restrict to one workspace")
    p.add_argument("--batch-size", type=int, default=500)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    exit_code = asyncio.run(_run(_parse_args()))
    raise SystemExit(exit_code)
