"""Integration tests for the live collection-coverage read model.

Seeds a realistic graph spanning two bounded contexts — runs + readout_data
(screening) and collections + collection_molecules (research-org) — and asserts
the correctness cases for per-run coverage, the protocol roll-up (union over
attaching runs only), the run/protocol gap lists, and the empty-collection
fraction-is-None edge case.

Seed graph:
  Protocol P; collection C (type "library") with 4 members m1..m4 (total=4).
  Run A (protocol P) attaches C; readouts for m1, m2; PLUS a NULL-molecule row.
  Run B (protocol P) attaches C; readouts for m2, m3.
  Run X (protocol P) does NOT attach C; has a readout for m4.
  Collection C2 (empty, attached to a run) — for the total=0 / fraction None case.
"""

from __future__ import annotations

import uuid
from datetime import date

import sqlalchemy as sa

from cellar.domain.research_organization.collection import Collection
from cellar.domain.research_organization.enums import CollectionType
from cellar.infrastructure.persistence.sqlalchemy.research_organization.collection_repository import (  # noqa: E501
    SQLAlchemyCollectionRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.coverage_query import (
    SQLAlchemyCollectionCoverageQuery,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.run_repository import (
    SQLAlchemyRunRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

_USER_ID = uuid.UUID("eeeeeeee-0000-0000-0000-000000000003")


# ---------------------------------------------------------------------------
# Low-level seed helpers (raw SQL — mirrors the proven sibling-test pattern)
# ---------------------------------------------------------------------------


async def _ensure_org(uow: AsyncUnitOfWork, org_id: uuid.UUID, ws_id: uuid.UUID) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO organizations "
            "(id, workspace_id, name, org_type, is_active, version) "
            "VALUES (:id, :ws, 'Test Org', 'internal', true, 1) "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": org_id, "ws": ws_id},
    )


async def _insert_protocol(uow: AsyncUnitOfWork, protocol_id: uuid.UUID, ws_id: uuid.UUID) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO protocols "
            "(id, workspace_id, name, protocol_type, status, "
            "is_locked, dose_unit, pos_control_signal, version, protocol_version, created_by) "
            "VALUES (:id, :ws, :name, 'biochemical', 'active', "
            "false, 'uM', 'high', 1, 1, :user)"
        ),
        {
            "id": protocol_id,
            "ws": ws_id,
            "name": f"Protocol-{str(protocol_id)[:8]}",
            "user": _USER_ID,
        },
    )


async def _insert_run(
    uow: AsyncUnitOfWork, run_id: uuid.UUID, protocol_id: uuid.UUID, ws_id: uuid.UUID
) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO runs "
            "(id, workspace_id, protocol_id, run_date, operator, "
            "status, is_locked, version, notes) "
            "VALUES (:id, :ws, :proto, :run_date, :user, "
            "'draft', false, 1, NULL)"
        ),
        {
            "id": run_id,
            "ws": ws_id,
            "proto": protocol_id,
            "run_date": date.today(),
            "user": _USER_ID,
        },
    )


async def _insert_readout_definition(
    uow: AsyncUnitOfWork, def_id: uuid.UUID, protocol_id: uuid.UUID
) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO readout_definitions "
            "(id, protocol_id, name, data_type, aggregation, "
            "normalizations, is_calculated, display_order) "
            "VALUES (:id, :proto, 'Signal', 'numeric', 'none', "
            "'[]'::jsonb, false, 0)"
        ),
        {"id": def_id, "proto": protocol_id},
    )


async def _insert_readout(
    uow: AsyncUnitOfWork,
    run_id: uuid.UUID,
    molecule_id: uuid.UUID | None,
    readout_definition_id: uuid.UUID,
    ws_id: uuid.UUID,
) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO readout_data "
            "(id, workspace_id, run_id, molecule_id, readout_definition_id, "
            "value_numeric, is_outlier, is_computed) "
            "VALUES (:id, :ws, :run, :mol, :def, 1.0, false, false)"
        ),
        {
            "id": uuid.uuid4(),
            "ws": ws_id,
            "run": run_id,
            "mol": molecule_id,
            "def": readout_definition_id,
        },
    )


