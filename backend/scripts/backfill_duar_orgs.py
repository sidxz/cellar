"""Fill Duar org columns on records made before orgs moved to Duar.

Run once per database after migrating to 120, naming the Duar org existing
records belong to (an install whose workspaces belong to different orgs runs it
once per workspace):

  * every org column added for Duar orgs that is still empty takes ``--org-id``;
    a molecule takes a discloser org only if it is disclosed;
  * columns that used to hold Cellar's local org ids (a run's performed-at org,
    a collection's owner, a disclosure's org, a bulk disclosure's partner) take
    ``--org-id`` where empty or still a local id; a Duar id already there stays;
  * a molecule's registrant comes from the History record of its registration;
  * a molecule registered with its structure, with no discloser on file, is
    disclosed by that registrant at its registration time (the rule new
    registrations follow). With no History record both stay empty.

Usage (from backend/):
    uv run python scripts/backfill_duar_orgs.py --org-id <uuid> --dry-run
    uv run python scripts/backfill_duar_orgs.py --org-id <uuid> [--workspace-id <uuid>]

Idempotent: a second pass changes nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cellar.infrastructure.persistence.settings import DatabaseSettings

# Table and column names below are fixed literals, never input — hence the S608 noqa.
_SCOPE = "(:every OR workspace_id = :ws)"
_LOCAL = "IN (SELECT id FROM organizations)"

# (label, SQL). Order matters: the registrant is filled before the discloser copies it.
_STEPS: list[tuple[str, str]] = [
    (
        "molecules.registered_by",
        f"""UPDATE molecules m SET registered_by = a.user_id
            FROM (SELECT DISTINCT ON (entity_id) entity_id, user_id FROM audit_operations
                  WHERE entity_type = 'Molecule' AND operation_type = 'registration'
                    AND actor_type = 'user'
                  ORDER BY entity_id, started_at) a
            WHERE a.entity_id = m.id AND m.registered_by IS NULL AND {_SCOPE}""",  # noqa: S608
    ),
    (
        "molecules.disclosed_by",
        f"""UPDATE molecules SET disclosed_by = registered_by, disclosed_at = created_at
            WHERE structure_status = 'disclosed' AND disclosed_by IS NULL
              AND registered_by IS NOT NULL AND {_SCOPE}""",  # noqa: S608
    ),
    *(
        (f"{t}.{c}", f"UPDATE {t} SET {c} = :org WHERE {c} IS NULL AND {_SCOPE}")  # noqa: S608
        for t, c in (
            ("molecules", "registered_by_org_id"),
            ("cdd_molecule_imports", "disclosed_by_org_id"),
            ("disclosure_requests", "requested_by_org_id"),
            ("bulk_disclosures", "submitted_by_org_id"),
            ("collections", "created_by_org_id"),
            ("projects", "created_by_org_id"),
            ("projects", "owner_org_id"),
            ("protocols", "created_by_org_id"),
            ("protocols", "owner_org_id"),
        )
    ),
    (
        "molecules.disclosed_by_org_id",
        f"""UPDATE molecules SET disclosed_by_org_id = :org
            WHERE disclosed_by_org_id IS NULL AND structure_status = 'disclosed'
              AND {_SCOPE}""",  # noqa: S608
    ),
    *(
        (
            f"{t}.{c}",
            f"UPDATE {t} SET {c} = :org WHERE ({c} IS NULL OR {c} {_LOCAL}) AND {_SCOPE}",  # noqa: S608
        )
        for t, c in (
            ("runs", "performed_at_org_id"),
            ("collections", "owner_org_id"),
            ("disclosure_requests", "disclosing_org_id"),
            ("bulk_disclosures", "partner_org_id"),
        )
    ),
]


async def backfill(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    org_id: uuid.UUID,
    workspace_id: uuid.UUID | None,
    dry_run: bool,
) -> dict[str, int]:
    """Rows changed per ``table.column``, in one transaction (rolled back on a dry run)."""
    params = {"org": org_id, "every": workspace_id is None, "ws": workspace_id}
    counts: dict[str, int] = {}
    async with session_factory() as session, session.begin():
        for label, sql in _STEPS:
            result = await session.execute(text(sql), params)
            counts[label] = result.rowcount  # type: ignore[attr-defined]
        if dry_run:
            await session.rollback()
    return counts


async def _main(args: argparse.Namespace) -> None:
    engine = create_async_engine(DatabaseSettings().database_url, pool_pre_ping=True)
    try:
        counts = await backfill(
            async_sessionmaker(engine, expire_on_commit=False),
            org_id=uuid.UUID(args.org_id),
            workspace_id=uuid.UUID(args.workspace_id) if args.workspace_id else None,
            dry_run=args.dry_run,
        )
        for label, n in counts.items():
            print(f"{label:40} {n}")
        print("Dry run: nothing written." if args.dry_run else "Done.")
    finally:
        await engine.dispose()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org-id", required=True, help="The Duar org existing records belong to.")
    parser.add_argument("--workspace-id", help="Limit to one workspace. Defaults to all.")
    parser.add_argument("--dry-run", action="store_true", help="Count the changes, write nothing.")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(_main(_parse_args()))
