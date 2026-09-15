"""Force-delete rules for what references molecules and their batches without an FK."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from cellar.domain.audit_compliance.enums import AuditAction
from cellar.infrastructure.cascade.cascade_runner import CascadePlan, CascadeRunner
from tests.integration.cascade import _rows


def _labels(plan: CascadePlan) -> dict:
    return {r.display_label: [s["label"] for s in r.samples] for r in plan.blockers}


async def _plan(session: AsyncSession, ws: uuid.UUID, molecule: uuid.UUID) -> CascadePlan:
    return await CascadeRunner(session).plan(
        parent_table="molecules", parent_id=molecule, workspace_id=ws
    )


async def _registered(session: AsyncSession, ws: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """A molecule with one batch."""
    org = await _rows.org(session, ws)
    molecule = await _rows.molecule(session, ws, org)
    return molecule, await _rows.batch(session, ws, molecule)


async def _assay(session: AsyncSession, ws: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """A protocol, its readout definition, and one run."""
    protocol = await _rows.protocol(session, ws)
    readout = await _rows.readout_definition(session, protocol)
    return protocol, readout, await _rows.run(session, ws, protocol)


async def test_readout_rows_for_the_molecule_block(db_session: AsyncSession) -> None:
    ws = uuid.uuid4()
    molecule, _batch = await _registered(db_session, ws)
    _protocol, readout, run = await _assay(db_session, ws)
    await _rows.readout_data(db_session, ws, run, readout, molecule_id=molecule)

    assert _labels(await _plan(db_session, ws, molecule)) == {
        "Runs with data for this molecule": ["2026-09-15"]
    }


async def test_a_curve_blocks_through_the_molecule_and_its_batch(db_session: AsyncSession) -> None:
    ws = uuid.uuid4()
    molecule, batch = await _registered(db_session, ws)
    protocol, readout, run = await _assay(db_session, ws)
    await _rows.curve(
        db_session,
        ws,
        run_id=run,
        protocol_id=protocol,
        readout_definition_id=readout,
        molecule_id=molecule,
        batch_id=batch,
    )

    assert set(_labels(await _plan(db_session, ws, molecule))) == {
        "Runs with data for this molecule",
        "Runs with data for this molecule's batches",
    }


async def test_a_well_holding_its_batch_blocks(db_session: AsyncSession) -> None:
    ws = uuid.uuid4()
    molecule, batch = await _registered(db_session, ws)
    _protocol, _readout, run = await _assay(db_session, ws)
    await _rows.wells(db_session, await _rows.plate(db_session, run), 1, batch_id=batch)

    assert _labels(await _plan(db_session, ws, molecule)) == {
        "Runs with data for this molecule's batches": ["2026-09-15"]
    }


async def test_a_campaign_row_for_the_molecule_blocks(db_session: AsyncSession) -> None:
    ws = uuid.uuid4()
    molecule, _batch = await _registered(db_session, ws)
    campaign = await _rows.campaign(db_session, ws, name="Hit follow-up")
    await _rows.result(db_session, campaign, molecule)

    assert _labels(await _plan(db_session, ws, molecule)) == {
        "Campaigns with a row for this molecule": ["Hit follow-up"]
    }


@pytest.mark.parametrize(
    ("table", "open_status", "finished_status"),
    [
        ("sample_requests", "approved", "fulfilled"),
        ("synthesis_requests", "in_progress", "failed"),
    ],
)
async def test_open_requests_block_and_finished_ones_go_with_the_molecule(
    db_session: AsyncSession, table: str, open_status: str, finished_status: str
) -> None:
    ws = uuid.uuid4()
    molecule, _batch = await _registered(db_session, ws)
    add = _rows.sample_request if table == "sample_requests" else _rows.synthesis_request
    open_request = await add(db_session, ws, molecule, status=open_status)
    finished_request = await add(db_session, ws, molecule, status=finished_status)
    runner = CascadeRunner(db_session)

    [blocker] = (
        await runner.plan(parent_table="molecules", parent_id=molecule, workspace_id=ws)
    ).blockers
    assert (blocker.table, blocker.count, blocker.samples[0]["id"]) == (
        table,
        1,
        str(open_request),
    )

    await db_session.execute(
        sa.text(f"UPDATE {table} SET status = :status WHERE id = :id"),
        {"status": finished_status, "id": open_request},
    )
    await runner.execute(parent_table="molecules", parent_id=molecule, workspace_id=ws)
    assert not await _rows.exists(db_session, table, open_request)
    assert not await _rows.exists(db_session, table, finished_request)


async def test_a_plate_well_map_holding_its_batch_blocks(db_session: AsyncSession) -> None:
    ws = uuid.uuid4()
    molecule, batch = await _registered(db_session, ws)
    await _rows.registered_plate(
        db_session, ws, barcode="PL-0001", well_map={"A1": {"batch_id": str(batch)}}
    )
    # A JSON null well map, like every legacy tracker plate, must not break the query.
    await _rows.registered_plate(db_session, ws, barcode="PL-0002", well_map=None)

    assert _labels(await _plan(db_session, ws, molecule)) == {
        "Inventory plates holding these batches": ["PL-0001"]
    }


async def test_tombstones_sync_rows_flags_and_files_go_with_the_molecule(
    db_session: AsyncSession,
) -> None:
    ws = uuid.uuid4()
    org = await _rows.org(db_session, ws)
    molecule = await _rows.molecule(db_session, ws, org, reg="CC-000001")
    tombstone = await _rows.molecule(db_session, ws, org, reg="CC-000002", merged_into_id=molecule)
    batch = await _rows.batch(db_session, ws, molecule)
    sync = await _rows.cdd_sync(db_session, ws, molecule)
    flag = await _rows.compound_flag(
        db_session, ws, protocol_id=uuid.uuid4(), molecule_id=molecule
    )
    molecule_file = await _rows.attachment(db_session, ws, "molecule", molecule)
    batch_file = await _rows.attachment(db_session, ws, "batch", batch)

    entries = await CascadeRunner(db_session).execute(
        parent_table="molecules", parent_id=molecule, workspace_id=ws
    )

    assert {molecule, tombstone, batch, sync, flag, molecule_file, batch_file} <= {
        e.entity_id for e in entries
    }
    for table, row in (
        ("molecules", tombstone),
        ("cdd_molecule_sync", sync),
        ("attachments", batch_file),
    ):
        assert not await _rows.exists(db_session, table, row)


async def test_links_from_records_that_stay_are_cleared_and_audited(
    db_session: AsyncSession,
) -> None:
    ws = uuid.uuid4()
    org = await _rows.org(db_session, ws)
    molecule = await _rows.molecule(db_session, ws, org, reg="CC-000001")
    batch = await _rows.batch(db_session, ws, molecule)
    other = await _rows.molecule(db_session, ws, org, reg="CC-000009")
    step = await _rows.reaction_step(
        db_session,
        await _rows.synthesis_route(db_session, ws, other),
        product_molecule_id=molecule,
        batch_id=batch,
    )
    request = await _rows.sample_request(db_session, ws, other, status="fulfilled", batch_id=batch)
    merge = await _rows.merge_event(
        db_session,
        ws,
        source_molecule_id=other,
        target_molecule_id=await _rows.molecule(db_session, ws, org, reg="CC-000010"),
        disclosure_request_id=await _rows.disclosure_request(db_session, ws, molecule),
    )

    entries = await CascadeRunner(db_session).execute(
        parent_table="molecules", parent_id=molecule, workspace_id=ws
    )

    assert {(e.entity_id, e.field_name) for e in entries if e.action == AuditAction.UPDATE} == {
        (step, "product_molecule_id"),
        (step, "batch_id"),
        (request, "batch_id"),
        (merge, "disclosure_request_id"),
    }
    row = (
        await db_session.execute(
            sa.text("SELECT product_molecule_id, batch_id FROM reaction_steps WHERE id = :id"),
            {"id": step},
        )
    ).one()
    assert tuple(row) == (None, None)