async def _insert_molecule(
    uow: AsyncUnitOfWork, mol_id: uuid.UUID, ws_id: uuid.UUID, org_id: uuid.UUID, reg_num: str
) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO molecules "
            "(id, workspace_id, name, molecule_type, structure_status, "
            "registration_status, synthesis_status, lifecycle_stage, "
            "registration_number, originating_org_id, version) "
            "VALUES (:id, :ws, :name, 'small_molecule', 'disclosed', "
            "'approved', 'synthesized', 'registered', :reg, :org, 1)"
        ),
        {
            "id": mol_id,
            "ws": ws_id,
            "name": f"Mol-{reg_num}",
            "reg": reg_num,
            "org": org_id,
        },
    )


async def _insert_collection(
    uow: AsyncUnitOfWork, collection_id: uuid.UUID, ws_id: uuid.UUID, *, name: str
) -> None:
    """Seed a Collection (type LIBRARY) via its aggregate + repository."""
    repo = SQLAlchemyCollectionRepository(uow)
    coll = Collection(
        id=collection_id,
        workspace_id=ws_id,
        name=name,
        created_by=_USER_ID,
        type=CollectionType.LIBRARY,
    )
    await repo.save(coll)


# ---------------------------------------------------------------------------
# Composite fixture: seed the whole graph and return the ids
# ---------------------------------------------------------------------------


class _Graph:
    def __init__(self) -> None:
        self.protocol_id = uuid.uuid4()
        self.run_a = uuid.uuid4()
        self.run_b = uuid.uuid4()
        self.run_x = uuid.uuid4()
        self.coll_c = uuid.uuid4()
        self.coll_c2 = uuid.uuid4()
        self.def_id = uuid.uuid4()
        self.m1 = uuid.uuid4()
        self.m2 = uuid.uuid4()
        self.m3 = uuid.uuid4()
        self.m4 = uuid.uuid4()


async def _seed_graph(uow: AsyncUnitOfWork, ws_id: uuid.UUID) -> _Graph:
    g = _Graph()
    org_id = ws_id  # convention used across the suite: org id == workspace id

    async with uow:
        await _ensure_org(uow, org_id, ws_id)
        await _insert_protocol(uow, g.protocol_id, ws_id)
        await _insert_readout_definition(uow, g.def_id, g.protocol_id)

        await _insert_run(uow, g.run_a, g.protocol_id, ws_id)
        await _insert_run(uow, g.run_b, g.protocol_id, ws_id)
        await _insert_run(uow, g.run_x, g.protocol_id, ws_id)

        for mol_id, reg in (
            (g.m1, "CC-000001"),
            (g.m2, "CC-000002"),
            (g.m3, "CC-000003"),
            (g.m4, "CC-000004"),
        ):
            await _insert_molecule(uow, mol_id, ws_id, org_id, reg)

        await _insert_collection(uow, g.coll_c, ws_id, name=f"C-{str(g.coll_c)[:8]}")
        await _insert_collection(uow, g.coll_c2, ws_id, name=f"C2-{str(g.coll_c2)[:8]}")
        await uow.commit()

    # Membership (C has m1..m4; C2 stays empty) — via the research-org repo.
    repo = SQLAlchemyCollectionRepository(uow)
    async with uow:
        await repo.add_molecules(ws_id, g.coll_c, [g.m1, g.m2, g.m3, g.m4])
        await uow.commit()

    # Run ↔ collection attachments — via the run repo.
    run_repo = SQLAlchemyRunRepository(uow)
    async with uow:
        await run_repo.add_collection(ws_id, g.run_a, g.coll_c)
        await run_repo.add_collection(ws_id, g.run_b, g.coll_c)
        # X intentionally does NOT attach C.
        # C2 (empty) attaches to A so it surfaces in run_coverage.
        await run_repo.add_collection(ws_id, g.run_a, g.coll_c2)
        await uow.commit()

    # Readout rows.
    async with uow:
        # Run A: m1, m2, plus a NULL-molecule row (must not crash counts/gap).
        await _insert_readout(uow, g.run_a, g.m1, g.def_id, ws_id)
        await _insert_readout(uow, g.run_a, g.m2, g.def_id, ws_id)
        await _insert_readout(uow, g.run_a, None, g.def_id, ws_id)
        # Run B: m2, m3.
        await _insert_readout(uow, g.run_b, g.m2, g.def_id, ws_id)
        await _insert_readout(uow, g.run_b, g.m3, g.def_id, ws_id)
        # Run X (does not attach C): m4.
        await _insert_readout(uow, g.run_x, g.m4, g.def_id, ws_id)
        await uow.commit()

    return g


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRunCoverage:
    async def test_per_run_covered_and_total(self, uow, workspace_id):
        g = await _seed_graph(uow, workspace_id)
        query = SQLAlchemyCollectionCoverageQuery(uow)

        async with uow:
            result = await query.run_coverage(workspace_id, [g.run_a, g.run_b])

        # Run A: C covered m1,m2 -> 2 of 4; C2 empty -> 0 of 0.
        a_by_coll = {cov.ref.id: cov for cov in result[g.run_a]}
        assert a_by_coll[g.coll_c].covered == 2
        assert a_by_coll[g.coll_c].total == 4
        assert a_by_coll[g.coll_c].ref.name.startswith("C-")
        assert a_by_coll[g.coll_c].ref.type == "library"
        assert a_by_coll[g.coll_c].fraction == 0.5

        # Run B: C covered m2,m3 -> 2 of 4.
        b_by_coll = {cov.ref.id: cov for cov in result[g.run_b]}
        assert b_by_coll[g.coll_c].covered == 2
        assert b_by_coll[g.coll_c].total == 4

    async def test_empty_collection_fraction_is_none(self, uow, workspace_id):
        g = await _seed_graph(uow, workspace_id)
        query = SQLAlchemyCollectionCoverageQuery(uow)

        async with uow:
            result = await query.run_coverage(workspace_id, [g.run_a])

        a_by_coll = {cov.ref.id: cov for cov in result[g.run_a]}
        assert g.coll_c2 in a_by_coll
        assert a_by_coll[g.coll_c2].total == 0
        assert a_by_coll[g.coll_c2].covered == 0
        assert a_by_coll[g.coll_c2].fraction is None

    async def test_empty_run_ids_returns_empty(self, uow, workspace_id):
        query = SQLAlchemyCollectionCoverageQuery(uow)
        async with uow:
            result = await query.run_coverage(workspace_id, [])
        assert result == {}


