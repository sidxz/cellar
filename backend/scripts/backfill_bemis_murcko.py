"""One-shot backfill — populate Molecule.bemis_murcko_smiles for legacy rows.

Idempotent: skips rows where bemis_murcko_smiles IS NOT NULL.
Batches of 500 by default. Run via:

    cd backend && uv run python scripts/backfill_bemis_murcko.py
    cd backend && uv run python scripts/backfill_bemis_murcko.py --dry-run
    cd backend && uv run python scripts/backfill_bemis_murcko.py --batch-size 500
    cd backend && uv run python scripts/backfill_bemis_murcko.py --workspace-id <uuid>

Idempotent + resumable: each batch is committed once, so partial runs
can be restarted without re-processing already-populated rows.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import uuid

import structlog
from rdkit import Chem
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Eagerly import sibling model modules so SQLAlchemy can resolve cross-context
# foreign keys at query-compile time (e.g. molecules.originating_org_id -> organizations.id).
# Without this, select(MoleculeModel) raises NoReferencedTableError.
import cellar.infrastructure.persistence.sqlalchemy.workspace_config.models  # noqa: F401
import cellar.infrastructure.persistence.sqlalchemy.research_organization.models  # noqa: F401
import cellar.infrastructure.persistence.sqlalchemy.screening_assay.models  # noqa: F401
import cellar.infrastructure.persistence.sqlalchemy.inventory.models  # noqa: F401

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from cellar.infrastructure.persistence.settings import DatabaseSettings
from cellar.infrastructure.rdkit.scaffold_calculator import MurckoScaffoldCalculator

logger = structlog.get_logger(__name__)


@dataclasses.dataclass
class BackfillBatchStats:
    processed: int = 0
    failed: int = 0


async def backfill_batch(
    session: AsyncSession,
    batch_size: int,
    workspace_id: uuid.UUID | None = None,
) -> BackfillBatchStats:
    """Backfill one batch of NULL-scaffold molecule rows.

    Queries up to *batch_size* molecules whose ``bemis_murcko_smiles`` is NULL,
    computes the Bemis-Murcko scaffold via RDKit, and commits the result.

    Args:
        session: An open async SQLAlchemy session.
        batch_size: Maximum number of rows to process per call.
        workspace_id: If provided, restrict to molecules in this workspace.

    Returns:
        BackfillBatchStats with ``processed`` (successfully written) and ``failed``
        (parse / compute errors) counts. Rows that failed are NOT retried —
        they retain ``NULL`` so that a subsequent run will attempt them again.
        To prevent an infinite retry loop on persistent failures, callers should
        compare ``stats.processed == 0 and stats.failed > 0`` and stop.
    """
    calc = MurckoScaffoldCalculator()
    stats = BackfillBatchStats()

    stmt = (
        select(MoleculeModel)
        .where(MoleculeModel.bemis_murcko_smiles.is_(None))
        .order_by(MoleculeModel.id)
        .limit(batch_size)
    )
    if workspace_id is not None:
        stmt = stmt.where(MoleculeModel.workspace_id == workspace_id)

    result = await session.execute(stmt)
    rows = list(result.scalars())

    for row in rows:
        if not row.smiles:
            # Structureless / undisclosed molecule — mark as computed-empty
            # so it won't be retried on subsequent runs.
            row.bemis_murcko_smiles = ""
            stats.processed += 1
            logger.debug(
                "backfill_no_smiles",
                mol_id=str(row.id),
                registration_number=row.registration_number,
            )
            continue

        mol = Chem.MolFromSmiles(row.smiles)
        if mol is None:
            stats.failed += 1
            logger.warning(
                "backfill_parse_failed",
                mol_id=str(row.id),
                registration_number=row.registration_number,
                smiles=row.smiles,
            )
            continue

        scaffold = calc.compute(mol)
        if scaffold is None:
            # RDKit compute error — defensive path in MurckoScaffoldCalculator.
            stats.failed += 1
            logger.warning(
                "backfill_compute_failed",
                mol_id=str(row.id),
                registration_number=row.registration_number,
                smiles=row.smiles,
            )
            continue

        row.bemis_murcko_smiles = scaffold
        stats.processed += 1
        logger.debug(
            "backfill_computed",
            mol_id=str(row.id),
            scaffold=scaffold or "<acyclic>",
        )

    await session.commit()
    return stats


async def run_until_empty(
    batch_size: int,
    workspace_id: uuid.UUID | None,
    dry_run: bool,
) -> None:
    """Process molecules in batches until no NULL rows remain.

    ``dry_run`` prints what would be done without writing any rows.
    """
    settings = DatabaseSettings()  # type: ignore[call-arg]
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    if dry_run:
        async with session_factory() as session:
            # Count only; no writes.
            stmt_count = select(MoleculeModel).where(MoleculeModel.bemis_murcko_smiles.is_(None))
            if workspace_id is not None:
                stmt_count = stmt_count.where(MoleculeModel.workspace_id == workspace_id)
            rows = list((await session.execute(stmt_count)).scalars())
            print(f"Dry run: {len(rows)} molecule(s) would be backfilled.")
        await engine.dispose()
        return

    total = BackfillBatchStats()
    batch_num = 0
    try:
        while True:
            batch_num += 1
            async with session_factory() as session:
                stats = await backfill_batch(
                    session, batch_size=batch_size, workspace_id=workspace_id
                )
            total.processed += stats.processed
            total.failed += stats.failed

            if stats.processed == 0 and stats.failed == 0:
                # Nothing left to process.
                break

            logger.info(
                "backfill_batch_done",
                batch=batch_num,
                processed=stats.processed,
                failed=stats.failed,
                total_so_far=total.processed,
            )

            if stats.processed == 0 and stats.failed > 0:
                # All remaining rows are unparseable — stop to avoid an infinite loop.
                logger.error(
                    "backfill_stopped_all_failures",
                    failed=stats.failed,
                )
                break

    finally:
        await engine.dispose()

    logger.info(
        "backfill_complete",
        total_processed=total.processed,
        total_failed=total.failed,
    )
    print(
        f"Done. Populated {total.processed} scaffold(s); "
        f"{total.failed} row(s) failed (smiles parse error — check logs)."
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Number of molecules to process per batch (default: 500).",
    )
    parser.add_argument(
        "--workspace-id",
        default=None,
        help="Limit backfill to a single workspace UUID.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count rows that would be processed, without writing.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    ws_id = uuid.UUID(args.workspace_id) if args.workspace_id else None
    asyncio.run(run_until_empty(args.batch_size, ws_id, args.dry_run))
