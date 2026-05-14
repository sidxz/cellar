"""Integration smoke for the SQL ChannelResolutionQuery.

Deep verification of the join is exercised indirectly by the
close-campaign integration tests in Phase 5 (which seed real
curves/runs/protocols and round-trip through this query). This module
only confirms the class is wireable and returns an empty list when no
data matches, plus a multi-DR regression that pins the readout-def
disambiguation behavior.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa


@pytest.mark.asyncio
async def test_empty_candidates_for_unknown_molecule(session_factory):
    from cellar.domain.research_organization.campaign_channel import (
        CampaignChannel,
    )
    from cellar.domain.research_organization.enums import (
        ChannelSourceKind,
        QualifierHandling,
        SelectionRule,
    )
    from cellar.infrastructure.persistence.sqlalchemy.research_organization.channel_resolution_query import (
        SQLAlchemyChannelResolutionQuery,
    )

    query = SQLAlchemyChannelResolutionQuery(session_factory)
    channel = CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="IC50",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )
    candidates = await query.fetch_candidates(
        workspace_id=uuid.uuid4(),
        channel=channel,
        molecule_id=uuid.uuid4(),
    )
    assert candidates == []


@pytest.mark.asyncio
async def test_multi_dr_protocol_disambiguates_by_readout_def(session_factory):
    """A protocol with two DR readouts sharing the same curve_type must
    surface only the curve fitted from each channel's own readout-def.

    Regression for the pre-033 bug where the resolver filtered by
    (workspace, molecule, protocol) only — two curves of curve_type=ic50
    on the same protocol would both come back and the selection rule
    would silently pick one. Post-033 the readout-def FK pins identity.
    """
    from cellar.domain.research_organization.campaign_channel import CampaignChannel
    from cellar.domain.research_organization.enums import (
        ChannelSourceKind,
        QualifierHandling,
        SelectionRule,
    )
    from cellar.infrastructure.persistence.sqlalchemy.research_organization.channel_resolution_query import (
        SQLAlchemyChannelResolutionQuery,
    )

    ws_id = uuid.uuid4()
    org_id = uuid.uuid4()
    user_id = uuid.UUID("eeeeeeee-0000-0000-0000-000000000001")
    protocol_id = uuid.uuid4()
    run_id = uuid.uuid4()
    molecule_id = uuid.uuid4()
    batch_id = uuid.uuid4()
    rd_target_id = uuid.uuid4()
    rd_counter_id = uuid.uuid4()
    curve_target_id = uuid.uuid4()
    curve_counter_id = uuid.uuid4()

    async with session_factory() as session, session.begin():
        await session.execute(
            sa.text(
                "INSERT INTO organizations "
                "(id, workspace_id, name, org_type, is_active, version) "
                "VALUES (:id, :ws, 'Test Org', 'internal', true, 1) "
                "ON CONFLICT DO NOTHING"
            ),
            {"id": org_id, "ws": ws_id},
        )
        await session.execute(
            sa.text(
                "INSERT INTO protocols "
                "(id, workspace_id, name, protocol_type, status, "
                "is_locked, dose_unit, pos_control_signal, version, "
                "protocol_version, created_by) "
                "VALUES (:id, :ws, 'Multi-DR', 'biochemical', 'active', "
                "false, 'uM', 'high', 1, 1, :user)"
            ),
            {"id": protocol_id, "ws": ws_id, "user": user_id},
        )
        await session.execute(
            sa.text(
                "INSERT INTO readout_definitions "
                "(id, protocol_id, name, data_type, display_order, "
                "is_calculated) "
                "VALUES (:id, :proto, :name, 'numeric', 0, false)"
            ),
            {"id": rd_target_id, "proto": protocol_id, "name": "Target IC50"},
        )
        await session.execute(
            sa.text(
                "INSERT INTO readout_definitions "
                "(id, protocol_id, name, data_type, display_order, "
                "is_calculated) "
                "VALUES (:id, :proto, :name, 'numeric', 1, false)"
            ),
            {"id": rd_counter_id, "proto": protocol_id, "name": "Counter IC50"},
        )
        await session.execute(
            sa.text(
                "INSERT INTO runs "
                "(id, workspace_id, protocol_id, run_date, operator, "
                "status, is_locked, version, notes) "
                "VALUES (:id, :ws, :proto, :run_date, :user, 'approved', "
                "false, 1, NULL)"
            ),
            {
                "id": run_id,
                "ws": ws_id,
                "proto": protocol_id,
                "run_date": date.today(),
                "user": user_id,
            },
        )
        # Two curves, same curve_type, different readout-defs, same
        # (run, molecule, batch). Pre-033 unique key (run, curve_type)
        # would have rejected this; post-033 the unique key includes
        # readout_definition_id so both rows coexist.
        for cid, rd_id, fitted in [
            (curve_target_id, rd_target_id, 0.50),
            (curve_counter_id, rd_counter_id, 12.5),
        ]:
            await session.execute(
                sa.text(
                    "INSERT INTO dose_response_curves "
                    "(id, workspace_id, molecule_id, batch_id, protocol_id, "
                    "run_id, readout_definition_id, curve_type, fitted_value, "
                    "hill_slope, top, bottom, r_squared, num_points) "
                    "VALUES (:id, :ws, :mol, :batch, :proto, :run, :rd, "
                    "'ic50', :fitted, 1.0, 100.0, 0.0, 0.95, 8)"
                ),
                {
                    "id": cid,
                    "ws": ws_id,
                    "mol": molecule_id,
                    "batch": batch_id,
                    "proto": protocol_id,
                    "run": run_id,
                    "rd": rd_id,
                    "fitted": fitted,
                },
            )

    query = SQLAlchemyChannelResolutionQuery(session_factory)

    target_channel = CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="Target IC50",
        protocol_id=protocol_id,
        readout_definition_id=rd_target_id,
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )
    counter_channel = CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="Counter IC50",
        protocol_id=protocol_id,
        readout_definition_id=rd_counter_id,
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=1,
    )

    target_candidates = await query.fetch_candidates(
        workspace_id=ws_id, channel=target_channel, molecule_id=molecule_id
    )
    counter_candidates = await query.fetch_candidates(
        workspace_id=ws_id, channel=counter_channel, molecule_id=molecule_id
    )

    assert len(target_candidates) == 1, (
        "Target channel must see exactly its own curve, not the sibling DR."
    )
    assert target_candidates[0].curve_id == curve_target_id
    assert target_candidates[0].value == pytest.approx(0.50)

    assert len(counter_candidates) == 1
    assert counter_candidates[0].curve_id == curve_counter_id
    assert counter_candidates[0].value == pytest.approx(12.5)


@pytest.mark.asyncio
async def test_empty_candidates_for_readout_source(session_factory):
    """Same smoke for the READOUT_DATA branch of the query."""
    from cellar.domain.research_organization.campaign_channel import (
        CampaignChannel,
    )
    from cellar.domain.research_organization.enums import (
        ChannelSourceKind,
        QualifierHandling,
        SelectionRule,
    )
    from cellar.infrastructure.persistence.sqlalchemy.research_organization.channel_resolution_query import (
        SQLAlchemyChannelResolutionQuery,
    )

    query = SQLAlchemyChannelResolutionQuery(session_factory)
    channel = CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="% inhibition",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.READOUT_DATA,
        selection_rule=SelectionRule.MEAN_ACROSS_RUNS,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )
    candidates = await query.fetch_candidates(
        workspace_id=uuid.uuid4(),
        channel=channel,
        molecule_id=uuid.uuid4(),
    )
    assert candidates == []
