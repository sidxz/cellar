"""Migration 105: batches from the CDD automated import keep their CDD batch name as
a real batch ID (spec 2026-11-18 §4a).

The test schema is already at head, so the batches are set up first and the
migration's upgrade is run again over them inside a transaction that rolls back.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from cellar.application.inventory.create_batch import (
    CreateBatch,
    CreateBatchCommand,
    NewBatchIdentifier,
)
from cellar.application.inventory.sync_batch_identifier_mirrors import SyncBatchIdentifierMirrors
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (  # noqa: E501
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

_M105 = Path(__file__).parents[3] / "alembic" / "versions" / "105_cdd_batch_name_backfill.py"


def _upgrade(sync_session) -> None:  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("m105", _M105)
    assert spec is not None and spec.loader is not None
    m105 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m105)
    with Operations.context(MigrationContext.configure(sync_session.connection())):
        m105.upgrade()


async def _snapshot(session, workspace_id) -> set[tuple]:  # type: ignore[no-untyped-def]
    """(batch number, identifier, type, source, is automatic, registered_by)."""
    rows = await session.execute(
        sa.text(
            "SELECT b.batch_number, bi.identifier, bi.identifier_type, bi.source, "
            "bi.derived_from_molecule_identifier_id IS NOT NULL, bi.registered_by "
            "FROM batch_identifiers bi JOIN batches b ON b.id = bi.batch_id "
            "WHERE bi.workspace_id = :ws"
        ),
        {"ws": workspace_id},
    )
    return {tuple(r) for r in rows.all()}


async def test_backfill_turns_cdd_batch_names_into_real_ids(
    session_factory, seeded_workspace_and_molecule, fake_event_dispatcher
) -> None:
    # Molecule CC-000001 has the compound ID "SACC-0001", so each of its batches
    # gets the automatic alias "SACC-0001-<ChemCellar suffix>".
    workspace_id, molecule_id, _ident_id, chemist = seeded_workspace_and_molecule
    uow = AsyncUnitOfWork(session_factory)
    batch_repo = SQLAlchemyBatchRepository(uow)
    create = CreateBatch(
        uow=uow,
        repo=batch_repo,
        molecule_repo=SQLAlchemyMoleculeRepository(uow),
        dispatcher=fake_event_dispatcher,
        sync=SyncBatchIdentifierMirrors(batch_repo),
    )

    async def batch(**kw) -> str:  # type: ignore[no-untyped-def]
        cmd = CreateBatchCommand(
            workspace_id=workspace_id,
            molecule_id=molecule_id,
            source="synthesized",
            chemist=chemist,
            amount_value=1.0,
            amount_unit="mg",
            **kw,
        )
        return (await create(cmd)).unwrap().batch.batch_number.value

    # -001: CDD batch whose automatic alias holds its CDD batch name → becomes real.
    aliased = await batch(
        custom_fields={"cdd_batch_id": 123}, vendor_catalog_number="SACC-0001-001"
    )
    # -002: CDD batch with no ID carrying its name → one is inserted.
    missing = await batch(custom_fields={"cdd_batch_id": 124}, vendor_catalog_number="CDD-B-002")
    # -003: a real ID "TAKEN-1" on a batch that is not from CDD …
    holder = await batch(identifiers=(NewBatchIdentifier("TAKEN-1", "custom", "Lab notebook"),))
    # -004: … so the CDD batch named "TAKEN-1" is skipped.
    clash = await batch(custom_fields={"cdd_batch_id": 125}, vendor_catalog_number="TAKEN-1")
    # -005: not from CDD: its alias equal to vendor_catalog_number stays automatic.
    plain = await batch(vendor_catalog_number="SACC-0001-005")

    async with session_factory() as session:
        before = await _snapshot(session, workspace_id)
        assert (aliased, "SACC-0001-001", "custom", "compound-syn", True, chemist) in before

        await session.run_sync(_upgrade)
        after = await _snapshot(session, workspace_id)
        await session.run_sync(_upgrade)
        again = await _snapshot(session, workspace_id)
        await session.rollback()

    assert after - before == {
        (aliased, "SACC-0001-001", "custom", "CDD batch ID", False, chemist),
        (missing, "CDD-B-002", "custom", "CDD batch ID", False, chemist),
    }
    assert before - after == {(aliased, "SACC-0001-001", "custom", "compound-syn", True, chemist)}
    assert {r for r in after if r[0] == clash} == {
        (clash, "SACC-0001-004", "custom", "compound-syn", True, chemist)
    }
    assert (holder, "TAKEN-1", "custom", "Lab notebook", False, chemist) in after
    assert (plain, "SACC-0001-005", "custom", "compound-syn", True, chemist) in after
    assert again == after  # a second run changes nothing
