"""CascadeRunner.plan: one exhaustive walk behind both preview and execute."""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from cellar.application.admin.cascade_service import CascadeBlockedError
from cellar.domain.audit_compliance.enums import AuditAction
from cellar.domain.shared.cascade.actions import CascadeAction
from cellar.infrastructure.cascade.cascade_runner import CascadeRunner
from cellar.infrastructure.cascade.rules import CascadeRule
from tests.integration.cascade import _rows

_READOUT_BLOCK = CascadeRule(
    child_table="readout_data",
    parent_table="runs",
    action=CascadeAction.BLOCK,
    fk_column="run_id",
    display_label="Test: readout rows",
)


async def _protocol_with_runs(session: AsyncSession, ws: uuid.UUID, runs: int) -> uuid.UUID:
    protocol = await _rows.protocol(session, ws)
    readout = await _rows.readout_definition(session, protocol)
    for _ in range(runs):
        run = await _rows.run(session, ws, protocol)
        await _rows.readout_data(session, ws, run, readout)
    return protocol


async def test_plan_counts_a_blocker_across_every_run_not_the_preview_sample(
    db_session: AsyncSession, extra_rules: Callable[..., None]
) -> None:
    ws = uuid.uuid4()
    protocol = await _protocol_with_runs(db_session, ws, runs=12)
    extra_rules(_READOUT_BLOCK)

    plan = await CascadeRunner(db_session).plan(
        parent_table="protocols", parent_id=protocol, workspace_id=ws
    )

    [blocker] = [b for b in plan.blockers if b.display_label == "Test: readout rows"]
    assert blocker.count == 12
    assert len(blocker.samples) == 5
    assert blocker.truncated


async def test_execute_refuses_with_every_blocker_and_changes_nothing(
    db_session: AsyncSession, extra_rules: Callable[..., None]
) -> None:
    ws = uuid.uuid4()
    protocol = await _protocol_with_runs(db_session, ws, runs=3)
    extra_rules(_READOUT_BLOCK)

    with pytest.raises(CascadeBlockedError) as refused:
        await CascadeRunner(db_session).execute(
            parent_table="protocols", parent_id=protocol, workspace_id=ws
        )

    [blocker] = [b for b in refused.value.blockers if b.display_label == "Test: readout rows"]
    assert blocker.count == 3
    assert await _rows.exists(db_session, "protocols", protocol)


async def test_warn_rules_are_listed_and_the_delete_goes_ahead(
    db_session: AsyncSession, extra_rules: Callable[..., None]
) -> None:
    ws = uuid.uuid4()
    protocol = await _protocol_with_runs(db_session, ws, runs=1)
    extra_rules(
        CascadeRule(
            child_table="readout_data",
            parent_table="runs",
            action=CascadeAction.WARN,
            fk_column="run_id",
            display_label="Test: readout rows",
        )
    )
    runner = CascadeRunner(db_session)

    preview = await runner.preview(parent_table="protocols", parent_id=protocol, workspace_id=ws)
    assert "Test: readout rows" in [w.display_label for w in preview.warnings]

    await runner.execute(parent_table="protocols", parent_id=protocol, workspace_id=ws)
    assert not await _rows.exists(db_session, "protocols", protocol)


async def test_preview_keeps_block_and_warn_rules_out_of_the_tree(
    db_session: AsyncSession, extra_rules: Callable[..., None]
) -> None:
    ws = uuid.uuid4()
    protocol = await _rows.protocol(db_session, ws)
    template = await _rows.import_template(db_session, ws, default_protocol_id=protocol)
    extra_rules(
        CascadeRule(
            child_table="import_templates",
            parent_table="protocols",
            action=CascadeAction.BLOCK,
            fk_column="default_protocol_id",
            label_field="name",
            display_label="Test: templates",
        )
    )

    preview = await CascadeRunner(db_session).preview(
        parent_table="protocols", parent_id=protocol, workspace_id=ws
    )

    assert all(child.action != CascadeAction.BLOCK for child in preview.root.children)
    [blocker] = [b for b in preview.blockers if b.display_label == "Test: templates"]
    assert blocker.samples == [{"id": str(template), "label": "CRO sheet"}]


async def test_set_null_is_audited_as_an_update(db_session: AsyncSession) -> None:
    ws = uuid.uuid4()
    parent = await _rows.protocol(db_session, ws)
    successor = await _rows.protocol(
        db_session, ws, name="Kinase assay v2", parent_protocol_id=parent
    )

    entries = await CascadeRunner(db_session).execute(
        parent_table="protocols", parent_id=parent, workspace_id=ws
    )

    [update] = [e for e in entries if e.action == AuditAction.UPDATE]
    assert (update.entity_type, update.entity_id, update.field_name) == (
        "protocol",
        successor,
        "parent_protocol_id",
    )
    assert (update.old_value, update.new_value) == (str(parent), None)


async def test_a_row_the_delete_removes_is_not_also_cleared(db_session: AsyncSession) -> None:
    ws = uuid.uuid4()
    org = await _rows.org(db_session, ws)
    molecule = await _rows.molecule(db_session, ws, org)
    request = await _rows.disclosure_request(
        db_session, ws, molecule, matched_molecule_id=molecule
    )

    entries = await CascadeRunner(db_session).execute(
        parent_table="molecules", parent_id=molecule, workspace_id=ws
    )

    assert [e.action for e in entries if e.entity_id == request] == [AuditAction.DELETE]


async def test_execute_deletes_more_rows_than_asyncpg_can_bind(db_session: AsyncSession) -> None:
    ws = uuid.uuid4()
    protocol = await _rows.protocol(db_session, ws)
    plate = await _rows.plate(db_session, await _rows.run(db_session, ws, protocol))
    await _rows.wells(db_session, plate, 33_000)

    await CascadeRunner(db_session).execute(
        parent_table="protocols", parent_id=protocol, workspace_id=ws
    )

    left = await db_session.scalar(
        sa.text("SELECT count(*) FROM wells WHERE plate_id = :plate"), {"plate": plate}
    )
    assert left == 0