class TestProtocolCoverage:
    async def test_union_over_attaching_runs_only(self, uow, workspace_id):
        g = await _seed_graph(uow, workspace_id)
        query = SQLAlchemyCollectionCoverageQuery(uow)

        async with uow:
            result = await query.protocol_coverage(workspace_id, g.protocol_id)

        by_coll = {cov.ref.id: cov for cov in result}
        # C: union of A (m1,m2) and B (m2,m3) = {m1,m2,m3} -> 3; m4 (only on
        # non-attaching X) excluded. total=4, run_count=2 (A and B attach C).
        assert by_coll[g.coll_c].covered == 3
        assert by_coll[g.coll_c].total == 4
        assert by_coll[g.coll_c].run_count == 2
        assert by_coll[g.coll_c].ref.type == "library"
        # C2 attaches to A but has no members covered -> covered 0, total 0.
        assert by_coll[g.coll_c2].covered == 0
        assert by_coll[g.coll_c2].total == 0
        assert by_coll[g.coll_c2].fraction is None


class TestRunGap:
    async def test_run_gap_returns_unscreened_members(self, uow, workspace_id):
        g = await _seed_graph(uow, workspace_id)
        query = SQLAlchemyCollectionCoverageQuery(uow)

        async with uow:
            gap = await query.run_gap(workspace_id, g.run_a, g.coll_c)

        # A screened m1,m2 -> remaining {m3, m4}.
        assert set(gap) == {g.m3, g.m4}


class TestProtocolGap:
    async def test_protocol_gap_returns_unscreened_by_any_attaching_run(self, uow, workspace_id):
        g = await _seed_graph(uow, workspace_id)
        query = SQLAlchemyCollectionCoverageQuery(uow)

        async with uow:
            gap = await query.protocol_gap(workspace_id, g.protocol_id, g.coll_c)

        # Union of A,B screened {m1,m2,m3}; m4 only on non-attaching X -> {m4}.
        assert set(gap) == {g.m4}
