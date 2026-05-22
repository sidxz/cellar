"""One-shot backfill: materialize BatchIdentifier mirrors for existing molecule
synonyms + batches.

Idempotent. Uses ON CONFLICT DO NOTHING against the workspace-unique
constraint (uq_batch_ws_identifier). Safe to re-run.

Run via:
    cd backend && uv run python scripts/backfill_batch_identifier_mirrors.py
    cd backend && uv run python scripts/backfill_batch_identifier_mirrors.py --workspace-id <uuid>
    cd backend && uv run python scripts/backfill_batch_identifier_mirrors.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import cellar.infrastructure.persistence.sqlalchemy.inventory.models
import cellar.infrastructure.persistence.sqlalchemy.research_organization.models
import cellar.infrastructure.persistence.sqlalchemy.screening_assay.models

# Eagerly import sibling model modules so SQLAlchemy can resolve cross-context FKs.
import cellar.infrastructure.persistence.sqlalchemy.workspace_config.models  # noqa: F401
from cellar.infrastructure.persistence.settings import DatabaseSettings
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeIdentifierModel,
    MoleculeModel,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import BatchModel

logger = structlog.get_logger(__name__)


def _derive_suffix(batch_number: str) -> str | None:
    """Extract the numeric suffix from a batch number like CC-000001-001 → '001'."""
    parts = batch_number.rsplit("-", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        return None
    return parts[1]


async def run_backfill(
    sessionmaker, *, workspace_id: uuid.UUID | None = None, dry_run: bool = False
) -> dict[str, int]:
    """
    Iterate all (molecule_identifier × batch) pairs and insert a BatchIdentifier
    mirror for each combination.

    Returns a dict with keys: created, skipped, malformed.
    """
    stats: dict[str, int] = {"created": 0, "skipped": 0, "malformed": 0}

    async with sessionmaker() as session:
        # Load all molecule rows to iterate (optionally filtered by workspace).
        mol_q = select(MoleculeModel.id, MoleculeModel.workspace_id)
        if workspace_id is not None:
            mol_q = mol_q.where(MoleculeModel.workspace_id == workspace_id)
        mol_rows = (await session.execute(mol_q)).all()

        for mol_id, ws_id in mol_rows:
            # Load all synonyms for this molecule.
            ident_rows = (
                await session.execute(
                    select(
                        MoleculeIdentifierModel.id,
                        MoleculeIdentifierModel.identifier,
                        MoleculeIdentifierModel.registered_by,
                    ).where(MoleculeIdentifierModel.molecule_id == mol_id)
                )
            ).all()

            # Load all batches for this molecule.
            batch_rows = (
                await session.execute(
                    select(BatchModel.id, BatchModel.batch_number).where(
                        BatchModel.molecule_id == mol_id
                    )
                )
            ).all()

            for ident_id, ident_value, ident_actor in ident_rows:
                for batch_id, batch_number in batch_rows:
                    suffix = _derive_suffix(batch_number)
                    if suffix is None:
                        stats["malformed"] += 1
                        logger.warning(
                            "backfill_malformed_batch_number",
                            batch_id=str(batch_id),
                            batch_number=batch_number,
                        )
                        continue

                    mirror = f"{ident_value}-{suffix}"

                    if dry_run:
                        # Count as "would create" without touching the DB.
                        stats["created"] += 1
                        continue

                    result = await session.execute(
                        text(
                            """
                            INSERT INTO batch_identifiers (
                                id, batch_id, workspace_id, identifier,
                                identifier_type, source, registered_by,
                                derived_from_molecule_identifier_id, created_at
                            ) VALUES (
                                gen_random_uuid(), :batch_id, :workspace_id, :identifier,
                                'custom', 'compound-syn (backfill)', :registered_by,
                                :derived_from, NOW()
                            )
                            ON CONFLICT (workspace_id, identifier) DO NOTHING
                            """
                        ),
                        {
                            "batch_id": batch_id,
                            "workspace_id": ws_id,
                            "identifier": mirror,
                            "registered_by": ident_actor,
                            "derived_from": ident_id,
                        },
                    )
                    if result.rowcount and result.rowcount > 0:
                        stats["created"] += 1
                    else:
                        stats["skipped"] += 1

        if not dry_run:
            await session.commit()

    logger.info("backfill_done", **stats, dry_run=dry_run)
    return stats


async def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill BatchIdentifier mirrors from molecule synonyms × batches."
    )
    parser.add_argument(
        "--workspace-id",
        type=uuid.UUID,
        default=None,
        help="Restrict backfill to a single workspace UUID (default: all workspaces).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count what would be created without writing to the DB.",
    )
    args = parser.parse_args()

    engine = create_async_engine(DatabaseSettings().database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    stats = await run_backfill(
        session_factory, workspace_id=args.workspace_id, dry_run=args.dry_run
    )
    print(
        f"backfill: created={stats['created']} skipped={stats['skipped']} "
        f"malformed={stats['malformed']} dry_run={args.dry_run}"
    )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
