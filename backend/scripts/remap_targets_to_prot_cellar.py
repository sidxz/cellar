"""One-shot cutover: move legacy local targets onto their prot-cellar mirror rows.

Run AFTER the first admin "Sync from Prot-Cellar" (Admin → Targets), which
creates the mirror rows (``source_version IS NOT NULL``). For every legacy
row (``source_version IS NULL``):

- name matches a mirror row (case-insensitive) → **remap**: move its
  ``protocol_targets`` / ``run_targets`` links to the mirror id (skipping
  links the mirror already has), then delete the legacy row;
- no match → **drop**: delete its links and the row.

Default is a dry run that prints the plan. ``--apply`` executes it in one
transaction.

    cd backend && uv run python scripts/remap_targets_to_prot_cellar.py --workspace-id <uuid>
    cd backend && uv run python scripts/remap_targets_to_prot_cellar.py \
        --workspace-id <uuid> --apply
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from dataclasses import dataclass
from typing import Literal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cellar.infrastructure.persistence.settings import DatabaseSettings


@dataclass(frozen=True)
class Action:
    kind: Literal["remap", "drop"]
    legacy_id: uuid.UUID
    name: str
    mirror_id: uuid.UUID | None
    protocol_links: int
    run_links: int


async def plan_remap(session: AsyncSession, workspace_id: uuid.UUID) -> list[Action]:
    rows = (
        await session.execute(
            sa.text(
                "SELECT l.id, l.name, m.id AS mirror_id, "
                "(SELECT count(*) FROM protocol_targets pt WHERE pt.target_id = l.id) AS pl, "
                "(SELECT count(*) FROM run_targets rt WHERE rt.target_id = l.id) AS rl "
                "FROM targets l "
                "LEFT JOIN targets m ON m.workspace_id = l.workspace_id "
                "  AND m.source_version IS NOT NULL "
                "  AND lower(btrim(m.name)) = lower(btrim(l.name)) "
                "WHERE l.workspace_id = :ws AND l.source_version IS NULL "
                "ORDER BY l.name"
            ),
            {"ws": workspace_id},
        )
    ).all()
    return [
        Action(
            kind="remap" if mirror_id else "drop",
            legacy_id=lid,
            name=name,
            mirror_id=mirror_id,
            protocol_links=int(pl),
            run_links=int(rl),
        )
        for lid, name, mirror_id, pl, rl in rows
    ]


_MOVE = {
    "protocol_targets": (
        "INSERT INTO protocol_targets (protocol_id, target_id) "
        "SELECT protocol_id, :new FROM protocol_targets WHERE target_id = :old "
        "ON CONFLICT DO NOTHING"
    ),
    "run_targets": (
        "INSERT INTO run_targets (run_id, target_id) "
        "SELECT run_id, :new FROM run_targets WHERE target_id = :old "
        "ON CONFLICT DO NOTHING"
    ),
}


async def apply_remap(session: AsyncSession, actions: list[Action]) -> None:
    for a in actions:
        if a.kind == "remap":
            for stmt in _MOVE.values():
                await session.execute(sa.text(stmt), {"new": a.mirror_id, "old": a.legacy_id})
        for table in ("protocol_targets", "run_targets"):
            await session.execute(
                sa.text(f"DELETE FROM {table} WHERE target_id = :old"), {"old": a.legacy_id}
            )
        await session.execute(sa.text("DELETE FROM targets WHERE id = :old"), {"old": a.legacy_id})


def _print_plan(actions: list[Action]) -> None:
    if not actions:
        print("nothing to do — no legacy (source_version IS NULL) targets")
        return
    for a in actions:
        target = f"→ {a.mirror_id}" if a.kind == "remap" else "(no prot-cellar match)"
        print(
            f"{a.kind:5} {a.name!r:45} {target}  "
            f"[{a.protocol_links} protocol link(s), {a.run_links} run link(s)]"
        )


async def run_remap(
    factory: async_sessionmaker[AsyncSession], workspace_id: uuid.UUID, *, apply: bool
) -> list[Action]:
    """Plan in one session; apply in a fresh transaction-scoped session.

    Planning runs SELECTs, which auto-begin a transaction on that session —
    so the apply step must not call ``session.begin()`` on the same session
    (SQLAlchemy raises "A transaction is already begun").
    """
    async with factory() as session:
        actions = await plan_remap(session, workspace_id)
        if apply and actions:
            mirror_count = await session.scalar(
                sa.text(
                    "SELECT count(*) FROM targets "
                    "WHERE workspace_id = :ws AND source_version IS NOT NULL"
                ),
                {"ws": workspace_id},
            )
            if not mirror_count:
                raise SystemExit(
                    "refusing: no prot-cellar mirror rows in this workspace — "
                    "run the admin sync first"
                )
    if apply and actions:
        async with factory.begin() as session:
            await apply_remap(session, actions)
    return actions


async def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--workspace-id", type=uuid.UUID, required=True)
    parser.add_argument("--apply", action="store_true", help="Execute (default: dry run).")
    args = parser.parse_args()

    engine = create_async_engine(DatabaseSettings().database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    actions = await run_remap(factory, args.workspace_id, apply=args.apply)
    _print_plan(actions)
    if args.apply and actions:
        print(f"applied {len(actions)} action(s)")
    elif actions:
        print("dry run — re-run with --apply to execute")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
