"""Force-delete rules for what references protocols and runs without an FK."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from cellar.application.admin.cascade_service import CascadeBlockedError, InboundReference
from cellar.infrastructure.cascade.cascade_runner import CascadeRunner
from tests.integration.cascade import _rows

_DRAFT_WARNING = (
    "Draft campaigns using this run (their cells re-resolve without it on the next refresh)"
)


def _labels(refs: list[InboundReference] | tuple[InboundReference, ...]) -> dict:
    return {r.display_label: [s["label"] for s in r.samples] for r in refs}


async def test_a_campaign_channel_on_the_protocol_blocks(db_session: AsyncSession) -> None:
    ws = uuid.uuid4()
    protocol = await _rows.protocol(db_session, ws)
    readout = await _rows.readout_definition(db_session, protocol)
    campaign = await _rows.campaign(db_session, ws, name="Kinase panel")
    await _rows.channel(db_session, campaign, protocol, readout)
    runner = CascadeRunner(db_session)

    preview = await runner.preview(parent_table="protocols", parent_id=protocol, workspace_id=ws)
    assert _labels(preview.blockers)["Campaigns with a channel on this protocol"] == [
        "Kinase panel"
    ]

    with pytest.raises(CascadeBlockedError):
        await runner.execute(parent_table="protocols", parent_id=protocol, workspace_id=ws)
    assert await _rows.exists(db_session, "protocols", protocol)


async def test_a_channel_naming_only_one_of_its_readouts_still_blocks(
    db_session: AsyncSession,
) -> None:
    ws = uuid.uuid4()
    protocol = await _rows.protocol(db_session, ws)
    readout = await _rows.readout_definition(db_session, protocol)
    counter_screen = await _rows.protocol(db_session, ws, name="Counter-screen")
    campaign = await _rows.campaign(db_session, ws)
    await _rows.channel(db_session, campaign, counter_screen, readout)

    plan = await CascadeRunner(db_session).plan(
        parent_table="protocols", parent_id=protocol, workspace_id=ws
    )

    assert "Campaigns with a channel on this protocol" in _labels(plan.blockers)


async def test_an_import_template_defaulting_to_the_protocol_blocks(
    db_session: AsyncSession,
) -> None:
    ws = uuid.uuid4()
    protocol = await _rows.protocol(db_session, ws)
    await _rows.import_template(db_session, ws, default_protocol_id=protocol)

    plan = await CascadeRunner(db_session).plan(
        parent_table="protocols", parent_id=protocol, workspace_id=ws
    )

    assert _labels(plan.blockers) == {
        "Plate import templates defaulting to this protocol": ["CRO sheet"]
    }


async def test_flags_and_attachments_go_with_the_protocol_and_its_runs(
    db_session: AsyncSession,
) -> None:
    ws = uuid.uuid4()
    protocol = await _rows.protocol(db_session, ws)
    run = await _rows.run(db_session, ws, protocol)
    flag = await _rows.compound_flag(
        db_session, ws, protocol_id=protocol, molecule_id=uuid.uuid4()
    )
    protocol_file = await _rows.attachment(db_session, ws, "protocol", protocol)
    run_file = await _rows.attachment(db_session, ws, "run", run)
    # Same id, different owner type: not this protocol's file.
    unrelated_file = await _rows.attachment(db_session, ws, "molecule", protocol)

    entries = await CascadeRunner(db_session).execute(
        parent_table="protocols", parent_id=protocol, workspace_id=ws
    )

    deleted = {(e.entity_type, e.entity_id) for e in entries}
    assert {
        ("compound_flag", flag),
        ("attachment", protocol_file),
        ("attachment", run_file),
    } <= deleted
    assert not await _rows.exists(db_session, "attachments", run_file)
    assert await _rows.exists(db_session, "attachments", unrelated_file)


@pytest.mark.parametrize("citation", ["seed run", "source run", "contributing run"])
async def test_a_closed_campaign_citing_the_run_blocks(
    db_session: AsyncSession, citation: str
) -> None:
    ws = uuid.uuid4()
    protocol = await _rows.protocol(db_session, ws)
    run = await _rows.run(db_session, ws, protocol)
    seeds = [(run, protocol)] if citation == "seed run" else []
    campaign = await _rows.campaign(db_session, ws, name="Closed panel", seed_runs=seeds)
    if citation != "seed run":
        # A channel on another protocol, so only the run citation can match.
        channel = await _rows.channel(db_session, campaign, uuid.uuid4(), uuid.uuid4())
        result = await _rows.result(db_session, campaign, uuid.uuid4())
        await _rows.measurement(
            db_session,
            result,
            channel,
            source_run_id=run if citation == "source run" else None,
            contributing_run_ids=[run] if citation == "contributing run" else None,
        )
    await _rows.set_campaign_status(db_session, campaign, "closed")

    with pytest.raises(CascadeBlockedError) as refused:
        await CascadeRunner(db_session).execute(
            parent_table="runs", parent_id=run, workspace_id=ws
        )

    assert _labels(refused.value.blockers) == {
        "Closed or superseded campaigns citing this run": ["Closed panel"]
    }


async def test_a_draft_seeded_from_the_run_warns_and_keeps_its_seed_list(
    db_session: AsyncSession,
) -> None:
    ws = uuid.uuid4()
    protocol = await _rows.protocol(db_session, ws)
    run = await _rows.run(db_session, ws, protocol)
    campaign = await _rows.campaign(
        db_session, ws, name="Draft panel", seed_runs=[(run, protocol)]
    )
    runner = CascadeRunner(db_session)

    preview = await runner.preview(parent_table="runs", parent_id=run, workspace_id=ws)
    assert preview.blockers == []
    assert _labels(preview.warnings) == {_DRAFT_WARNING: ["Draft panel"]}

    await runner.execute(parent_table="runs", parent_id=run, workspace_id=ws)

    assert not await _rows.exists(db_session, "runs", run)
    seeds = await db_session.scalar(
        sa.text("SELECT seed_runs FROM campaign WHERE id = :id"), {"id": campaign}
    )
    assert seeds == [{"run_id": str(run), "protocol_id": str(protocol)}]
