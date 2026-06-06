"""Integration tests: protocol/run target M2M — roll-up, auto-prune, delete protection.

Exercises the effective-target union (direct union run-derived) and the auto-prune
of inherited-only targets, against a real PostgreSQL schema.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.run_repository import (
    SQLAlchemyRunRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

_USER_ID = uuid.UUID("eeeeeeee-0000-0000-0000-000000000001")


async def _insert_protocol(uow: AsyncUnitOfWork, pid: uuid.UUID, ws: uuid.UUID) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO protocols "
            "(id, workspace_id, name, protocol_type, status, is_locked, "
            "dose_unit, pos_control_signal, version, protocol_version, created_by) "
            "VALUES (:id, :ws, :name, 'biochemical', 'active', false, "
            "'uM', 'high', 1, 1, :user)"
        ),
        {"id": pid, "ws": ws, "name": f"P-{str(pid)[:8]}", "user": _USER_ID},
    )


async def _insert_run(
    uow: AsyncUnitOfWork, rid: uuid.UUID, pid: uuid.UUID, ws: uuid.UUID
) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO runs "
            "(id, workspace_id, protocol_id, run_date, operator, status, "
            "is_locked, version) "
            "VALUES (:id, :ws, :proto, :run_date, :user, 'draft', false, 1)"
        ),
        {"id": rid, "ws": ws, "proto": pid, "run_date": date.today(), "user": _USER_ID},
    )


async def _insert_target(
    uow: AsyncUnitOfWork, tid: uuid.UUID, ws: uuid.UUID, name: str
) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO targets (id, workspace_id, name, target_type) "
            "VALUES (:id, :ws, :name, 'single_protein')"
        ),
        {"id": tid, "ws": ws, "name": name},
    )


@pytest.mark.asyncio
class TestTargetLinks:
    async def test_rollup_and_auto_prune(self, uow, workspace_id):
        p = uuid.uuid4()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        t1, t2, t3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        async with uow:
            await _insert_protocol(uow, p, workspace_id)
            await _insert_run(uow, r1, p, workspace_id)
            await _insert_run(uow, r2, p, workspace_id)
            for t, n in ((t1, "NadD"), (t2, "PptT"), (t3, "Pks13")):
                await _insert_target(uow, t, workspace_id, n)
            await uow.commit()

        prepo = SQLAlchemyProtocolRepository(uow)
        rrepo = SQLAlchemyRunRepository(uow)

        # Direct protocol target (Pks13) + independent run targets.
        async with uow:
            await prepo.add_direct_target(workspace_id, p, t3)
            await rrepo.add_target(workspace_id, r1, t1)
            await rrepo.add_target(workspace_id, r2, t2)
            await uow.commit()

        async with uow:
            eff = await prepo.find_effective_targets(workspace_id, p)
        by_id = {e.id: e for e in eff}
        assert set(by_id) == {t1, t2, t3}
        assert by_id[t3].is_direct is True and by_id[t3].run_count == 0
        assert by_id[t1].is_direct is False and by_id[t1].run_count == 1
        assert by_id[t2].is_direct is False and by_id[t2].run_count == 1

        # Second run references t1 → run_count rises to 2.
        async with uow:
            await rrepo.add_target(workspace_id, r2, t1)
            await uow.commit()
        async with uow:
            eff = {e.id: e for e in await prepo.find_effective_targets(workspace_id, p)}
        assert eff[t1].run_count == 2

        # Drop t1 from r1 → still present via r2.
        async with uow:
            await rrepo.remove_target(workspace_id, r1, t1)
            await uow.commit()
        async with uow:
            eff = {e.id: e for e in await prepo.find_effective_targets(workspace_id, p)}
        assert t1 in eff and eff[t1].run_count == 1

        # Drop t1 from the last run → auto-pruned from the protocol.
        async with uow:
            await rrepo.remove_target(workspace_id, r2, t1)
            await uow.commit()
        async with uow:
            eff = {e.id: e for e in await prepo.find_effective_targets(workspace_id, p)}
        assert t1 not in eff
        # Direct target survives with zero runs.
        assert t3 in eff and eff[t3].is_direct is True

    async def test_idempotent_add(self, uow, workspace_id):
        p = uuid.uuid4()
        r = uuid.uuid4()
        t = uuid.uuid4()
        async with uow:
            await _insert_protocol(uow, p, workspace_id)
            await _insert_run(uow, r, p, workspace_id)
            await _insert_target(uow, t, workspace_id, "EGFR")
            await uow.commit()

        rrepo = SQLAlchemyRunRepository(uow)
        async with uow:
            await rrepo.add_target(workspace_id, r, t)
            await rrepo.add_target(workspace_id, r, t)  # no-op, no duplicate-PK error
            await uow.commit()
        async with uow:
            refs = (await rrepo.find_target_refs_for_runs(workspace_id, [r])).get(r, [])
        assert [x.id for x in refs] == [t]

    async def test_delete_referenced_target_is_blocked(self, uow, workspace_id):
        """RESTRICT FK (migration 053): an in-use target cannot be deleted —
        its links must never be silently stripped. Unlinking first unblocks."""
        p = uuid.uuid4()
        r = uuid.uuid4()
        t = uuid.uuid4()
        async with uow:
            await _insert_protocol(uow, p, workspace_id)
            await _insert_run(uow, r, p, workspace_id)
            await _insert_target(uow, t, workspace_id, "BRAF")
            await uow.commit()

        rrepo = SQLAlchemyRunRepository(uow)
        async with uow:
            await rrepo.add_target(workspace_id, r, t)
            await uow.commit()

        with pytest.raises(IntegrityError):
            async with uow:
                await uow.session.execute(
                    sa.text("DELETE FROM targets WHERE id = :id"), {"id": t}
                )
                await uow.commit()

        # Still linked; after unlinking, the delete goes through.
        async with uow:
            refs = (await rrepo.find_target_refs_for_runs(workspace_id, [r])).get(r, [])
        assert [x.id for x in refs] == [t]

        async with uow:
            await rrepo.remove_target(workspace_id, r, t)
            await uow.commit()
        async with uow:
            await uow.session.execute(
                sa.text("DELETE FROM targets WHERE id = :id"), {"id": t}
            )
            await uow.commit()

    async def test_workspace_scoping_blocks_cross_ws_link(self, uow, workspace_id):
        other_ws = uuid.uuid4()
        p = uuid.uuid4()
        r = uuid.uuid4()
        t_other = uuid.uuid4()
        async with uow:
            await _insert_protocol(uow, p, workspace_id)
            await _insert_run(uow, r, p, workspace_id)
            await _insert_target(uow, t_other, other_ws, "ForeignTarget")
            await uow.commit()

        rrepo = SQLAlchemyRunRepository(uow)
        async with uow:
            # Target belongs to another workspace → defense-in-depth no-op.
            await rrepo.add_target(workspace_id, r, t_other)
            await uow.commit()
        async with uow:
            refs = (await rrepo.find_target_refs_for_runs(workspace_id, [r])).get(r, [])
        assert refs == []

    async def test_batched_effective_targets(self, uow, workspace_id):
        p1, p2 = uuid.uuid4(), uuid.uuid4()
        r1 = uuid.uuid4()
        t1, t2 = uuid.uuid4(), uuid.uuid4()
        async with uow:
            await _insert_protocol(uow, p1, workspace_id)
            await _insert_protocol(uow, p2, workspace_id)
            await _insert_run(uow, r1, p1, workspace_id)
            await _insert_target(uow, t1, workspace_id, "A")
            await _insert_target(uow, t2, workspace_id, "B")
            await uow.commit()

        prepo = SQLAlchemyProtocolRepository(uow)
        rrepo = SQLAlchemyRunRepository(uow)
        async with uow:
            await rrepo.add_target(workspace_id, r1, t1)  # inherited on p1
            await prepo.add_direct_target(workspace_id, p2, t2)  # direct on p2
            await uow.commit()

        async with uow:
            batch = await prepo.find_effective_targets_for_protocols(
                workspace_id, [p1, p2]
            )
        assert {x.id for x in batch[p1]} == {t1}
        assert {x.id for x in batch[p2]} == {t2}
