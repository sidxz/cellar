"""remap_targets_to_prot_cellar — legacy local targets → mirror rows by name."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa
from scripts.remap_targets_to_prot_cellar import Action, apply_remap, plan_remap, run_remap
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio

_USER = uuid.UUID("eeeeeeee-0000-0000-0000-000000000002")


async def _seed(session: AsyncSession, ws: uuid.UUID) -> dict[str, uuid.UUID]:
    ids = {k: uuid.uuid4() for k in ("legacy_nadd", "mirror_nadd", "legacy_egfr", "proto", "run")}
    await session.execute(
        sa.text(
            "INSERT INTO targets (id, workspace_id, name, target_type, source_version) VALUES "
            "(:ln, :ws, 'NadD', 'single_protein', NULL), "
            "(:mn, :ws, 'nadd', 'single_protein', 7), "
            "(:le, :ws, 'Epidermal Growth Factor Receptor', 'single_protein', NULL)"
        ),
        {"ln": ids["legacy_nadd"], "mn": ids["mirror_nadd"], "le": ids["legacy_egfr"], "ws": ws},
    )
    await session.execute(
        sa.text(
            "INSERT INTO protocols (id, workspace_id, name, protocol_type, status, is_locked, "
            "dose_unit, pos_control_signal, version, protocol_version, created_by) VALUES "
            "(:p, :ws, 'P', 'biochemical', 'active', false, 'uM', 'high', 1, 1, :u)"
        ),
        {"p": ids["proto"], "ws": ws, "u": _USER},
    )
    await session.execute(
        sa.text(
            "INSERT INTO runs (id, workspace_id, protocol_id, run_date, operator, status, "
            "is_locked, version) VALUES (:r, :ws, :p, :d, :u, 'draft', false, 1)"
        ),
        {"r": ids["run"], "ws": ws, "p": ids["proto"], "d": date.today(), "u": _USER},
    )
    # legacy NadD linked to the run; the mirror NadD ALSO already linked to the same run
    # (dedupe case); legacy EGFR linked to the protocol.
    await session.execute(
        sa.text("INSERT INTO run_targets (run_id, target_id) VALUES (:r, :ln), (:r, :mn)"),
        {"r": ids["run"], "ln": ids["legacy_nadd"], "mn": ids["mirror_nadd"]},
    )
    await session.execute(
        sa.text("INSERT INTO protocol_targets (protocol_id, target_id) VALUES (:p, :le)"),
        {"p": ids["proto"], "le": ids["legacy_egfr"]},
    )
    return ids


async def _count(session: AsyncSession, sql: str, **params) -> int:
    return int(await session.scalar(sa.text(sql), params) or 0)


async def test_plan_then_apply(session_factory: async_sessionmaker[AsyncSession]) -> None:
    ws = uuid.uuid4()
    async with session_factory() as session, session.begin():
        ids = await _seed(session, ws)

    async with session_factory() as session:
        actions = await plan_remap(session, ws)
    assert sorted(actions, key=lambda a: a.name) == [
        Action("drop", ids["legacy_egfr"], "Epidermal Growth Factor Receptor", None, 1, 0),
        Action("remap", ids["legacy_nadd"], "NadD", ids["mirror_nadd"], 0, 1),
    ]

    async with session_factory() as session, session.begin():
        await apply_remap(session, actions)

    async with session_factory() as session:
        assert (
            await _count(session, "SELECT count(*) FROM targets WHERE workspace_id=:ws", ws=ws)
            == 1
        )
        assert (
            await _count(session, "SELECT count(*) FROM run_targets WHERE run_id=:r", r=ids["run"])
            == 1
        )
        assert (
            await _count(
                session,
                "SELECT count(*) FROM run_targets WHERE run_id=:r AND target_id=:t",
                r=ids["run"],
                t=ids["mirror_nadd"],
            )
            == 1
        )
        assert (
            await _count(
                session,
                "SELECT count(*) FROM protocol_targets WHERE protocol_id=:p",
                p=ids["proto"],
            )
            == 0
        )

    # cleanup (session_factory rows are committed; keep the shared test DB tidy)
    async with session_factory() as session, session.begin():
        await session.execute(sa.text("DELETE FROM runs WHERE id=:r"), {"r": ids["run"]})
        await session.execute(sa.text("DELETE FROM protocols WHERE id=:p"), {"p": ids["proto"]})
        await session.execute(sa.text("DELETE FROM targets WHERE workspace_id=:ws"), {"ws": ws})


async def test_run_remap_entrypoint_dry_run_then_apply(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The CLI path: plan + apply through ``run_remap`` on ONE factory.

    Regression for the first saclab-dev run — planning auto-begins a
    transaction, so applying via ``session.begin()`` on the same session raised
    "A transaction is already begun on this Session".
    """
    ws = uuid.uuid4()
    async with session_factory() as session, session.begin():
        ids = await _seed(session, ws)

    dry = await run_remap(session_factory, ws, apply=False)
    assert {a.kind for a in dry} == {"remap", "drop"}
    async with session_factory() as session:
        assert (
            await _count(session, "SELECT count(*) FROM targets WHERE workspace_id=:ws", ws=ws)
            == 3
        )

    applied = await run_remap(session_factory, ws, apply=True)
    assert applied == dry
    async with session_factory() as session:
        assert (
            await _count(session, "SELECT count(*) FROM targets WHERE workspace_id=:ws", ws=ws)
            == 1
        )
        assert (
            await _count(session, "SELECT count(*) FROM run_targets WHERE run_id=:r", r=ids["run"])
            == 1
        )

    async with session_factory() as session, session.begin():
        await session.execute(sa.text("DELETE FROM runs WHERE id=:r"), {"r": ids["run"]})
        await session.execute(sa.text("DELETE FROM protocols WHERE id=:p"), {"p": ids["proto"]})
        await session.execute(sa.text("DELETE FROM targets WHERE workspace_id=:ws"), {"ws": ws})
